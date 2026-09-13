"""Run all unified multi-domain benchmark pillars:
1. Canonical Golden SEC 10-K (50 cases) — Financial Domain
2. CUAD Legal Contract Understanding (56 cases / 102 agreements) — Legal Domain
3. Stanford LegalBench Consumer Contracts QA (396 cases) — Legal Domain
4. Isaacus Legal RAG Bench (10 cases / 4,876 statutory passages) — Legal Domain
5. PubMedQA & PubChem Clinical Reasoning (50 cases) — Biomedical Domain

Generates unified summary scorecards upon completion across Financial, Legal, and Biomedical domains.

Usage:
  python scripts/run_all_benchmarks.py [--pillar {all,financial,cuad,legalbench,legalrag,biomedical}]
"""

from __future__ import annotations

import argparse
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
    ap = argparse.ArgumentParser(description="Unified Multi-Domain Benchmark Runner")
    ap.add_argument(
        "--pillar",
        choices=["all", "financial", "cuad", "legalbench", "legalrag", "biomedical"],
        default="all",
        help="Run specific benchmark pillar or all",
    )
    args = ap.parse_args()

    print("🚀 Starting Unified Multi-Domain Benchmark Suite...")
    print(f"Pillar Selection: {args.pillar}\n")

    # 1. Canonical SEC 10-K Golden Set (50 cases)
    if args.pillar in ("all", "financial"):
        run_cmd(
            [
                str(P3 / ".venv" / "bin" / "python"), "-m", "harness.cli", "run",
                "--strategy", "langgraph",
                "--golden-set", "data/domain_a_financial/golden_set_v1.jsonl",
            ],
            cwd=P1,
            desc="Pillar 1: Canonical SEC 10-K Financial Golden Set (50 cases)",
        )

    # 2. CUAD Legal Contract Understanding (56 cases)
    if args.pillar in ("all", "cuad", "legal"):
        run_cmd(
            [
                str(P3 / ".venv" / "bin" / "python"), "scripts/benchmark_cuad.py",
                "--strategy", "langgraph",
            ],
            cwd=P1,
            desc="Pillar 2: CUAD Legal Commercial Contracts (56 cases / 102 agreements)",
        )

    # 3. Stanford LegalBench (396 cases)
    if args.pillar in ("all", "legalbench"):
        run_cmd(
            [
                str(P3 / ".venv" / "bin" / "python"), "scripts/benchmark_legalbench.py",
                "--strategy", "langgraph",
            ],
            cwd=P1,
            desc="Pillar 3: Stanford LegalBench Consumer Contracts QA (396 cases)",
        )

    # 4. Isaacus Legal RAG Bench (10 cases)
    if args.pillar in ("all", "legalrag"):
        run_cmd(
            [
                str(P3 / ".venv" / "bin" / "python"), "scripts/benchmark_legalrag.py",
                "--strategy", "langgraph",
            ],
            cwd=P1,
            desc="Pillar 4: Isaacus Legal RAG Bench (10 cases / 4,876 statutory passages)",
        )

    # 5. PubMedQA & PubChem Biomedical Benchmark (50 cases)
    if args.pillar in ("all", "biomedical"):
        run_cmd(
            [
                str(P3 / ".venv" / "bin" / "python"), "scripts/benchmark_pubmedqa.py",
                "--strategy", "langgraph",
                "--skip-judge-metrics",
            ],
            cwd=P1,
            desc="Pillar 5: PubMedQA & PubChem Biomedical Benchmark (50 cases)",
        )

    print("\n" + "="*60)
    print("🎉 ALL SELECTED BENCHMARK PILLARS COMPLETED SUCCESSFULLY!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
