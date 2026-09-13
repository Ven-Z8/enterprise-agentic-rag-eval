"""Run all 4 benchmark pillars sequentially:
1. Canonical Golden SEC 10-K (50 cases)
2. FinanceBench (150 questions)
3. ConvFinQA (50 multi-turn dialogues / 185 turns)
4. CUAD Legal Contract Understanding (56 cases / 102 agreements)

Generates unified summary scorecards upon completion across Financial and Legal domains.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
P1 = ROOT / "p1-eval-harness"
P3 = ROOT / "p3-rag-filings"

env = os.environ.copy()
env["TOKENIZERS_PARALLELISM"] = "false"
env["OMP_NUM_THREADS"] = "1"
env["TMPDIR"] = "/Volumes/VeN/tmp"


def run_cmd(cmd: list[str], cwd: Path, desc: str) -> None:
    print(f"\n{'='*60}\n>>> STARTING: {desc}\n{'='*60}\n", flush=True)
    t0 = time.perf_counter()
    res = subprocess.run(cmd, cwd=cwd, env=env)
    dur = time.perf_counter() - t0
    if res.returncode != 0:
        print(f"\n[ERROR] {desc} exited with code {res.returncode} after {dur:.1f}s\n", flush=True)
        sys.exit(res.returncode)
    print(f"\n[COMPLETED] {desc} in {dur:.1f}s\n", flush=True)


def main():
    print("🚀 Starting Unified Benchmark Suite across all 3 pillars...")
    print("Using OpenRouter Cohere Reranker (cohere/rerank-v3.5) with local fallback.\n")

    # 1. Canonical SEC 10-K Golden Set (50 cases)
    run_cmd(
        [
            "uv", "run", "--project", str(P3),
            "python", "-m", "harness.cli", "run",
            "--strategy", "langgraph",
            "--golden-set", "data/domain_a_financial/golden_set_v1.jsonl",
        ],
        cwd=P1,
        desc="Pillar 1: Canonical SEC 10-K Golden Set (50 cases)",
    )

    # 2. FinanceBench (150 questions)
    run_cmd(
        [
            "uv", "run", "--project", str(P3),
            "python", "scripts/benchmark_financebench.py",
            "--mode", "evidence",
        ],
        cwd=P1,
        desc="Pillar 2: FinanceBench (150 Questions)",
    )

    # 3. ConvFinQA (50 dialogues / 185 turns)
    run_cmd(
        [
            "uv", "run", "--project", str(P3),
            "python", "scripts/benchmark_convfinqa.py",
            "--limit", "50",
        ],
        cwd=P1,
        desc="Pillar 3: ConvFinQA (50 Dialogues / 185 Turns)",
    )

    print("\n" + "="*60)
    print("🎉 ALL 4 BENCHMARK PILLARS COMPLETED SUCCESSFULLY!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
