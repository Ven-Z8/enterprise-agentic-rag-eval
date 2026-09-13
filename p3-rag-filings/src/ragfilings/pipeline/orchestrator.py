"""Multi-agent LangGraph orchestrator over the generic RAG pipeline.

Graph topology:

    plan ─▶ retrieve ─▶ analyze ─▶ synthesize ─▶ audit ─▶ END
                                       ▲            │
                                       └── retry ───┘   (bounded, on audit failure)

Every node is a real step:
- plan: structured query planning via Instructor / Pydantic (QueryPlan)
- retrieve: deterministic multi-query hybrid_rerank (BM25 + dense + CrossEncoder) (0 LLM tokens)
- analyze: deterministic safe-eval mathematical computation (0 LLM tokens)
- synthesize: grounded structured synthesis via Instructor / Pydantic (SynthesisResponse)
- audit: deterministic claim checking + LLM auditor guard (AuditResult)
- retries: bounded loop back to synthesize if audit fails
"""

from __future__ import annotations

import logging
import operator
import time
import uuid
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from ..agents.auditor import audit_answer
from ..agents.planner import plan_query
from ..agents.synthesis import synthesize
from ..domains import get_pack
from ..domains.financial.math_tool import compute_financial_math
from ..domains.financial.query_decompose import needs_decomposition
from ..domains.financial.verification import verify
from ..retrieval import Index, confidence
from ..schemas import QueryPlan
from .engine import split_graph_strategy
from .memory import SessionMemoryManager

logger = logging.getLogger(__name__)


class OrchestratorState(TypedDict, total=False):
    session_id: str
    query: str
    index: Any
    cfg: dict[str, Any]
    domain: str
    pack: Any
    strategy: str
    filters: dict[str, Any] | None
    top_k: int | None
    graph_engine: Any
    graph_block: str | None
    derived_values: list[float]
    plan: dict[str, Any]
    hits: list[dict[str, Any]]
    math_result: dict[str, Any] | None
    answer: str | None
    citations: list[str]
    invalid_citations: list[str]
    feedback: str | None
    audit: dict[str, Any] | None
    verification: dict[str, Any]
    verified: bool
    refused: bool
    refusal_reason: str | None
    usage: dict[str, Any]
    retries_left: int
    steps: Annotated[list[dict[str, Any]], operator.add]


def _step(agent: str, action: str, input_payload: Any, output_payload: Any) -> dict[str, Any]:
    return {"agent": agent, "action": action, "input": input_payload, "output": output_payload}


def _merge_usage(state: OrchestratorState, u: dict[str, Any] | None) -> None:
    if u is None:
        return
    acc = state["usage"]
    acc["input_tokens"] += u.get("input_tokens", 0)
    acc["output_tokens"] += u.get("output_tokens", 0)
    acc["cost_usd"] += u.get("cost_usd", 0.0)
    acc["calls"] += u.get("calls", 1)


