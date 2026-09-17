"""Regression runner: one command, timestamped run dirs, diff vs baseline.

Layout under reports/evals/:
  <timestamp>-<gitsha8>-<strategy>/
      results_<strategy>.jsonl    per-case scores
      traces/<strategy>/<id>.json full agent traces
      run_meta.json               git sha + config snapshot
      scorecard.md / .png         metric scorecard
      scorecard_<strategy>.html   interactive case table
      diff_report.md              comparison against the baseline run (if any)

A run is reproducible: run_meta.json pins the git sha, generation/judge
models, retrieval config, and the golden set path.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from harness.runner import git_sha, run_eval


def latest_run(out_root: Path) -> Path | None:
    runs = sorted(d for d in out_root.glob("*/results_*.jsonl") if d.is_file())
    if not runs:
        return None
    return runs[-1].parent


def load_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(run_dir.glob("results_*.jsonl")):
        with path.open(encoding="utf-8") as f:
            rows.extend(json.loads(line) for line in f if line.strip())
    return rows


def _aggregate_view(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_cat: dict[str, dict[str, int]] = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], {"n": 0, "correct": 0})
        c["n"] += 1
        c["correct"] += bool(r["correct"])
    for c in by_cat.values():
        c["accuracy"] = c["correct"] / c["n"]
    cost = [(r.get("cost_usd") or 0.0) for r in rows]
    return {
        "n": len(rows),
        "accuracy": sum(bool(r["correct"]) for r in rows) / len(rows) if rows else None,
        "cost_total_usd": sum(cost),
        "by_category": by_cat,
    }


def diff_runs(base_dir: Path, new_dir: Path) -> dict[str, Any]:
    """Per-case and per-category comparison of two runs."""
    base = {r["case_id"]: r for r in load_rows(base_dir)}
    new = {r["case_id"]: r for r in load_rows(new_dir)}
    common = sorted(set(base) & set(new))

    improved, regressed = [], []
    for cid in common:
        b, n = base[cid], new[cid]
        if n["correct"] and not b["correct"]:
            improved.append(cid)
        elif b["correct"] and not n["correct"]:
            regressed.append(cid)

    return {
        "baseline": base_dir.name,
        "current": new_dir.name,
        "common_cases": len(common),
        "improved": improved,
        "regressed": regressed,
        "baseline_view": _aggregate_view([base[c] for c in common]),
        "current_view": _aggregate_view([new[c] for c in common]),
    }


def _md_table(view: dict[str, Any]) -> str:
    lines = ["| Category | n | Accuracy |", "|---|---|---|"]
    for cat in sorted(view["by_category"]):
        c = view["by_category"][cat]
        lines.append(f"| {cat} | {c['n']} | {c['accuracy']:.0%} |")
    lines.append(f"| **overall** | {view['n']} | {(view['accuracy'] or 0):.0%} |")
    return "\n".join(lines)


def write_diff_report(diff: dict[str, Any], out_path: Path) -> None:
    lines = [
        "# Regression diff",
        "",
        f"baseline: `{diff['baseline']}` → current: `{diff['current']}` "
        f"({diff['common_cases']} common cases)",
        "",
        f"- improved: {len(diff['improved'])}"
        + (f" — {', '.join(diff['improved'])}" if diff["improved"] else ""),
        f"- regressed: {len(diff['regressed'])}"
        + (f" — {', '.join(diff['regressed'])}" if diff["regressed"] else ""),
        "",
        "## Baseline",
        "",
        _md_table(diff["baseline_view"]),
        "",
        "## Current",
        "",
        _md_table(diff["current_view"]),
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def run_regression(
    cfg: dict[str, Any],
    adapter: Any,
    golden_set: str | Path,
    strategy: str,
    out_root: str | Path = "reports/evals",
    limit: int | None = None,
    baseline: str | None = None,
    skip_judge_metrics: bool = False,
    run_dir: str | Path | None = None,
) -> tuple[Path, dict[str, Any] | None, dict[str, Any]]:
    """Run the suite into a fresh timestamped dir and diff against baseline.

    baseline: a run dir name under out_root, or None to auto-pick the latest
    existing run. Returns (run_dir, diff_or_None, all_results).
    """
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    baseline_dir = None
    if baseline:
        candidate = out_root / baseline
        if not candidate.exists():
            raise FileNotFoundError(f"baseline run not found: {candidate}")
        baseline_dir = candidate
    else:
        baseline_dir = latest_run(out_root)

    if run_dir is not None:
        target_run_dir = Path(run_dir)
        if not target_run_dir.is_absolute():
            target_run_dir = out_root / target_run_dir
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target_run_dir = out_root / f"{stamp}-{git_sha()[:8]}-{strategy}"

    all_results = run_eval(
        cfg,
        adapter,
        golden_set,
        [strategy],
        out_dir=target_run_dir,
        limit=limit,
        skip_judge_metrics=skip_judge_metrics,
    )

    diff = None
    if baseline_dir is not None and baseline_dir != target_run_dir:
        diff = diff_runs(baseline_dir, target_run_dir)
        write_diff_report(diff, target_run_dir / "diff_report.md")
    return target_run_dir, diff, all_results
