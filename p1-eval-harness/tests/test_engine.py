"""Scoring engine: the numbers in the scorecards come from this logic, so every
scoring rule gets pinned — tolerance math, unit equivalence, the
refusal/unanswerable matrix, citation prefix matching, schema enforcement on
load, and byte-level compatibility with the standard Trace format."""

import json
from pathlib import Path

import pytest

from harness.metrics import engine
from harness.traces.build import build_trace
from harness.traces import trace as trace_mod

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "data" / "domain_a_financial"


def _case(expected_answer, ctype="exact", rules=(), category="lookup",
          citations=("AAPL_2025_10K:Item8",)):
    return {
        "id": "fin-9999", "input": "q?",
        "expected": {"answer": expected_answer, "citations": list(citations),
                     "type": ctype},
        "variation_rules": list(rules), "difficulty": "easy",
        "failure_category": category, "domain": "financial", "notes": "",
    }


def _result(answer, citations=("AAPL_2025_10K:Item8:c007",), refused=False,
            hit_ids=("AAPL_2025_10K:Item8:c007", "PEP_2025_10K:Item1:c000")):
    return {
        "refused": refused, "refusal_reason": "low confidence" if refused else None,
        "answer": answer, "citations": list(citations), "invalid_citations": [],
        "verification": {"verified": True, "claims": []},
        "confidence": 0.8, "latency_ms": 1200.0, "strategy": "dense",
        "model": "test/model",
        "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001,
                  "calls": 1},
        "hits": [{"chunk": {"id": i}, "score": 0.5, "dense_sim": 0.5}
                 for i in hit_ids],
    }


def test_exact_numeric_with_tolerance_and_unit_equivalence():
    case = _case("$416,161 million", rules=["numeric_tolerance:0.1%", "unit_equivalence"])
    ok = engine.score_case(case, _result("Net sales were $416.2 billion."), cfg=None)
    assert ok["correct"] is True                   # billion-scale, within 0.1%
    near = engine.score_case(case, _result("Net sales were $416,300 million."), cfg=None)
    assert near["correct"] is True                 # 0.033% off < 0.1%
    wrong = engine.score_case(case, _result("Net sales were $391,035 million."), cfg=None)
    assert wrong["correct"] is False               # prior-year column


def test_exact_without_unit_equivalence_requires_same_scale():
    case = _case("$416,161 million", rules=["numeric_tolerance:0.1%"])
    assert engine.score_case(case, _result("$416.2 billion"), cfg=None)["correct"] is False


def test_contains_matches_key_figure_inside_longer_prose():
    case = _case("$215,938 million (fiscal year 2026)", ctype="contains",
                 rules=["numeric_tolerance:0.1%", "unit_equivalence"])
    res = _result("Revenue was $215,938 million in FY2026, up 62% year over year.")
    assert engine.score_case(case, res, cfg=None)["correct"] is True


def test_unanswerable_matrix():
    case = _case(None, citations=())
    refusal = engine.score_case(case, _result(None, citations=(), refused=True), cfg=None)
    assert refusal["correct"] is True and refusal["outcome"] == "correct_refusal"
    halluc = engine.score_case(case, _result("$12,345 million"), cfg=None)
    assert halluc["correct"] is False and halluc["outcome"] == "hallucination"


def test_answerable_refusal_is_incorrect_refusal():
    case = _case("$416,161 million")
    scored = engine.score_case(case, _result(None, citations=(), refused=True), cfg=None)
    assert scored["correct"] is False and scored["outcome"] == "incorrect_refusal"


def test_citation_and_retrieval_hits_are_prefix_matches():
    case = _case("$416,161 million")
    scored = engine.score_case(case, _result("$416,161 million"), cfg=None)
    assert scored["citation_hit"] is True          # cited chunk is inside Item8
    assert scored["retrieval_hit"] is True         # a hit chunk is inside Item8
    off = _result("$416,161 million", citations=("AAPL_2025_10K:Item7:c001",),
                  hit_ids=("PEP_2025_10K:Item1:c000",))
    scored2 = engine.score_case(case, off, cfg=None)
    assert scored2["citation_hit"] is False and scored2["retrieval_hit"] is False


class FakeScorer:
    """Stand-in for DeepEvalScorer: records calls, returns canned verdicts."""

    def __init__(self, correct: bool = True, score: float = 1.0):
        self.correct = correct
        self.score = score
        self.calls = 0

    def correctness(self, case, result):
        self.calls += 1
        return {"correct": self.correct, "score": self.score, "reason": "fake verdict"}

    def metrics(self, case, result):
        return {"faithfulness": 1.0, "answer_relevancy": 1.0, "contextual_precision": 1.0}