def build_workflow() -> StateGraph:
    def plan_node(state: OrchestratorState) -> dict[str, Any]:
        graph_rescue = state.get("graph_engine")
        pack = state.get("pack")

        # 1. Deterministic clarification upfront for ambiguous queries
        if graph_rescue and hasattr(graph_rescue, "clarification"):
            clarification = graph_rescue.clarification(state["query"])
            if clarification is not None:
                return {
                    "answer": clarification,
                    "refused": False,
                    "verified": True,
                    "citations": [],
                    "steps": [
                        _step("Planner", "clarification", {"query": state["query"]}, clarification)
                    ],
                }

        # 2. Fast-path deterministic plan for clean-scope queries
        if graph_rescue and hasattr(graph_rescue, "extract_queries"):
            rqs = graph_rescue.extract_queries(state["query"])
            if rqs:
                tickers = list(dict.fromkeys(r.ticker for r in rqs))
                years = list(dict.fromkeys(r.fiscal_year for r in rqs))
                plan_d = {
                    "intent": "synthesis" if len(rqs) > 1 else "lookup",
                    "ticker": tickers[0] if len(tickers) == 1 else None,
                    "fiscal_year": years[0] if len(years) == 1 else None,
                    "sub_questions": [state["query"]],
                    "needs_math": False,
                    "reasoning": f"deterministic scope extraction: {tickers} FY{years}",
                }
                return {
                    "plan": plan_d,
                    "steps": [_step("Planner", "fast_path_plan", {"query": state["query"]}, plan_d)],
                }

        # 2b. Fast-path deterministic plan for legal contract queries
        if graph_rescue and hasattr(graph_rescue, "find_contracts"):
            contracts = graph_rescue.find_contracts(state["query"])
            if contracts:
                plan_d = {
                    "intent": "synthesis" if len(contracts) > 1 else "lookup",
                    "ticker": None,
                    "fiscal_year": None,
                    "sub_questions": [state["query"]],
                    "needs_math": False,
                    "reasoning": f"deterministic contract scope: {contracts}",
                }
                return {
                    "plan": plan_d,
                    "steps": [_step("Planner", "fast_path_plan", {"query": state["query"]}, plan_d)],
                }

        # 2c. Fast-path deterministic plan for biomedical queries
        if state.get("domain") == "biomedical" or getattr(pack, "name", None) == "biomedical":
            sub_qs = pack.decompose_query(state["query"], state["cfg"]) if pack else [state["query"]]
            plan_d = {
                "intent": "synthesis",
                "ticker": None,
                "fiscal_year": None,
                "sub_questions": sub_qs,
                "needs_math": False,
                "reasoning": "deterministic biomedical literature retrieval",
            }
            return {
                "plan": plan_d,
                "steps": [_step("Planner", "fast_path_plan", {"query": state["query"]}, plan_d)],
            }

        # 3. Fallback to Instructor LLM query planning
        plan_prompt = (
            pack.get_phase_instructions("planning")
            if hasattr(pack, "get_phase_instructions")
            else None
        )
        chunks = getattr(state["index"], "chunks", [])
        plan, usage = plan_query(
            state["query"],
            state["cfg"],
            chunks,
            system_prompt=plan_prompt,
        )
        _merge_usage(state, usage)
        plan_d = plan.model_dump()
        return {
            "plan": plan_d,
            "steps": [_step("Planner", "plan_query", {"query": state["query"]}, plan_d)],
        }

    def retrieve_node(state: OrchestratorState) -> dict[str, Any]:
        plan = QueryPlan(**state["plan"])
        if plan.intent == "not_in_corpus" and not plan.sub_questions:
            return {
                "refused": True,
                "refusal_reason": f"planner: question outside corpus scope ({plan.reasoning})",
                "steps": [_step("Researcher", "skipped", {}, "out-of-corpus plan")],
            }

        strat = state.get("strategy") or state["cfg"].get("retrieval", {}).get(
            "strategy", "hybrid_rerank"
        )
        base_strat, use_graph = split_graph_strategy(strat)

        # Deterministic multi-query hybrid_rerank (0 LLM tokens, maximum speed & recall)
        sub_queries = plan.sub_questions or [state["query"]]
        top_k = state.get("top_k") or state["cfg"].get("retrieval", {}).get("top_k", 8)
        rerank_candidates = state["cfg"].get("retrieval", {}).get("rerank_candidates", 25)
        reranker_name = state["cfg"].get("retrieval", {}).get("reranker")

        filters = dict(state.get("filters") or {})
        inventory = {str(c.get("ticker")) for c in getattr(state["index"], "chunks", []) if c.get("ticker")}
        if plan.ticker and str(plan.ticker).upper() in inventory and "ticker" not in filters:
            filters["ticker"] = str(plan.ticker).upper()
        if plan.fiscal_year and "fiscal_year" not in filters:
            filters["fiscal_year"] = plan.fiscal_year

        all_hits: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for sq in sub_queries:
            sq_hits = state["index"].search(
                sq,
                base_strat,
                top_k,
                filters=filters or None,
                rerank_candidates=rerank_candidates,
                reranker_name=reranker_name,
            )
            if not sq_hits and filters:
                sq_hits = state["index"].search(
                    sq,
                    base_strat,
                    top_k,
                    rerank_candidates=rerank_candidates,
                    reranker_name=reranker_name,
                )
            for h in sq_hits:
                cid = h["chunk"]["id"]
                if cid not in seen_ids:
                    all_hits.append(h)
                    seen_ids.add(cid)

        hits = sorted(all_hits, key=lambda x: x["score"], reverse=True)[:top_k]
        events = [{"tool": "hybrid_rerank", "sub_queries": sub_queries}]
        notes = f"Retrieved {len(hits)} chunks via {strat}"

        # Augment with graph engine if available
        graph_rescue = state.get("graph_engine")
        graph_block = None
        derived_values: list[float] = []
        if graph_rescue and hasattr(graph_rescue, "rescue") and use_graph:
            outcome = graph_rescue.rescue(state["query"])
            if outcome is not None:
                seen = {h["chunk"]["id"]: h for h in hits}
                outcome_chunks = getattr(outcome, "chunks", [])
                if outcome_chunks:
                    for c in outcome_chunks:
                        cid = c.get("id")
                        if cid and cid not in seen:
                            hits.append({"chunk": c, "score": 1.0, "dense_sim": 1.0})
                            seen[cid] = hits[-1]
                else:
                    for cid in getattr(outcome, "chunk_ids", []):
                        if cid not in seen:
                            c = next((ch for ch in getattr(state["index"], "chunks", []) if ch.get("id") == cid), None)
                            if c:
                                hits.append({"chunk": c, "score": 1.0, "dense_sim": 1.0})
                                seen[cid] = hits[-1]
                graph_block = getattr(outcome, "facts_block", None)
                derived_values = list(getattr(outcome, "derived_values", []) or [])

        conf = confidence(hits)
        min_conf = state["cfg"].get("verification", {}).get("min_confidence", 0.35)
        update: dict[str, Any] = {
            "hits": hits,
            "graph_block": graph_block,
            "derived_values": derived_values,
            "steps": [
                _step(
                    "Researcher",
                    "hybrid_rerank",
                    {
                        "sub_questions": plan.sub_questions,
                        "ticker": plan.ticker,
                        "fiscal_year": plan.fiscal_year,
                    },
                    {
                        "n_hits": len(hits),
                        "confidence": round(conf, 4),
                        "tool_calls": events,
                        "notes": notes,
                    },
                )
            ],
        }
        pack = state.get("pack")
        if not hits or conf < min_conf:
            tool_res = pack.compute(state["query"], [], state["cfg"]) if pack and hasattr(pack, "compute") else None
            if tool_res:
                update["math_result"] = tool_res
                update["refused"] = False
            else:
                reason = (
                    "no retrieval hits"
                    if not hits
                    else f"low retrieval confidence: {conf:.3f} < {min_conf}"
                )
                update.update({"refused": True, "refusal_reason": reason})
        return update

    def analyze_node(state: OrchestratorState) -> dict[str, Any]:
        if state.get("math_result"):
            return {"steps": [_step("DataAnalyst", "tool_result_preserved", {}, state["math_result"])]}

        plan = state.get("plan", {})
        pack = state.get("pack")
        needs_math_fn = (
            getattr(pack, "needs_decomposition", needs_decomposition)
            if pack
            else needs_decomposition
        )
        needs_math = bool(plan.get("needs_math")) or needs_math_fn(state["query"])
        chunks = [h["chunk"] for h in state.get("hits", [])]

        compute_fn = (
            getattr(pack, "compute", None)
            or getattr(pack, "compute_math", None)
            or compute_financial_math
        )
        math_res = compute_fn(state["query"], chunks, state["cfg"]) if (needs_math or hasattr(pack, "compute")) else None
        if not math_res and (not needs_math or not chunks):
            return {"steps": [_step("DataAnalyst", "skipped", {}, "no computation needed")]}

        derived = list(state.get("derived_values", []))
        if math_res:
            _merge_usage(state, math_res.pop("usage", {}))
            for k in ("result_value", "raw_value"):
                if k in math_res:
                    try:
                        derived.append(float(math_res[k]))
                    except (ValueError, TypeError):
                        pass
        return {
            "math_result": math_res,
            "derived_values": derived,
            "steps": [
                _step(
                    "DataAnalyst",
                    "safe_eval_math",
                    {"query": state["query"]},
                    math_res or {"calculated": False},
                )
            ],
        }

    def synthesize_node(state: OrchestratorState) -> dict[str, Any]:
        pack = state.get("pack")
        synthesis_prompt = (
            pack.get_phase_instructions("synthesis")
            if hasattr(pack, "get_phase_instructions")
            else None
        )
        instance = synthesize(
            state["query"],
            state["hits"],
            state["cfg"],
            state["usage"],
            math_result=state.get("math_result"),
            feedback=state.get("feedback"),
            system_prompt=synthesis_prompt,
            graph_block=state.get("graph_block"),
        )
        is_refusal = (
            instance.status == "refused"
            or not instance.answer
            or "<exact" in str(instance.answer).lower()
        )
        return {
            "answer": instance.answer if not is_refusal else None,
            "citations": instance.citations if not is_refusal else [],
            "refused": is_refusal,
            "refusal_reason": instance.reason if is_refusal else None,
            "feedback": None,
            "steps": [
                _step(
                    "Synthesizer",
                    "grounded_synthesis",
                    {
                        "n_context": len(state["hits"]),
                        "retry_feedback": bool(state.get("feedback")),
                    },
                    {"answer_len": len(instance.answer or ""), "citations": instance.citations},
                )
            ],
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

        pack = state.get("pack")
        by_id = {h["chunk"]["id"]: h["chunk"] for h in state["hits"]}
        citations = [c for c in state.get("citations", []) if isinstance(c, str)]
        valid = [c for c in citations if c in by_id]
        invalid = [c for c in citations if c not in by_id]
        cited_chunks = [by_id[c] for c in valid] or [h["chunk"] for h in state["hits"]]
        if not cited_chunks and state.get("math_result"):
            cited_chunks = [{"id": "TOOL", "text": state["math_result"].get("formatted", "")}]

        verify_fn = getattr(pack, "verify", verify) if pack else verify
        derived_vals = state.get("derived_values", [])
        checked = verify_fn(
            str(state["answer"]),
            cited_chunks,
            math_result=state.get("math_result"),
            derived_values=derived_vals,
            query=state["query"],
        )

        # Fast audit: if deterministic check is 100% verified and citations are valid,
        # skip redundant LLM auditor overhead on verified facts
        has_graph = bool(state.get("graph_block"))
        det_ok = checked.get("verified", False) and not invalid
        skip_llm_audit = det_ok and (
            has_graph or state["cfg"].get("verification", {}).get("fast_audit", True)
        )

        if skip_llm_audit:
            llm_ok = True
            audit_d = {"verified": True, "refuse": False, "audit_claims": []}
            problems: list[str] = []
        else:
            audit_prompt = (
                pack.get_phase_instructions("auditor")
                if hasattr(pack, "get_phase_instructions")
                else None
            )
            audit_res = audit_answer(
                state["query"],
                str(state["answer"]),
                citations,
                state["hits"],
                state["cfg"],
                state["usage"],
                math_result=state.get("math_result"),
                system_prompt=audit_prompt,
            )
            audit_d = audit_res.model_dump()
            llm_ok = bool(audit_d.get("verified")) and not audit_d.get("refuse")

            problems = []
            if not checked.get("verified", False):
                failed = [c["raw"] for c in checked.get("claims", []) if not c.get("found")]
                if failed:
                    problems.append(f"figures not found in cited chunks: {', '.join(failed)}")
            if invalid:
                problems.append(f"nonexistent citation ids: {', '.join(invalid)}")
            for claim in audit_d.get("audit_claims", []):
                if claim.get("status") == "UNVERIFIED":
                    problems.append(f"auditor: {claim.get('figure')} unverified")
            if audit_d.get("refuse"):
                problems.append("auditor: context too thin to answer")

        all_ok = checked.get("verified", False) and llm_ok and not invalid
        update: dict[str, Any] = {
            "invalid_citations": invalid,
            "verification": checked,
            "audit": audit_d,
            "verified": all_ok,
            "steps": [
                _step(
                    "Auditor",
                    "claim_audit",
                    {"answer": state["answer"][:200]},
                    {
                        "deterministic": checked.get("verified", False),
                        "llm": llm_ok,
                        "fast_path": skip_llm_audit,
                        "problems": problems,
                    },
                )
            ],
        }
        if not all_ok:
            if state.get("retries_left", 0) > 0:
                update["feedback"] = "; ".join(problems) or "audit failed"
                update["retries_left"] = state.get("retries_left", 0) - 1
            else:
                update["refused"] = True
                update["refusal_reason"] = (
                    f"audit failed: {'; '.join(problems) or 'unverified claims'}"
                )
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

    def route_after_plan(state: OrchestratorState) -> str:
        if state.get("refused") or state.get("answer"):
            return END
        return "retrieve"

    def route_after_retrieve(state: OrchestratorState) -> str:
        return END if state.get("refused") else "analyze"

    workflow = StateGraph(OrchestratorState)
    workflow.add_node("plan", plan_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.add_node("audit", audit_node)

    workflow.set_entry_point("plan")
    workflow.add_conditional_edges(
        "plan", route_after_plan, {"retrieve": "retrieve", END: END}
    )
    workflow.add_conditional_edges(
        "retrieve", route_after_retrieve, {"analyze": "analyze", END: END}
    )
    workflow.add_edge("analyze", "synthesize")
    workflow.add_edge("synthesize", "audit")
    workflow.add_conditional_edges(
        "audit", route_after_audit, {"synthesize": "synthesize", END: END}
    )
    return workflow


class MultiAgentOrchestrator:
    """LangGraph multi-agent pipeline with real usage accounting."""

    def __init__(self, cfg: dict[str, Any], memory: SessionMemoryManager | None = None) -> None:
        self.cfg = cfg
        self.memory = memory
        self.workflow = build_workflow().compile()

    def run(
        self,
        query: str,
        index: Index,
        strategy: str = "hybrid_rerank",
        domain: str = "financial",
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        pack = get_pack(domain)

        t0 = time.perf_counter()
        session_id = f"sess_{uuid.uuid4().hex[:12]}"

        base_strat, use_graph = split_graph_strategy(strategy)
        graph_engine = None
        if use_graph and hasattr(pack, "load_rescue"):
            try:
                graph_engine = pack.load_rescue(self.cfg, index)
            except Exception:
                pass

        initial_state: OrchestratorState = {
            "session_id": session_id,
            "query": query,
            "index": index,
            "cfg": self.cfg,
            "domain": domain,
            "pack": pack,
            "strategy": strategy,
            "filters": filters,
            "top_k": top_k,
            "graph_engine": graph_engine,
            "graph_block": None,
            "derived_values": [],
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
            "verified": bool(
                final_state.get("verified", False) and not final_state.get("refused", False)
            ),
            "verification": final_state.get("verification", {}),
            "audit": final_state.get("audit"),
            "confidence": confidence(final_state.get("hits", [])),
            "hits": final_state.get("hits", []),
            "math_result": final_state.get("math_result"),
            "plan": final_state.get("plan", {}),
            "usage": final_state.get("usage", {}),
            "latency_ms": latency_ms,
            "agent_history": steps,
            "strategy": strategy,
        }
