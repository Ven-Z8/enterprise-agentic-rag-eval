"""Generation: confidence-gated refusal, grounded JSON answers, verify-retry.

The OpenRouter call site (generation._complete) is mocked — these tests pin
the pipeline logic around it: the gate must refuse BEFORE any model call, a
planted wrong number must trigger exactly one corrective retry, and a
still-wrong number must ship flagged, not silently.
"""

import json

import pytest

from ragfilings.pipeline import engine as generation

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


def _reply(answer, citations=("AAPL_2025_10K:Item8:c007",), reason=None):
    return json.dumps({"answer": answer, "citations": list(citations), "reason": reason})


class MockComplete:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, messages, cfg, model=None, client=None):
        self.calls.append(messages)
        return self.replies.pop(0), {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001}


def test_low_confidence_refuses_without_model_call(monkeypatch):
    mock = MockComplete([])
    monkeypatch.setattr(generation, "_complete", mock)
    result = generation.answer("What was X?", _hits(sim=0.10), CFG)
    assert result["refused"] and "confidence" in result["refusal_reason"]
    assert result["answer"] is None and not mock.calls
    assert result["usage"]["calls"] == 0


def test_grounded_answer_with_verified_claims(monkeypatch):
    mock = MockComplete([_reply("Net sales were $416,161 million.")])
    monkeypatch.setattr(generation, "_complete", mock)
    result = generation.answer("Total net sales?", _hits(), CFG)
    assert not result["refused"]
    assert result["citations"] == ["AAPL_2025_10K:Item8:c007"]
    assert result["verification"]["verified"]
    assert result["usage"] == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cost_usd": 0.001,
        "calls": 1,
    }


def test_planted_wrong_number_triggers_one_corrective_retry(monkeypatch):
    mock = MockComplete(
        [_reply("Net sales were $999,999 million."), _reply("Net sales were $416,161 million.")]
    )
    monkeypatch.setattr(generation, "_complete", mock)
    result = generation.answer("Total net sales?", _hits(), CFG)
    assert len(mock.calls) == 2
    assert "999,999" in str(mock.calls[1])  # retry names the failed claim
    assert result["verification"]["verified"]
    assert "$416,161" in result["answer"]
    assert result["usage"]["calls"] == 2


def test_persistently_wrong_number_ships_flagged(monkeypatch):
    mock = MockComplete(
        [_reply("Sales were $999,999 million."), _reply("Sales were $999,999 million.")]
    )
    monkeypatch.setattr(generation, "_complete", mock)
    result = generation.answer("Total net sales?", _hits(), CFG)
    assert not result["refused"]  # flagged, not suppressed
    assert not result["verification"]["verified"]
    assert len(mock.calls) == 2  # retries capped by config


def test_tolerates_prose_around_json_and_model_refusal(monkeypatch):
    mock = MockComplete(
        ["Here you go:\n" + _reply(None, citations=(), reason="not in the provided context")]
    )
    monkeypatch.setattr(generation, "_complete", mock)
    result = generation.answer("CEO's shoe size?", _hits(), CFG)
    assert result["refused"] and "context" in result["refusal_reason"]


def test_invented_citation_ids_are_flagged_and_excluded_from_verification(monkeypatch):
    mock = MockComplete(
        [
            _reply(
                "Net sales were $416,161 million.",
                citations=("AAPL_2025_10K:Item8:c007", "FAKE_ID:c999"),
            )
        ]
    )
    monkeypatch.setattr(generation, "_complete", mock)
    result = generation.answer("Total net sales?", _hits(), CFG)
    assert result["invalid_citations"] == ["FAKE_ID:c999"]
    assert result["citations"] == ["AAPL_2025_10K:Item8:c007"]
    assert result["verification"]["verified"]


def test_unparseable_reply_gets_one_reformat_attempt_then_errors(monkeypatch):
    mock = MockComplete(["no json here", "still no json"])
    monkeypatch.setattr(generation, "_complete", mock)
    with pytest.raises(generation.GenerationError):
        generation.answer("Q?", _hits(), CFG)
    assert len(mock.calls) == 2
