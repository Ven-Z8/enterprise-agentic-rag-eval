"""End-to-end regression guards for the RAG pipeline.

- Known-answer questions must retrieve the right section from the REAL index
  (skipped when the index hasn't been built — it's gitignored).
- An unanswerable low-confidence query must refuse without any model call and
  the refusal must be logged with its reason.

Scoring/scorecard behavior lives in the sibling p1-eval-harness project.
The "verification catches a planted wrong number" requirement is pinned in
test_verification.py::test_catches_planted_wrong_number and
test_generation.py::test_planted_wrong_number_triggers_one_corrective_retry.
"""

import json
from pathlib import Path

import pytest

from ragfilings.config import load
from ragfilings.pipeline import engine as generation

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "corpus" / "index"

needs_index = pytest.mark.skipif(
    not (INDEX_DIR / "embeddings.npy").exists(),
    reason="real index not built (run `ragfilings index`)",
)


@pytest.fixture(scope="module")
def real_index():
    from ragfilings import retrieval

    cfg = load()
    return retrieval.load_index(INDEX_DIR, cfg["embedding"]["model"])


# KNOWN LIMITATION (deliberate, measured by the eval): hybrid's BM25 leg
# pollutes cross-company on generic financial phrasing ("total net sales",
# "fiscal 2025" match every retailer), so the AAPL case is pinned dense-only.
# Company-aware filtering is the candidate fix for the failure analysis.
@needs_index
@pytest.mark.parametrize(
    "question,section,strategies",
    [
        (
            "What was Apple's total net sales for fiscal year 2025?",
            "AAPL_2025_10K:Item8",
            ("dense",),
        ),
        (
            "What risks does NVIDIA describe around export controls?",
            "NVDA_2026_10K:Item1A",
            ("dense", "hybrid"),
        ),
        (
            "What was Microsoft's total revenue in fiscal year 2025?",
            "MSFT_2025_10K:Item8",
            ("dense", "hybrid"),
        ),
    ],
)
def test_known_answer_question_retrieves_right_section(real_index, question, section, strategies):
    for strategy in strategies:
        hits = real_index.search(question, strategy, top_k=8)
        ids = [h["chunk"]["id"] for h in hits]
        assert any(i.startswith(section) for i in ids), (
            f"{strategy} missed {section}; got {ids[:4]}..."
        )


class LowConfidenceIndex:
    def search(
        self, query, strategy, top_k, reranker_name=None, filters=None, rerank_candidates=25
    ):
        chunk = {"id": "PEP_2025_10K:Item1:c000", "text": "irrelevant filler"}
        return [{"chunk": chunk, "score": 0.05, "dense_sim": 0.05}]


def test_unanswerable_low_confidence_refuses_and_logs(tmp_path, monkeypatch):
    from ragfilings.pipeline import orchestrator as orch_mod
    from ragfilings.schemas import QueryPlan

    def boom(*a, **k):
        raise AssertionError("model must not be called on a gate refusal")

    monkeypatch.setattr(generation, "_complete", boom)

    # Mock plan_query to avoid LLM call — return a simple plan
    fake_plan = QueryPlan(
        intent="question",
        reasoning="test",
        sub_questions=[],
        ticker=None,
        fiscal_year=None,
    )
    monkeypatch.setattr(
        orch_mod, "plan_query", lambda *a, **kw: (fake_plan, None)
    )

    cfg = load()
    log = tmp_path / "refusals.jsonl"
    result = generation.ask(
        "What was Tesla's average vehicle selling price in March 2026?",
        cfg,
        index=LowConfidenceIndex(),
        strategy="dense",
        refusal_log=log,
    )
    assert result["refused"] and "confidence" in result["refusal_reason"]
    entry = json.loads(log.read_text().strip())
    assert entry["reason"] == result["refusal_reason"]
    assert entry["strategy"] == "dense" and "Tesla" in entry["query"]

