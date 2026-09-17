"""CUAD benchmark adapter — Contract Understanding Atticus Dataset (NeurIPS 2021).

Evaluates the legal RAG pipeline against the official CUAD test split across:
1. Contract Clause Extraction (Governing Law, Termination, Non-Compete, Liability Cap, etc.)
2. Document & Party Lookups (Titles, Dates, Parties, Defined Terms)
3. Unanswerable Absence Detection (Source Code Escrow, Joint IP, etc.)
4. Ambiguous Agreement Scope Clarifications

Usage:
  python scripts/benchmark_cuad.py [--limit N] [--strategy langgraph] [--skip-judge-metrics]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

P1 = Path(__file__).resolve().parent.parent
P3 = P1.parent / "rag-engine"
sys.path.insert(0, str(P1 / "src"))
sys.path.insert(0, str(P3 / "src"))

from harness import config as harness_cfg  # noqa: E402
from harness.adapters.ragfilings_adapter import RAGFilingsAdapter  # noqa: E402
from harness.judge import DeepEvalScorer  # noqa: E402
from harness.metrics.engine import load_cases, score_case  # noqa: E402

CUAD_DATA = P1 / "data" / "domain_b_legal" / "golden_set_legal_v1.jsonl"
OUT_DIR = P1 / "reports" / "cuad"


def main() -> None:
    ap = argparse.ArgumentParser(description="CUAD Legal Benchmark Runner")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of cases (for smoke runs)")
    ap.add_argument("--strategy", default="langgraph", help="RAG pipeline strategy")
    ap.add_argument("--skip-judge-metrics", action="store_true", help="Skip auxiliary DeepEval judge metrics")
    args = ap.parse_args()

    print("=" * 60)
    print("⚖️  Starting CUAD Legal Contract Understanding Benchmark")
    print(f"Dataset: {CUAD_DATA}")
    print(f"Strategy: {args.strategy}")
    print("=" * 60 + "\n")

    cases = load_cases(CUAD_DATA)
    if args.limit:
        cases = cases[: args.limit]

    cfg = harness_cfg.load()
    adapter = RAGFilingsAdapter(domain="legal")
    scorer = DeepEvalScorer(cfg)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_file = OUT_DIR / f"cuad_{stamp}_{args.strategy}.jsonl"

    rows: list[dict] = []
    latencies: list[float] = []
    costs: list[float] = []

    t_start = time.perf_counter()

    for i, case in enumerate(cases, 1):
        cid = case["id"]
        cat = case.get("failure_category", "unknown")
        q = case["input"]
        print(f"[{args.strategy} {i:2d}/{len(cases)}] {cid} ({cat})... ", end="", flush=True)

        t0 = time.perf_counter()
        raw_res = adapter.run_case(case, strategy=args.strategy)
        lat = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat)

        cost = raw_res.get("usage", {}).get("cost_usd", 0.0)
        costs.append(cost)

        scored = score_case(
            case,
            raw_res,
            cfg=cfg,
            scorer=scorer,
            include_deepeval_metrics=not args.skip_judge_metrics,
        )

        is_cor = scored.get("correct", False)
        outcome = scored.get("outcome", "unknown")
        symbol = "✅ PASS" if is_cor else "❌ FAIL"
        print(f"{symbol} ({outcome}) in {lat/1000.0:.1f}s | ${cost:.4f}")

        row = {
            "case_id": cid,
            "category": cat,
            "correct": is_cor,
            "outcome": outcome,
            "latency_ms": lat,
            "cost_usd": cost,
            "refused": raw_res.get("refused", False),
            "refusal_reason": raw_res.get("refusal_reason"),
            "input": q,
            "answer": raw_res.get("answer"),
            "citations": raw_res.get("citations", []),
            "judge_reason": scored.get("judge_reason"),
            "judge_score": scored.get("judge_score"),
            "deepeval": scored.get("deepeval"),
        }
        rows.append(row)

        with out_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    total_time = time.perf_counter() - t_start
    n = len(rows)
    n_correct = sum(1 for r in rows if r["correct"])
    acc = (n_correct / n) * 100.0 if n else 0.0

    p50_lat = statistics.median(latencies) / 1000.0 if latencies else 0.0
    p95_lat = statistics.quantiles(latencies, nquantiles=20)[18] / 1000.0 if len(latencies) >= 20 else p50_lat
    avg_cost = sum(costs) / n if n else 0.0

    # Category breakdown
    cats: dict[str, list[bool]] = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r["correct"])

    unans = [r for r in rows if r["category"] == "unanswerable"]
    hallucinations = sum(1 for r in unans if not r["refused"])
    hallucination_rate = (hallucinations / len(unans)) * 100.0 if unans else 0.0

    print("\n" + "=" * 60)
    print("📋 CUAD LEGAL BENCHMARK SCORECARD")
    print("=" * 60)
    print(f"Total Cases:         {n}")
    print(f"Overall Accuracy:    {acc:.1f}% ({n_correct}/{n})")
    print(f"Hallucination Rate:  {hallucination_rate:.1f}% ({hallucinations}/{len(unans)} unanswerables)")
    print(f"Median Latency (p50): {p50_lat:.1f}s")
    print(f"95th Pct Latency:    {p95_lat:.1f}s")
    print(f"Average Cost/Query:  ${avg_cost:.4f}")
    print(f"Total Runtime:       {total_time:.1f}s")
    print("\nCategory Breakdown:")
    for c, results in sorted(cats.items()):
        c_acc = (sum(results) / len(results)) * 100.0
        print(f"  {c:18}: {c_acc:5.1f}% ({sum(results)}/{len(results)})")
    print(f"\nDetailed results saved to: {out_file}\n")


if __name__ == "__main__":
    main()
