"""Retrieval: index build/persist roundtrip, dense ranking, hybrid BM25 rescue.

Tests use a deterministic fake embedder (letter-trigram hashing, digit-blind)
so no model download is needed and the hybrid test is meaningful: the fake
dense leg cannot see numbers, so only BM25 can rescue an exact-figure query —
exactly the failure mode hybrid exists to fix on real financial filings.
"""

import zlib

import numpy as np
import pytest

from ragfilings import retrieval


class FakeModel:
    """Digit-blind letter-trigram embedder. Deterministic (crc32, not the
    per-process-randomized builtin hash), no downloads."""

    DIM = 64

    def encode(self, texts, **kwargs):
        out = []
        for t in texts:
            t = t.removeprefix(retrieval._BGE_QUERY_PREFIX)
            v = np.zeros(self.DIM)
            letters = "".join(ch if ch.isalpha() else " " for ch in t.lower())
            for word in letters.split():
                for i in range(len(word) - 2):
                    v[zlib.crc32(word[i : i + 3].encode()) % self.DIM] += 1.0
            n = np.linalg.norm(v)
            out.append(v / n if n else v)
        return np.array(out)


def _chunk(cid, text):
    return {
        "id": cid,
        "doc_id": cid.split(":")[0],
        "section_id": cid.split(":")[1],
        "item": "8",
        "ticker": cid.split("_")[0],
        "text": text,
    }


# The figure-bearing chunk sits LAST so index-order tie-breaks can never hand
# it a win by accident.
FIGURE_ID = "AAPL_2025_10K:Item8:c000"
CHUNKS = [
    _chunk(
        "AAPL_2025_10K:Item7:c000",
        "Management discussion of liquidity and capital resources for the year.",
    ),
    _chunk(
        "NVDA_2026_10K:Item8:c000",
        "Data center segment revenue grew driven by accelerated computing demand.",
    ),
    _chunk(
        "PEP_2025_10K:Item1:c000",
        "PepsiCo brands include beverages and convenient foods sold worldwide.",
    ),
    _chunk(
        FIGURE_ID, "Consolidated statements of operations. Total net sales | $416,161 | $391,035"
    ),
]


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "_load_model", lambda name: FakeModel())
    retrieval.build_index(CHUNKS, tmp_path, model_name="fake")
    return retrieval.load_index(tmp_path, model_name="fake")


def test_build_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "_load_model", lambda name: FakeModel())
    retrieval.build_index(CHUNKS, tmp_path, model_name="fake")
    idx = retrieval.load_index(tmp_path, model_name="fake")
    assert [c["id"] for c in idx.chunks] == [c["id"] for c in CHUNKS]
    assert idx.embeddings.shape == (len(CHUNKS), FakeModel.DIM)


def test_load_without_index_says_how_to_build(tmp_path):
    with pytest.raises(FileNotFoundError, match="ragfilings index"):
        retrieval.load_index(tmp_path, model_name="fake")


def test_dense_ranks_semantic_match_first(index):
    hits = index.search("data center revenue growth", strategy="dense", top_k=2)
    assert hits[0]["chunk"]["id"].startswith("NVDA_2026_10K")
    assert hits[0]["score"] >= hits[1]["score"]
    assert 0.0 <= hits[0]["dense_sim"] <= 1.0 + 1e-9


def test_hybrid_bm25_lifts_exact_figures_dense_cannot_see(index):
    # Pure-figure query: the fake dense embedder is digit-blind, so dense
    # cannot surface the figure chunk. Only the hybrid BM25 leg can.
    query = "416,161 391,035"
    dense_ids = [h["chunk"]["id"] for h in index.search(query, "dense", top_k=2)]
    hybrid_ids = [h["chunk"]["id"] for h in index.search(query, "hybrid", top_k=2)]
    assert FIGURE_ID not in dense_ids
    assert FIGURE_ID in hybrid_ids


def test_top_k_and_unknown_strategy(index):
    assert len(index.search("pepsi beverages", strategy="dense", top_k=3)) == 3
    with pytest.raises(ValueError, match="strategy"):
        index.search("q", strategy="rerank", top_k=2)


def test_confidence_is_top_dense_sim_for_both_strategies(index):
    # Refusal gating compares confidence against one threshold, so it must be
    # on the same scale (dense cosine) regardless of ranking strategy.
    for strategy in ("dense", "hybrid"):
        hits = index.search("pepsi beverages and convenient foods", strategy=strategy, top_k=4)
        assert max(h["dense_sim"] for h in hits) == pytest.approx(
            retrieval.confidence(hits), abs=1e-9
        )


def test_context_header_defaults_to_10k_and_item():
    chunk = {
        "company": "Apple",
        "ticker": "AAPL",
        "fiscal_year": 2025,
        "item": "8",
        "title": "Financial Statements",
        "text": "x",
    }
    assert retrieval.context_header(chunk) == (
        "Apple (AAPL) FY2025 10-K — Item 8: Financial Statements"
    )


def test_context_header_supports_other_forms_and_generic_sections():
    # Non-10-K corpus chunks (10-Q / 8-K / earnings PDFs) carry a form field;
    # generic sections carry no item number.
    chunk = {
        "company": "Amcor",
        "ticker": "AMCR",
        "fiscal_year": 2023,
        "form": "10-Q",
        "item": "S2",
        "title": "Part 2",
        "text": "x",
    }
    assert retrieval.context_header(chunk) == ("Amcor (AMCR) FY2023 10-Q — Item S2: Part 2")
    no_item = {
        "company": "3M",
        "ticker": "MMM",
        "fiscal_year": 2018,
        "form": "Earnings",
        "item": "",
        "title": "Part 1",
        "text": "x",
    }
    assert retrieval.context_header(no_item) == "3M (MMM) FY2018 Earnings — Part 1"
    assert retrieval.embed_text(no_item).startswith("3M (MMM) FY2018 Earnings — Part 1\n")
