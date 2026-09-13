"""Tests for the real agent core: planner, tool loop, researcher, synthesis, auditor.

All LLM calls are mocked at the module boundary — these tests pin the agent
logic: filter validation against the corpus inventory, tool-loop execution
and usage accounting, filtered-retry behavior, and usage aggregation.
"""

from __future__ import annotations

from ragfilings.agents import auditor as auditor_mod
from ragfilings.agents import planner as planner_mod
from ragfilings.agents import synthesis as synthesis_mod
from ragfilings.schemas import AuditResult, QueryPlan, SynthesizedAnswer

CFG = {
    "generation": {"model": "test/gen", "max_tokens": 512, "verify_retries": 1},
    "extraction": {"model": "test/extract"},
    "retrieval": {"strategy": "hybrid", "top_k": 8, "rerank_candidates": 25},
    "verification": {"min_confidence": 0.35},
}

CHUNK_AAPL = {
    "id": "AAPL_2025_10K:Item8:c007",
    "ticker": "AAPL",
    "fiscal_year": 2025,
    "item": "8",
    "title": "Financials",
    "text": "Total net sales | $416,161 | $391,035",
}
CHUNK_MSFT = {
    "id": "MSFT_2025_10K:Item8:c003",
    "ticker": "MSFT",
    "fiscal_year": 2025,
    "item": "8",
    "title": "Financials",
    "text": "Total revenue | $281,724 million",
}


class FakeIndex:
    """Returns hits only when filters match, to exercise filter plumbing."""

    def __init__(self, chunks, extra_chunks=()):
        self.chunks = list(chunks) + list(extra_chunks)
        self.calls = []

    def search(
        self, query, strategy, top_k, reranker_name=None, filters=None, rerank_candidates=25
    ):
        self.calls.append({"query": query, "filters": filters})
        out = self.chunks
        if filters:
            for k, v in filters.items():
                out = [c for c in out if str(c.get(k)) == str(v)]
        return [{"chunk": c, "score": 0.9, "dense_sim": 0.8} for c in out]


# ---------------------------------------------------------------- planner


def test_corpus_inventory_lists_distinct_filings():
    inv = planner_mod.corpus_inventory([CHUNK_AAPL, CHUNK_MSFT, CHUNK_AAPL])
    assert inv == ["AAPL FY2025", "MSFT FY2025"]


def test_planner_drops_filters_not_in_corpus(monkeypatch):
    def fake_structured(messages, response_model, cfg, role="generation", **kw):
        return QueryPlan(
            intent="lookup",
            ticker="ZZZZ",
            fiscal_year=1999,
            sub_questions=["net sales?"],
            needs_math=False,
            reasoning="x",
        ), {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.001, "calls": 1}

    monkeypatch.setattr(planner_mod, "complete_structured", fake_structured)
    plan, usage = planner_mod.plan_query("ZZZZ revenue 1999?", CFG, [CHUNK_AAPL, CHUNK_MSFT])
    assert plan.ticker is None  # ZZZZ not in corpus -> dropped
    assert plan.fiscal_year is None  # 1999 not in corpus -> dropped
    assert usage["input_tokens"] == 10


def test_planner_keeps_valid_filters_and_defaults_subquestions(monkeypatch):
    def fake_structured(messages, response_model, cfg, role="generation", **kw):
        return QueryPlan(
            intent="lookup", ticker="aapl", fiscal_year=2025, sub_questions=[], needs_math=False
        ), {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0, "calls": 1}

    monkeypatch.setattr(planner_mod, "complete_structured", fake_structured)
    plan, _ = planner_mod.plan_query("Apple net sales?", CFG, [CHUNK_AAPL])
    assert plan.ticker == "AAPL"  # validated against inventory and normalized
    assert plan.sub_questions == ["Apple net sales?"]


# -------------------------------------------------------- synthesis/auditor


def test_synthesize_passes_feedback_and_aggregates_usage(monkeypatch):
    seen = {}

    def fake_structured(messages, response_model, cfg, role="generation", **kw):
        seen["messages"] = messages
        seen["role"] = role
        return SynthesizedAnswer(
            answer="$416,161 million", citations=["AAPL_2025_10K:Item8:c007"]
        ), {"input_tokens": 50, "output_tokens": 30, "cost_usd": 0.004, "calls": 1}

    monkeypatch.setattr(synthesis_mod, "complete_structured", fake_structured)
    usage = {"input_tokens": 5, "output_tokens": 5, "cost_usd": 0.001, "calls": 1}
    inst = synthesis_mod.synthesize(
        "net sales?",
        [{"chunk": CHUNK_AAPL, "score": 0.9, "dense_sim": 0.8}],
        CFG,
        usage,
        feedback="figures not found: $999",
    )
    assert inst.answer == "$416,161 million"
    assert "AUDITOR FEEDBACK" in seen["messages"][-1]["content"]
    assert seen["role"] == "generation"
    assert usage == {"input_tokens": 55, "output_tokens": 35, "cost_usd": 0.005, "calls": 2}


def test_audit_answer_flags_nonexistent_citations(monkeypatch):
    def fake_structured(messages, response_model, cfg, role="generation", **kw):
        return AuditResult(verified=True, refuse=False, audit_claims=[]), {
            "input_tokens": 10,
            "output_tokens": 5,
            "cost_usd": 0.001,
            "calls": 1,
        }

    monkeypatch.setattr(auditor_mod, "complete_structured", fake_structured)
    seen = {}

    def spy(messages, response_model, cfg, role="generation", **kw):
        seen["user"] = messages[-1]["content"]
        return fake_structured(messages, response_model, cfg, role=role, **kw)

    monkeypatch.setattr(auditor_mod, "complete_structured", spy)
    usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
    res = auditor_mod.audit_answer(
        "net sales?",
        "$416,161 million",
        ["AAPL_2025_10K:Item8:c007", "GHOST:c999"],
        [{"chunk": CHUNK_AAPL, "score": 0.9, "dense_sim": 0.8}],
        CFG,
        usage,
    )
    assert res.verified is True
    assert "GHOST:c999" in seen["user"]
    assert usage["cost_usd"] == 0.001


def test_orchestrator_audit_exhaustion_marks_refused_and_unverified(monkeypatch):
    from ragfilings.pipeline.orchestrator import MultiAgentOrchestrator
    from ragfilings.schemas import AuditClaim, AuditResult, SynthesizedAnswer

    monkeypatch.setattr(
        "ragfilings.pipeline.orchestrator.plan_query",
        lambda *args, **kwargs: (QueryPlan(intent="lookup", ticker="AAPL"), {"calls": 1}),
    )
    monkeypatch.setattr(
        "ragfilings.pipeline.orchestrator.synthesize",
        lambda *args, **kwargs: SynthesizedAnswer(
            answer="$999B fake revenue", citations=["AAPL_2025_10K:Item8:c007"]
        ),
    )
    monkeypatch.setattr(
        "ragfilings.pipeline.orchestrator.audit_answer",
        lambda *args, **kwargs: AuditResult(
            verified=False, audit_claims=[AuditClaim(figure="999B", status="UNVERIFIED")]
        ),
    )

    orch = MultiAgentOrchestrator({**CFG, "generation": {"verify_retries": 0}})
    res = orch.run("what was sales?", FakeIndex([CHUNK_AAPL]))
    assert res["verified"] is False
    assert res["refused"] is True
    assert res["answer"] is None
    assert "audit failed" in res["refusal_reason"].lower()
