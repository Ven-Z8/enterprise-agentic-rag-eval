"""Retrieval — two strategies over the chunk store, switchable via config.

  - "dense"  : embedding cosine similarity (baseline)
  - "hybrid" : reciprocal-rank fusion of dense + BM25 rankings

Embedding model: BAAI/bge-small-en-v1.5, run locally via sentence-transformers.
Why this model and not an embeddings API:
  (1) zero API keys — `ragfilings index` reproduces the exact index on any
      machine, which the README's one-command repro promises;
  (2) its 512-token window covers our 1,800-char chunks without truncation
      (MiniLM's 256 would silently halve every chunk);
  (3) top BEIR retrieval quality per parameter at 33M params — CPU/MPS
      indexing of ~8.4K chunks finishes in minutes.
Its known weakness — exact numerals and tickers — is precisely what the
hybrid strategy's BM25 leg compensates for; that contrast is the point of
the dense-vs-hybrid comparison this project publishes.

The index is built once (`ragfilings index`) and persisted: embeddings.npy +
chunks.jsonl (frozen ordering) + meta.json. BM25 is rebuilt at load time —
tokenizing 8.4K chunks takes ~1s, not worth a persistence format.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

# BGE models are trained with this query-side instruction; passages get none.
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_RRF_K = 60  # standard reciprocal-rank-fusion constant; flat quality plateau


def _load_model(model_name: str):
    # Imported lazily: tests fake this out, and `ragfilings parse` etc. should
    # not pay the torch import.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower().replace(",", ""))


def context_header(chunk: dict[str, Any]) -> str:
    """Readable provenance header for a chunk.

    Financial chunks: company, ticker, fiscal year, form, item and section
    title. Most financial-statement table chunks carry no company identifier
    in their body (only ~31% mention their own company/ticker), so without
    this header the retriever cannot tell one filer's income statement from
    another's. The header makes embeddings, BM25, the reranker, and the LLM
    context all company/section aware without touching the body (which the
    fact-graph builder parses unchanged).

    Contract chunks (doc_type == "contract"): contract code + agreement title.
    """
    if chunk.get("doc_type") == "contract":
        head = f"Contract {chunk.get('contract', '')}: {chunk.get('contract_title', '')}"
        title = chunk.get("title") or ""
        if title and title not in head:
            head += f" — {title}"
        return head
    company = chunk.get("company") or ""
    ticker = chunk.get("ticker") or ""
    fy = chunk.get("fiscal_year")
    form = chunk.get("form") or "10-K"
    item = chunk.get("item") or ""
    title = chunk.get("title") or ""
    head = f"{company} ({ticker}) FY{fy} {form}"
    if item:
        head += f" — Item {item}"
    if title:
        head += f": {title}" if item else f" — {title}"
    return head


def embed_text(chunk: dict[str, Any]) -> str:
    """The string embedded / indexed / shown to the LLM: header + body."""
    return context_header(chunk) + "\n" + chunk["text"]


_reranker_model = None
_reranker_name = None


def _get_reranker(model_name: str = "BAAI/bge-reranker-base"):
    global _reranker_model, _reranker_name
    if _reranker_model is None or _reranker_name != model_name:
        from sentence_transformers import CrossEncoder

        _reranker_model = CrossEncoder(model_name)
        _reranker_name = model_name
    return _reranker_model


@dataclass
class Index:
    chunks: list[dict[str, Any]]
    embeddings: np.ndarray  # (n_chunks, dim), L2-normalized rows
    bm25: BM25Okapi
    model: Any  # embedding model, encodes queries at search time

    def _filter_mask(self, filters: dict[str, Any] | None) -> np.ndarray | None:
        """Boolean mask over chunks matching ALL metadata equality filters.

        Returns None when no filters are given. Callers decide the filters
        (e.g. {"ticker": "AAPL", "fiscal_year": "2025"}); retrieval itself
        never infers them from query text.
        """
        if not filters:
            return None
        mask = np.ones(len(self.chunks), dtype=bool)
        for key, value in filters.items():
            wanted = {value} if not isinstance(value, (list, tuple, set)) else set(value)
            for i, c in enumerate(self.chunks):
                if mask[i] and str(c.get(key, "")) not in {str(w) for w in wanted}:
                    mask[i] = False
        return mask

    def search(
        self,
        query: str,
        strategy: str,
        top_k: int,
        reranker_name: str | None = None,
        filters: dict[str, Any] | None = None,
        rerank_candidates: int = 25,
    ) -> list[dict[str, Any]]:
        """Return top_k hits: {chunk, score, dense_sim}, best first.

        filters: optional hard metadata filter (see _filter_mask). If the
        filter matches no chunks, [] is returned rather than silently
        widening — the caller decides whether to retry unfiltered.
        """
        mask = self._filter_mask(filters)
        if mask is not None and not mask.any():
            return []

        q = self.model.encode([_BGE_QUERY_PREFIX + query], normalize_embeddings=True)[0]
        dense_sims = self.embeddings @ q
        if mask is not None:
            dense_sims = np.where(mask, dense_sims, -1.0)

        if strategy == "dense":
            order = np.argsort(-dense_sims, kind="stable")[:top_k]
            scored = [(int(i), float(self.embeddings[i] @ q)) for i in order]
        elif strategy in ("hybrid", "hybrid_rerank"):
            bm25_scores = self.bm25.get_scores(_tokenize(query))
            if mask is not None:
                bm25_scores = np.where(mask, bm25_scores, -1.0)
            rrf = np.zeros(len(self.chunks))
            for ranking in (
                np.argsort(-dense_sims, kind="stable"),
                np.argsort(-bm25_scores, kind="stable"),
            ):
                for rank, i in enumerate(ranking):
                    rrf[i] += 1.0 / (_RRF_K + rank + 1)

            if strategy == "hybrid_rerank":
                candidate_order = np.argsort(-rrf, kind="stable")[:rerank_candidates]
                reranker = _get_reranker(reranker_name or "BAAI/bge-reranker-base")
                pairs = [(query, embed_text(self.chunks[i])) for i in candidate_order]
                rerank_scores = reranker.predict(pairs)
                reranked = sorted(
                    zip(candidate_order, rerank_scores), key=lambda x: x[1], reverse=True
                )[:top_k]
                scored = [(int(i), float(s)) for i, s in reranked]
            else:
                order = np.argsort(-rrf, kind="stable")[:top_k]
                scored = [(int(i), float(rrf[i])) for i in order]
        else:
            raise ValueError(f"unknown retrieval strategy: {strategy!r}")
        return [
            {"chunk": self.chunks[i], "score": s, "dense_sim": float(self.embeddings[i] @ q)}
            for i, s in scored
        ]


def confidence(hits: list[dict[str, Any]]) -> float:
    """Retrieval confidence = best dense cosine among the hits."""
    return max((h.get("dense_sim", h.get("score", 0.0)) for h in hits), default=0.0)


def build_index(chunks: list[dict[str, Any]], index_dir: str | Path, model_name: str) -> None:
    """Embed every chunk once and persist the index to index_dir."""
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    model = _load_model(model_name)
    emb = np.asarray(
        model.encode(
            [embed_text(c) for c in chunks],
            batch_size=64,
            normalize_embeddings=True,
            show_progress_bar=True,
        ),
        dtype=np.float32,
    )
    np.save(index_dir / "embeddings.npy", emb)
    with (index_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (index_dir / "meta.json").write_text(
        json.dumps({"model": model_name, "n_chunks": len(chunks), "dim": int(emb.shape[1])})
    )


def load_index(index_dir: str | Path, model_name: str) -> Index:
    index_dir = Path(index_dir)
    if not (index_dir / "embeddings.npy").exists():
        raise FileNotFoundError(f"no index at {index_dir} — build it first with `ragfilings index`")
    chunks = [json.loads(line) for line in (index_dir / "chunks.jsonl").open(encoding="utf-8")]
    embeddings = np.load(index_dir / "embeddings.npy")
    bm25 = BM25Okapi([_tokenize(embed_text(c)) for c in chunks])
    return Index(chunks, embeddings, bm25, _load_model(model_name))
