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
