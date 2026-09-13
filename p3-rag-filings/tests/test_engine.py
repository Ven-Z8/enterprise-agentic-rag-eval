"""Tests for Pipeline Engine."""

import json

from ragfilings.llm.base import BaseLLMClient
from ragfilings.llm.types import LLMResponse, TokenUsage
from ragfilings.pipeline.engine import _parse_json, answer

CFG = {
    "generation": {"model": "test/model", "max_tokens": 512, "verify_retries": 1},
    "verification": {"min_confidence": 0.35},
}

CHUNK = {
    "id": "AAPL_2025_10K:Item8:c007",
    "text": "Total net sales | $416,161 | $391,035",
}


def _hits(sim=0.8):
    return [{"chunk": CHUNK, "score": sim, "dense_sim": sim}]


def _reply(ans, citations=("AAPL_2025_10K:Item8:c007",), reason=None):
    return json.dumps({"answer": ans, "citations": list(citations), "reason": reason})


class MockLLMClient(BaseLLMClient):
    def __init__(self, replies):
        super().__init__()
        self.replies = list(replies)
        self.calls = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def complete(self, messages, model=None, max_tokens=1200, temperature=0.0, **kwargs):
        self.calls.append(messages)
        text = self.replies.pop(0)
        return LLMResponse(
            content=text,
            usage=TokenUsage(input_tokens=100, output_tokens=20, cost_usd=0.001),
            model="mock-model",
        )


def test_parse_json_variations():
    assert _parse_json('{"answer": "42"}') == {"answer": "42"}
    assert _parse_json('Here is output:\n```json\n{"answer": "42"}\n```') == {"answer": "42"}
    assert _parse_json("invalid plain text") is None


def test_engine_answer_grounded():
    client = MockLLMClient([_reply("Net sales were $416,161 million.")])
    res = answer("Total net sales?", _hits(), CFG, client=client)
    assert not res["refused"]
    assert res["citations"] == ["AAPL_2025_10K:Item8:c007"]
    assert res["verification"]["verified"]
    assert res["usage"]["calls"] == 1


def test_engine_answer_low_confidence_refuses():
    client = MockLLMClient([])
    res = answer("Question?", _hits(sim=0.1), CFG, client=client)
    assert res["refused"]
    assert "low retrieval confidence" in res["refusal_reason"]
    assert not client.calls


def test_multi_agent_orchestrator_grounded_flow(monkeypatch):
    from ragfilings.pipeline.orchestrator import MultiAgentOrchestrator
    from ragfilings.schemas import QueryPlan, SynthesisResponse, AuditResult, AuditClaim

    # Mock planner
    def mock_plan(*args, **kwargs):
        return QueryPlan(
            intent="lookup",
            ticker="AAPL",
            fiscal_year=2025,
            sub_questions=["What was Apple net sales in FY2025?"],
            needs_math=False,
            reasoning="Apple net sales lookup",
        ), {"input_tokens": 50, "output_tokens": 20, "cost_usd": 0.0001}

    # Mock synthesize
    def mock_synth(*args, **kwargs):
        return SynthesisResponse(
            status="answered",
            answer="Apple's total net sales in FY2025 were $416,161 million.",
            citations=["AAPL_2025_10K:Item8:c007"],
            reason=None,
        )

    # Mock audit
    def mock_audit(*args, **kwargs):
        return AuditResult(
            verified=True,
            refuse=False,
            audit_claims=[
                AuditClaim(figure="$416,161", found_in_chunk="AAPL_2025_10K:Item8:c007", status="VERIFIED")
            ],
        )

    from ragfilings.pipeline import orchestrator
    monkeypatch.setattr(orchestrator, "plan_query", mock_plan)
    monkeypatch.setattr(orchestrator, "synthesize", mock_synth)
    monkeypatch.setattr(orchestrator, "audit_answer", mock_audit)

    class MockIndex:
        def __init__(self):
            self.chunks = [CHUNK]
        def search(self, *args, **kwargs):
            return [{"chunk": CHUNK, "score": 0.95, "dense_sim": 0.95}]

    orch = MultiAgentOrchestrator(CFG)
    res = orch.run("What was Apple's total net sales in FY2025?", MockIndex())

    assert not res["refused"]
    assert res["verified"]
    assert res["answer"] == "Apple's total net sales in FY2025 were $416,161 million."
    assert res["citations"] == ["AAPL_2025_10K:Item8:c007"]
    assert len(res["agent_history"]) >= 4  # plan, retrieve, synthesize, audit


def test_multi_agent_orchestrator_early_exit_out_of_corpus(monkeypatch):
    from ragfilings.pipeline.orchestrator import MultiAgentOrchestrator
    from ragfilings.schemas import QueryPlan

    def mock_plan(*args, **kwargs):
        return QueryPlan(
            intent="not_in_corpus",
            ticker="XYZ",
            fiscal_year=2015,
            sub_questions=[],
            needs_math=False,
            reasoning="Company XYZ is not in corpus",
        ), {"input_tokens": 30, "output_tokens": 10, "cost_usd": 0.00005}

    from ragfilings.pipeline import orchestrator
    monkeypatch.setattr(orchestrator, "plan_query", mock_plan)

    class MockIndex:
        def __init__(self):
            self.chunks = [CHUNK]
        def search(self, *args, **kwargs):
            return []

    orch = MultiAgentOrchestrator(CFG)
    res = orch.run("What was XYZ's revenue in 2015?", MockIndex())

    assert res["refused"]
    assert "outside corpus scope" in res["refusal_reason"]
    assert res["answer"] is None
