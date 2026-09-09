"""FinanceBench benchmark adapter — two modes.

evidence (default): reasoning-over-evidence. Each question is handed its
official evidence excerpt as the retrieved context; the pipeline then does
grounded synthesis + numeric-claim verification + financial math on top.
Measures grounding/reasoning with retrieval isolated out (FinanceBench's
filings are out-of-corpus PDFs).

retrieval: full retrieval. The referenced filings were downloaded (EDGAR
first) and indexed by scripts/build_financebench_corpus.py; each question
retrieves its own top-k chunks from that index and answers from them.
Measures retrieval + grounding + reasoning end-to-end.

Both modes score our answer against the official FinanceBench answer with
the calibrated G-Eval judge.

Usage:
  uv run python scripts/benchmark_financebench.py [--limit N]
  uv run python scripts/benchmark_financebench.py --mode retrieval [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

P1 = Path(__file__).resolve().parent.parent
P3 = P1.parent / "p3-rag-filings"
sys.path.insert(0, str(P1 / "src"))
sys.path.insert(0, str(P3 / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from financebench_common import FB_DIR, load_financebench  # noqa: E402
from ragfilings.config import load as load_cfg  # noqa: E402
from ragfilings.pipeline.engine import answer  # noqa: E402

from harness import config as harness_cfg  # noqa: E402
from harness.judge import DeepEvalScorer  # noqa: E402


def evidence_hits(rec: dict) -> list[dict]:
    """Build pseudo retrieval hits from the official evidence text."""
    hits = []
    doc = rec.get("doc_name", "unknown")
    for i, ev in enumerate(rec.get("evidence", [])):
        text = ev.get("evidence_text") or ev.get("evidence_text_full_page") or ""
        if not text.strip():
            continue
        hits.append(
            {
                "chunk": {
                    "id": f"{doc}:evidence:{i}",
                    "text": text,
                    "section": "evidence",
                    "ticker": None,
                },
                "score": 0.9,
                "dense_sim": 0.9,
            }
        )
    return hits


def make_retriever(cfg: dict):
    """Load the FinanceBench index built by build_financebench_corpus.py."""
    from ragfilings import retrieval

    index_dir = FB_DIR / "index"
    manifest_path = FB_DIR / "corpus_manifest.json"
    if not (index_dir / "embeddings.npy").exists():
        raise SystemExit(
            f"no FinanceBench index at {index_dir} — run scripts/build_financebench_corpus.py first"
        )
    index = retrieval.load_index(index_dir, cfg["embedding"]["model"])
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    indexed_docs = {name for name, e in manifest.items() if e.get("n_chunks")}

    def retrieve(rec: dict) -> tuple[list[dict], bool]:
        hits = index.search(
            rec["question"],
            "hybrid_rerank",
            top_k=cfg["retrieval"]["top_k"],
            reranker_name=cfg["retrieval"]["reranker"],
            rerank_candidates=cfg["retrieval"]["rerank_candidates"],
        )
        return hits, rec["doc_name"] in indexed_docs

    return retrieve, indexed_docs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["evidence", "retrieval"], default="evidence")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg = load_cfg(str(P3 / "config.toml"))
    # The synthesis pipeline reads p3's config; the judge reads the harness's.
    cfg["judge"] = harness_cfg.load().get("judge", {})
    recs = load_financebench()
    if args.limit:
        recs = recs[: args.limit]

    retrieve, indexed_docs = (None, None)
    if args.mode == "retrieval":
        retrieve, indexed_docs = make_retriever(cfg)
        covered = sum(1 for r in recs if r["doc_name"] in indexed_docs)
        print(
            f"retrieval mode: {covered}/{len(recs)} questions have their "
            f"document in the index ({len(indexed_docs)} docs indexed)"
        )

    scorer = DeepEvalScorer(cfg)

    out_path = (
        Path(args.out)
        if args.out
        else (
            P1
            / "reports"
            / "financebench"
            / f"fb_{args.mode}_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_correct = 0
    with out_path.open("w", encoding="utf-8") as out:
        for i, rec in enumerate(recs):
            qid = rec["financebench_id"]
            question = rec["question"]
            official = rec["answer"]
            doc_unavailable = False
            hit_ids: list[str] = []
            if args.mode == "evidence":
                hits = evidence_hits(rec)
                if not hits:
                    print(f"[{i + 1}/{len(recs)}] {qid}: no evidence, skip")
                    continue
            else:
                hits, doc_ok = retrieve(rec)
                doc_unavailable = not doc_ok
                hit_ids = [h["chunk"]["id"] for h in hits]
            t0 = time.time()
            try:
                # graph_rescue=None: the graph is built from OUR 25 filings, not
                # FinanceBench's, so disable graph augmentation/clarification here.
                res = answer(question, hits, cfg, graph_rescue=None)
            except Exception as e:  # noqa: BLE001
                print(f"[{i + 1}/{len(recs)}] {qid}: ERROR {e}")
                continue
            dt = time.time() - t0

            our_answer = res.get("answer")
            if res.get("refused") or not our_answer:
                our_answer = res.get("refusal_reason") or ""

            # Score our answer against the official answer with the judge.
            case = {
                "id": qid,
                "input": question,
                "expected": {"answer": official, "type": "judge"},
            }
            result = {
                "answer": our_answer,
                "refused": res.get("refused", False),
                "citations": res.get("citations", []),
                "hits": hits,
            }
            try:
                scored = scorer.correctness(case, result)
                correct = bool(scored.get("correct"))
            except Exception as e:  # noqa: BLE001
                print(f"[{i + 1}/{len(recs)}] {qid}: judge ERROR {e}")
                correct = False

            n_correct += int(correct)
            flag = "" if not doc_unavailable else " [doc-not-indexed]"
            print(
                f"[{i + 1}/{len(recs)}] {qid}: "
                f"{'CORRECT' if correct else 'WRONG'}{flag} ({dt:.1f}s)"
            )
            out.write(
                json.dumps(
                    {
                        "id": qid,
                        "mode": args.mode,
                        "question": question,
                        "doc_name": rec["doc_name"],
                        "doc_unavailable": doc_unavailable,
                        "official_answer": official,
                        "our_answer": our_answer,
                        "refused": res.get("refused", False),
                        "correct": correct,
                        "citations": res.get("citations", []),
                        "hit_ids": hit_ids,
                        "latency_s": dt,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            out.flush()

    total = len(recs)
    print(f"\nFinanceBench ({args.mode}): {n_correct}/{total} = {n_correct / total:.1%}")
    print(f"results -> {out_path}")


if __name__ == "__main__":
    main()