def test_judge_type_uses_deepeval_scorer():
    scorer = FakeScorer(correct=True, score=0.9)
    case = _case("Revenue grew on data center demand", ctype="judge")
    scored = engine.score_case(case, _result("Growth driven by data center."),
                               cfg=None, scorer=scorer)
    assert scored["correct"] is True and scorer.calls == 1
    assert scored["judge_score"] == 0.9
    assert scored["deepeval"]["faithfulness"] == 1.0

    negative = FakeScorer(correct=False, score=0.2)
    scored2 = engine.score_case(case, _result("Unrelated answer."),
                                cfg=None, scorer=negative)
    assert scored2["correct"] is False


def test_judge_type_without_scorer_fails_loudly():
    case = _case("Revenue grew on data center demand", ctype="judge")
    with pytest.raises(ValueError, match="DeepEval scorer"):
        engine.score_case(case, _result("Growth."), cfg=None, scorer=None)


def test_ambiguous_answered_goes_through_judge():
    case = _case(None, ctype="judge", category="ambiguous", citations=())
    case["notes"] = "year unspecified"
    clarifying = engine.score_case(case, _result("Which fiscal year do you mean?"),
                                   cfg=None, scorer=FakeScorer(correct=True, score=0.8))
    assert clarifying["correct"] is True and clarifying["outcome"] == "answered"
    guessing = engine.score_case(case, _result("$416,161 million."),
                                 cfg=None, scorer=FakeScorer(correct=False, score=0.1))
    assert guessing["correct"] is False


def test_loads_all_50_v1_golden_cases():
    cases = engine.load_cases(GOLDEN_DIR / "golden_set_v1.jsonl")
    assert len(cases) == 50
    assert all(c["expected"]["type"] in ("exact", "contains", "judge") for c in cases)
    assert len({c["id"] for c in cases}) == 50


def test_load_cases_directory_mode_includes_enterprise_set():
    cases = engine.load_cases(GOLDEN_DIR)
    ids = {c["id"] for c in cases}
    assert len(cases) == 95  # 50 v1 + 45 enterprise
    assert any(i.startswith("ent-") for i in ids)
    assert any(i.startswith("fin-") for i in ids)


def test_load_cases_rejects_schema_violations(tmp_path):
    bad = tmp_path / "golden_set_bad.jsonl"
    # a case missing the required `expected` block must fail loudly at load
    bad.write_text(json.dumps({"id": "x", "input": "q"}) + "\n", encoding="utf-8")
    with pytest.raises(Exception):
        engine.load_cases(bad)


def test_trace_roundtrips_through_standard_format():
    trace_dict = build_trace(_case("$416,161 million"),
                             _result("Net sales were $416,161 million."))
    t = trace_mod.Trace.from_dict(json.loads(json.dumps(trace_dict)))
    assert t.case_id == "fin-9999"
    assert t.citations == ["AAPL_2025_10K:Item8:c007"]
    assert t.usage.cost_usd == pytest.approx(0.001)
    kinds = [s.kind for s in t.steps]
    assert "tool_call" in kinds and "response" in kinds
    assert all(k in trace_mod.STEP_KINDS for k in kinds)


def test_aggregate_metrics():
    rows = [
        {"correct": True, "outcome": "answered", "citation_hit": True,
         "retrieval_hit": True, "category": "lookup", "refused": False,
         "latency_ms": 1000.0, "cost_usd": 0.002, "verified": True},
        {"correct": False, "outcome": "hallucination", "citation_hit": False,
         "retrieval_hit": True, "category": "unanswerable", "refused": False,
         "latency_ms": 3000.0, "cost_usd": 0.004, "verified": True},
        {"correct": True, "outcome": "correct_refusal", "citation_hit": None,
         "retrieval_hit": None, "category": "unanswerable", "refused": True,
         "latency_ms": 500.0, "cost_usd": 0.0, "verified": True},
    ]
    m = engine.aggregate(rows)
    assert m["n"] == 3 and m["accuracy"] == pytest.approx(2 / 3)
    assert m["hallucination_rate"] == pytest.approx(1 / 2)   # of 2 unanswerable
    assert m["refusal_correctness"] == pytest.approx(1.0)    # 1 refusal, correct
    assert m["citation_faithfulness"] == pytest.approx(1 / 2)  # of answered w/ cites
    assert m["latency_p50_ms"] == 1000.0
    assert m["cost_per_query_usd"] == pytest.approx(0.002)
    assert m["by_category"]["unanswerable"]["n"] == 2
