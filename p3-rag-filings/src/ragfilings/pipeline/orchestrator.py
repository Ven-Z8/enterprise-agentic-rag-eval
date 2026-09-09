"""Multi-agent LangGraph orchestrator over the 10-K RAG pipeline.

Graph topology:

    plan ─▶ retrieve ─▶ analyze ─▶ synthesize ─▶ audit ─▶ END
                                       ▲            │
                                       └── retry ───┘   (bounded, on audit failure)

Every node is a real step: the planner and auditor are instructor-validated
structured calls, the researcher is a native tool-calling loop, analyze runs
the deterministic safe-eval math tool, and synthesize produces a typed cited
answer. Token/cost usage is accumulated from API-reported usage on every
call — nothing is estimated.
"""

from __future__ import annotations

import logging
import operator
import time
import uuid
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from ..agents.auditor import audit_answer
from ..agents.planner import plan_query
from ..agents.researcher import run_researcher
from ..agents.synthesis import synthesize
from ..retrieval import Index, confidence
from ..tools import compute_financial_math, needs_decomposition
from ..tools.verification import verify
from .memory import SessionMemoryManager

logger = logging.getLogger(__name__)


class OrchestratorState(TypedDict, total=False):
    session_id: str
    query: str
    index: Any
    cfg: dict[str, Any]
    graph_engine: Any
    plan: dict[str, Any]
    hits: list[dict[str, Any]]
    math_result: Optional[dict[str, Any]]
    answer: Optional[str]
    citations: list[str]
    invalid_citations: list[str]
    feedback: Optional[str]
    audit: Optional[dict[str, Any]]
    verification: dict[str, Any]
    verified: bool
    refused: bool
    refusal_reason: Optional[str]
    usage: dict[str, Any]
    retries_left: int
    steps: Annotated[list[dict[str, Any]], operator.add]


def _step(agent: str, action: str, input_payload: Any, output_payload: Any) -> dict[str, Any]:
    return {"agent": agent, "action": action,
            "input": input_payload, "output": output_payload}


def _merge_usage(state: OrchestratorState, u: dict[str, Any]) -> None:
    acc = state["usage"]
    acc["input_tokens"] += u.get("input_tokens", 0)
    acc["output_tokens"] += u.get("output_tokens", 0)
    acc["cost_usd"] += u.get("cost_usd", 0.0)
    acc["calls"] += u.get("calls", 1)


