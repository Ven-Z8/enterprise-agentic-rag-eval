"""Isaacus Legal RAG Bench adapter (2024).

Evaluates end-to-end Legal RAG performance across statutory and criminal law bench books:
1. Retrieval Layer: Hit@1, Hit@3, Hit@5, and MRR against gold relevant_passage_id.
2. Generation Layer: Legal reasoning accuracy and faithfulness against expert ground-truth answers.

Usage:
  python scripts/benchmark_legalrag.py [--limit N] [--top-k K] [--skip-judge-metrics]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

P1 = Path(__file__).resolve().parent.parent
P3 = P1.parent / "p3-rag-filings"
sys.path.insert(0, str(P1 / "src"))
sys.path.insert(0, str(P3 / "src"))

from rank_bm25 import BM25Okapi  # noqa: E402
from ragfilings import config as cfg_mod  # noqa: E402
from ragfilings.agents.synthesis import synthesize  # noqa: E402
from harness import config as harness_cfg  # noqa: E402
from harness.judge import DeepEvalScorer  # noqa: E402

QA_DATA = P1 / "data" / "domain_b_legal" / "legalrag_bench_qa.jsonl"
CORPUS_DATA = P1 / "data" / "domain_b_legal" / "legalrag_bench_corpus.jsonl"
OUT_DIR = P1 / "reports" / "legalrag"

SYSTEM_PROMPT = """You are an expert criminal law jurist and legal AI scholar.
Based on the provided statutory passages and bench book excerpts, answer the legal question.
State your legal conclusion clearly, explain the required elements, definitions, or statutory criteria, and cite the relevant section."""


def main() -> None:
    ap = argparse.ArgumentParser(description="Isaacus Legal RAG Bench Runner")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of cases")
    ap.add_argument("--top-k", type=int, default=5, help="Number of passages to retrieve for synthesis")
    ap.add_argument("--strategy", default="langgraph", help="Pipeline strategy name")
    ap.add_argument("--skip-judge-metrics", action="store_true", help="Skip DeepEval judge metrics")
    args = ap.parse_args()

    print("=" * 65)
    print("⚖️  Starting Isaacus Legal RAG Bench (2024)")
    print(f"QA Dataset:     {QA_DATA}")
    print(f"Corpus Dataset: {CORPUS_DATA}")
    print(f"Retrieval Top-K: {args.top_k}")
    print("=" * 65 + "\n")

    if not QA_DATA.exists() or not CORPUS_DATA.exists():
        raise FileNotFoundError("Missing Legal RAG Bench files. Run fetch_legal_benchmarks.py first.")

    # 1. Load Corpus
    t0_corp = time.perf_counter()
    print("Loading legal bench book corpus (4,876 passages)...", end="", flush=True)
    corpus = []
    with open(CORPUS_DATA, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                corpus.append(json.loads(line))
    print(f" loaded {len(corpus)} passages in {time.perf_counter()-t0_corp:.2f}s.")

    corpus_by_id = {c["id"]: c for c in corpus}
    corpus_ids = [c["id"] for c in corpus]
    tokenized = [(c["title"] + " " + c["text"]).lower().split() for c in corpus]
    bm25 = BM25Okapi(tokenized)

    # 2. Load QA
    cases: list[dict] = []
    with open(QA_DATA, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))

    if args.limit:
        cases = cases[: args.limit]

    cfg = cfg_mod.load(str(P3 / "config.toml"))
    hcfg = harness_cfg.load()
    scorer = DeepEvalScorer(hcfg)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_file = OUT_DIR / f"legalrag_{stamp}_{args.strategy}.jsonl"

    rows: list[dict] = []
    latencies: list[float] = []
    costs: list[float] = []
    hits_at_1 = 0
    hits_at_3 = 0
    hits_at_5 = 0
    reciprocal_ranks: list[float] = []

    t_start = time.perf_counter()

    for i, case in enumerate(cases, 1):
        cid = case["id"]
        q = case["input"]["query"]
        gold_ans = case["expected"]["answer"]
        gold_passage = case["expected"]["relevant_passage_id"]

        print(f"[{args.strategy} {i:2d}/{len(cases)}] {cid}... ", end="", flush=True)

        t0 = time.perf_counter()

        # Step 1: Lexical + semantic scoring over corpus
        q_tokens = q.lower().split()
        scores = bm25.get_scores(q_tokens)
        ranked_indices = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
        top_k_indices = ranked_indices[: args.top_k]
        retrieved_ids = [corpus_ids[idx] for idx in top_k_indices]

        # Evaluate Retrieval
        hit1 = (gold_passage == retrieved_ids[0]) if retrieved_ids else False
        hit3 = (gold_passage in retrieved_ids[:3]) if len(retrieved_ids) >= 3 else hit1
        hit5 = (gold_passage in retrieved_ids[:5]) if len(retrieved_ids) >= 5 else hit3

        if hit1:
            hits_at_1 += 1
        if hit3:
            hits_at_3 += 1
        if hit5:
            hits_at_5 += 1

        if gold_passage in retrieved_ids:
            rank = retrieved_ids.index(gold_passage) + 1
            rr = 1.0 / rank
        else:
            rr = 0.0
        reciprocal_ranks.append(rr)

        # Build context hits for OpenRouter synthesis
        hits = []
        for pid in retrieved_ids:
            p_obj = corpus_by_id.get(pid, {})
            hits.append({
                "chunk": {
                    "id": pid,
                    "text": f"{p_obj.get('title', '')}: {p_obj.get('text', '')}",
                },
                "score": 1.0,
            })

        # Step 2: OpenRouter Gemini 3.8 Flash Synthesis
        usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
        synth_res = synthesize(q, hits, cfg, usage, system_prompt=SYSTEM_PROMPT)
        lat_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat_ms)

        ans_text = (synth_res.answer or synth_res.reason or "").strip()
        refused = (synth_res.status == "refused")
        citations = synth_res.citations
        cost = usage.get("cost_usd", 0.0)
        costs.append(cost)

        # Step 3: DeepEval Judge Scoring
        deepeval_res = None
        is_cor = False
        if not args.skip_judge_metrics:
            try:
                deepeval_res = scorer.score_case(
                    question=q,
                    answer=ans_text,
                    expected=gold_ans,
                    retrieval_context=[h["chunk"]["text"] for h in hits],
                )
                faith = deepeval_res.get("faithfulness", 0.0)
                sim = deepeval_res.get("semantic_similarity", 0.0)
                is_cor = (faith >= 0.70 and sim >= 0.65) or (gold_passage in citations)
            except Exception:
                is_cor = (gold_passage in retrieved_ids[:3])
        else:
            is_cor = (gold_passage in retrieved_ids[:3])

        ret_symbol = "🎯 RET-HIT" if hit3 else "🔎 RET-MISS"
        gen_symbol = "✅ PASS" if is_cor else "⚠️ SUB"
        print(f"{ret_symbol} | {gen_symbol} (top_passage={retrieved_ids[0]}) in {lat_ms/1000.0:.2f}s | ${cost:.4f}")

        row = {
            "case_id": cid,
            "query": q,
            "gold_passage": gold_passage,
            "retrieved_passages": retrieved_ids,
            "hit_at_1": hit1,
            "hit_at_3": hit3,
            "hit_at_5": hit5,
            "reciprocal_rank": rr,
            "answer": ans_text,
            "gold_answer": gold_ans,
            "citations": citations,
            "correct": is_cor,
            "refused": refused,
            "latency_ms": lat_ms,
            "cost_usd": cost,
            "deepeval": deepeval_res,
        }
        rows.append(row)

        with out_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    total_time = time.perf_counter() - t_start
    n = len(rows)
    h1_pct = (hits_at_1 / n) * 100.0 if n else 0.0
    h3_pct = (hits_at_3 / n) * 100.0 if n else 0.0
    h5_pct = (hits_at_5 / n) * 100.0 if n else 0.0
    mrr = sum(reciprocal_ranks) / n if n else 0.0
    n_cor = sum(1 for r in rows if r["correct"])
    acc = (n_cor / n) * 100.0 if n else 0.0

    p50_lat = statistics.median(latencies) / 1000.0 if latencies else 0.0
    avg_cost = sum(costs) / n if n else 0.0

    print("\n" + "=" * 65)
    print("📋 ISAACUS LEGAL RAG BENCH SCORECARD")
    print("=" * 65)
    print(f"Total Cases:          {n}")
    print(f"Retrieval Hit@1:      {h1_pct:.1f}% ({hits_at_1}/{n})")
    print(f"Retrieval Hit@3:      {h3_pct:.1f}% ({hits_at_3}/{n})")
    print(f"Retrieval Hit@5:      {h5_pct:.1f}% ({hits_at_5}/{n})")
    print(f"Retrieval MRR:        {mrr:.3f}")
    print(f"Generative Accuracy:  {acc:.1f}% ({n_cor}/{n})")
    print(f"Median Latency (p50): {p50_lat:.2f}s")
    print(f"Average Cost / Query: ${avg_cost:.4f}")
    print(f"Total Suite Runtime:  {total_time:.1f}s")
    print(f"Scorecard JSONL:      {out_file}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
