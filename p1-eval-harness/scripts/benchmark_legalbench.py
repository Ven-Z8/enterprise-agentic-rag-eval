"""Stanford LegalBench benchmark adapter — Consumer Contracts QA split (NeurIPS 2023).

Evaluates the legal RAG engine on real consumer Terms of Service agreements
(Microsoft, eBay, Netflix, Zoom, Google) testing arbitration clauses, liability caps,
opt-out provisions, data privacy, and cancellation policies.

Usage:
  python scripts/benchmark_legalbench.py [--limit N] [--strategy langgraph] [--skip-judge-metrics]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

P1 = Path(__file__).resolve().parent.parent
P3 = P1.parent / "p3-rag-filings"
sys.path.insert(0, str(P1 / "src"))
sys.path.insert(0, str(P3 / "src"))

from ragfilings import config as cfg_mod  # noqa: E402
from ragfilings.agents.synthesis import synthesize  # noqa: E402
from harness import config as harness_cfg  # noqa: E402
from harness.judge import DeepEvalScorer  # noqa: E402

LEGALBENCH_DATA = P1 / "data" / "domain_b_legal" / "legalbench_consumer_contracts_qa.jsonl"
OUT_DIR = P1 / "reports" / "legalbench"

SYSTEM_PROMPT = """You are a legal AI assistant evaluating consumer contracts and Terms of Service agreements.
Answer the user question based ONLY on the provided contract excerpt.
Your response MUST begin with either 'Yes.' or 'No.', followed by a concise 1-2 sentence legal explanation citing the specific clause or sentence that supports your conclusion."""


def extract_binary_decision(answer: str) -> str:
    """Extract 'yes' or 'no' from the beginning of the generated answer."""
    cleaned = answer.strip()
    m = re.match(r"^(yes|no)\b", cleaned, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    low = cleaned[:30].lower()
    if "yes" in low and "no" not in low:
        return "yes"
    if "no" in low and "yes" not in low:
        return "no"
    return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description="Stanford LegalBench Consumer Contracts Runner")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of cases")
    ap.add_argument("--strategy", default="langgraph", help="RAG pipeline strategy")
    ap.add_argument("--skip-judge-metrics", action="store_true", help="Skip DeepEval judge metrics")
    args = ap.parse_args()

    print("=" * 65)
    print("⚖️  Starting Stanford LegalBench (Consumer Contracts QA, NeurIPS 2023)")
    print(f"Dataset:  {LEGALBENCH_DATA}")
    print(f"Strategy: {args.strategy}")
    print("=" * 65 + "\n")

    if not LEGALBENCH_DATA.exists():
        raise FileNotFoundError(f"Missing dataset at {LEGALBENCH_DATA}. Run fetch_legal_benchmarks.py first.")

    cases: list[dict] = []
    with open(LEGALBENCH_DATA, "r", encoding="utf-8") as f:
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
    out_file = OUT_DIR / f"legalbench_{stamp}_{args.strategy}.jsonl"

    rows: list[dict] = []
    latencies: list[float] = []
    costs: list[float] = []

    t_start = time.perf_counter()

    for i, case in enumerate(cases, 1):
        cid = case["id"]
        q = case["input"]["query"]
        contract = case["input"]["contract"]
        gold = case["expected"]["answer"].strip().lower()

        print(f"[{args.strategy} {i:2d}/{len(cases)}] {cid}... ", end="", flush=True)

        hits = [{
            "chunk": {
                "id": f"tos_clause_{cid}",
                "text": contract,
            },
            "score": 1.0,
        }]

        usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
        t0 = time.perf_counter()
        synth_res = synthesize(q, hits, cfg, usage, system_prompt=SYSTEM_PROMPT)
        lat_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(lat_ms)

        ans_text = (synth_res.answer or synth_res.reason or "").strip()
        citations = synth_res.citations
        pred = extract_binary_decision(ans_text)
        is_cor = (pred == gold)
        cost = usage.get("cost_usd", 0.0)
        costs.append(cost)

        # DeepEval judge scoring
        deepeval_res = None
        if not args.skip_judge_metrics:
            try:
                deepeval_res = scorer.score_case(
                    question=q,
                    answer=ans_text,
                    retrieval_context=[contract],
                )
            except Exception:
                deepeval_res = None

        symbol = "✅ PASS" if is_cor else "❌ FAIL"
        print(f"{symbol} (pred={pred.upper()}, gold={gold.upper()}) in {lat_ms/1000.0:.2f}s | ${cost:.4f}")

        row = {
            "case_id": cid,
            "correct": is_cor,
            "pred": pred,
            "gold": gold,
            "question": q,
            "answer": ans_text,
            "citations": citations,
            "has_citation": len(citations) > 0,
            "latency_ms": lat_ms,
            "cost_usd": cost,
            "deepeval": deepeval_res,
        }
        rows.append(row)

        with out_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    total_time = time.perf_counter() - t_start
    n = len(rows)
    n_correct = sum(1 for r in rows if r["correct"])
    acc = (n_correct / n) * 100.0 if n else 0.0
    cited_count = sum(1 for r in rows if r["has_citation"])
    cite_rate = (cited_count / n) * 100.0 if n else 0.0

    p50_lat = statistics.median(latencies) / 1000.0 if latencies else 0.0
    p95_lat = statistics.quantiles(latencies, n=20)[18] / 1000.0 if len(latencies) >= 20 else p50_lat
    avg_cost = sum(costs) / n if n else 0.0

    # Faithfulness
    faiths = [
        r["deepeval"]["faithfulness"]
        for r in rows
        if r.get("deepeval") and "faithfulness" in r["deepeval"]
    ]
    avg_faith = (sum(faiths) / len(faiths)) * 100.0 if faiths else 100.0

    print("\n" + "=" * 65)
    print("📋 STANFORD LEGALBENCH (CONSUMER CONTRACTS QA) SCORECARD")
    print("=" * 65)
    print(f"Total Cases:          {n}")
    print(f"Overall Accuracy:     {acc:.1f}% ({n_correct}/{n})")
    print(f"Citation Rate:        {cite_rate:.1f}% ({cited_count}/{n})")
    print(f"Median Latency (p50): {p50_lat:.2f}s (p95: {p95_lat:.2f}s)")
    print(f"Average Cost / Query: ${avg_cost:.4f}")
    if faiths:
        print(f"DeepEval Faithfulness: {avg_faith:.1f}%")
    print(f"Total Suite Runtime:  {total_time:.1f}s")
    print(f"Scorecard JSONL:      {out_file}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