def build_workflow() -> StateGraph:
    def plan_node(state: OrchestratorState) -> dict[str, Any]:
        plan, usage = plan_query(state["query"], state["cfg"], state["index"].chunks)
        _merge_usage(state, usage)
        plan_d = plan.model_dump()
        return {
            "plan": plan_d,
            "steps": [_step("Planner", "plan_query", {"query": state["query"]}, plan_d)],
        }

    def retrieve_node(state: OrchestratorState) -> dict[str, Any]:
        from ..schemas import QueryPlan

        plan = QueryPlan(**state["plan"])
        if plan.intent == "not_in_corpus" and not plan.sub_questions:
            return {
                "refused": True,
                "refusal_reason": f"planner: question outside corpus scope ({plan.reasoning})",
                "steps": [_step("Researcher", "skipped", {}, "out-of-corpus plan")],
            }

        res = run_researcher(state["query"], plan, state["index"], state["cfg"],
                             state["usage"],
                             graph_engine=state.get("graph_engine"))
        hits = res["hits"]

        conf = confidence(hits)
        min_conf = state["cfg"].get("verification", {}).get("min_confidence", 0.35)
        update: dict[str, Any] = {
            "hits": hits,
            "steps": [_step("Researcher", "tool_loop",
                            {"sub_questions": plan.sub_questions,
                             "ticker": plan.ticker, "fiscal_year": plan.fiscal_year},
                            {"n_hits": len(hits), "confidence": round(conf, 4),
                             "tool_calls": res["events"], "notes": res["notes"]})],
        }
        if not hits or conf < min_conf:
            reason = ("no retrieval hits" if not hits
                      else f"low retrieval confidence: {conf:.3f} < {min_conf}")
            update.update({"refused": True, "refusal_reason": reason})
        return update

    def analyze_node(state: OrchestratorState) -> dict[str, Any]:
        plan = state.get("plan", {})
        needs_math = bool(plan.get("needs_math")) or needs_decomposition(state["query"])
        if not needs_math or not state.get("hits"):
            return {"steps": [_step("DataAnalyst", "skipped", {}, "no computation needed")]}

        chunks = [h["chunk"] for h in state["hits"]]
        math_res = compute_financial_math(state["query"], chunks, state["cfg"])
        if math_res:
            _merge_usage(state, math_res.pop("usage", {}))
        return {
            "math_result": math_res,
            "steps": [_step("DataAnalyst", "safe_eval_math",
                            {"query": state["query"]},
                            math_res or {"calculated": False})],
        }

    def synthesize_node(state: OrchestratorState) -> dict[str, Any]:
        instance = synthesize(
            state["query"], state["hits"], state["cfg"], state["usage"],
            math_result=state.get("math_result"),
            feedback=state.get("feedback"),
        )
        return {
            "answer": instance.answer,
            "citations": instance.citations,
            "feedback": None,
            "steps": [_step("Synthesizer", "grounded_synthesis",
                            {"n_context": len(state["hits"]),
                             "retry_feedback": bool(state.get("feedback"))},
                            {"answer_len": len(instance.answer or ""),
                             "citations": instance.citations})],
        }

    def audit_node(state: OrchestratorState) -> dict[str, Any]:
        if state.get("refused") or not state.get("answer"):
            if not state.get("refused") and not state.get("answer"):
                return {
                    "refused": True,
                    "refusal_reason": "model could not answer from the retrieved context",
                    "verified": False,
                }
            return {"verified": False}

        by_id = {h["chunk"]["id"]: h["chunk"] for h in state["hits"]}
        citations = [c for c in state.get("citations", []) if isinstance(c, str)]
        valid = [c for c in citations if c in by_id]
        invalid = [c for c in citations if c not in by_id]
        cited_chunks = [by_id[c] for c in valid] or [h["chunk"] for h in state["hits"]]

        checked = verify(str(state["answer"]), cited_chunks,
                         math_result=state.get("math_result"))
        audit_res = audit_answer(
            state["query"], str(state["answer"]), citations, state["hits"],
            state["cfg"], state["usage"], math_result=state.get("math_result"),
        )
        audit_d = audit_res.model_dump()
        llm_ok = bool(audit_d.get("verified")) and not audit_d.get("refuse")

        problems: list[str] = []
        if not checked["verified"]:
            failed = [c["raw"] for c in checked["claims"] if not c["found"]]
            problems.append(f"figures not found in cited chunks: {', '.join(failed)}")
        if invalid:
            problems.append(f"nonexistent citation ids: {', '.join(invalid)}")
        for claim in audit_d.get("audit_claims", []):
            if claim.get("status") == "UNVERIFIED":
                problems.append(f"auditor: {claim.get('figure')} unverified")
        if audit_d.get("refuse"):
            problems.append("auditor: context too thin to answer")

        all_ok = checked["verified"] and llm_ok and not invalid
        update: dict[str, Any] = {
            "invalid_citations": invalid,
            "verification": checked,
            "audit": audit_d,
            "verified": all_ok,
            "steps": [_step("Auditor", "claim_audit",
                            {"answer": state["answer"][:200]},
                            {"deterministic": checked["verified"], "llm": llm_ok,
                             "problems": problems})],
        }
        if not all_ok:
            if state.get("retries_left", 0) > 0:
                update["feedback"] = "; ".join(problems) or "audit failed"
                update["retries_left"] = state.get("retries_left", 0) - 1
            else:
                update["refused"] = True
                update["refusal_reason"] = f"audit failed: {'; '.join(problems) or 'unverified claims'}"
                update["verified"] = False
        return update

    def route_after_audit(state: OrchestratorState) -> str:
        if state.get("refused"):
            return END
        if state.get("verified"):
            return END
        if state.get("feedback"):
            return "synthesize"
        return END

    workflow = StateGraph(OrchestratorState)
    workflow.add_node("plan", plan_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("audit", audit_node)

    workflow.set_entry_point("plan")
    workflow.add_edge("plan", "retrieve")
    workflow.add_edge("retrieve", "analyze")
    workflow.add_edge("analyze", "synthesize")
    workflow.add_edge("synthesize", "audit")
    workflow.add_conditional_edges("audit", route_after_audit,
                                   {"synthesize": "synthesize", END: END})
    return workflow


class MultiAgentOrchestrator:
    """LangGraph multi-agent pipeline with real usage accounting."""

    def __init__(self, cfg: dict[str, Any],
                 memory: SessionMemoryManager | None = None) -> None:
        self.cfg = cfg
        self.memory = memory
        self.workflow = build_workflow().compile()

    def run(self, query: str, index: Index, strategy: str = "agent_react") -> dict[str, Any]:
        from ..graph import load_graph_engine

        t0 = time.perf_counter()
        session_id = f"sess_{uuid.uuid4().hex[:12]}"

        initial_state: OrchestratorState = {
            "session_id": session_id,
            "query": query,
            "index": index,
            "cfg": self.cfg,
            "graph_engine": load_graph_engine(self.cfg, index),
            "plan": {},
            "hits": [],
            "math_result": None,
            "answer": None,
            "citations": [],
            "invalid_citations": [],
            "feedback": None,
            "audit": None,
            "verification": {"verified": False, "claims": []},
            "verified": False,
            "refused": False,
            "refusal_reason": None,
            "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0},
            "retries_left": self.cfg.get("generation", {}).get("verify_retries", 1),
            "steps": [],
        }

        final_state = self.workflow.invoke(initial_state)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        steps = final_state.get("steps", [])
        if self.memory is not None:
            for i, s in enumerate(steps, start=1):
                payload = {"input": s.get("input"), "output": s.get("output")}
                self.memory.log_step(session_id, i, s["agent"], s["action"], payload)
            self.memory.save_session(
                session_id=session_id,
                query=query,
                final_answer=final_state.get("answer") or "",
                verified=final_state.get("verified", False),
                strategy=strategy,
                cost_usd=final_state.get("usage", {}).get("cost_usd", 0.0),
                latency_ms=latency_ms,
            )

        return {
            "session_id": session_id,
            "refused": final_state.get("refused", False),
            "refusal_reason": final_state.get("refusal_reason"),
            "answer": final_state.get("answer") if not final_state.get("refused") else None,
            "citations": final_state.get("citations", []) if not final_state.get("refused") else [],
            "invalid_citations": final_state.get("invalid_citations", []),
            "verified": bool(final_state.get("verified", False) and not final_state.get("refused", False)),
            "verification": final_state.get("verification", {}),
            "audit": final_state.get("audit"),
            "confidence": confidence(final_state.get("hits", [])),
            "hits": final_state.get("hits", []),
            "math_result": final_state.get("math_result"),
            "plan": final_state.get("plan", {}),
            "usage": final_state.get("usage", {}),
            "latency_ms": latency_ms,
            "agent_history": steps,
        }
