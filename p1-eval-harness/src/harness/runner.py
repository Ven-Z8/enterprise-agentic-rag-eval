"""Evaluation runner: golden cases × strategies → scorecard + traces.

Executes each golden case through the adapter, scores it with the two-tier
engine (deterministic + calibrated LLM-judge), records a full trajectory
trace per case, and writes results JSONL + run metadata. A run is
reproducible: run_meta.json pins the git sha, generation/judge models,
target retrieval config, and the golden set path.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from harness.metrics.engine import aggregate, load_cases, score_case
from harness.traces.build import build_trace


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _run_meta(
    cfg: dict[str, Any],
    adapter: Any,
    golden_path: str | Path,
    strategies: list[str],
    judge_model: str,
) -> dict[str, Any]:
    target_cfg = getattr(adapter, "cfg", None) or {}
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_sha": git_sha(),
        "golden_set": str(golden_path),
        "strategies": strategies,
        "adapter": getattr(adapter, "name", type(adapter).__name__),
        "generation_model": getattr(adapter, "model_name", None)
        or target_cfg.get("generation", {}).get("model"),
        "judge_model": judge_model,
        "retrieval": target_cfg.get("retrieval", {}),
        "verification": target_cfg.get("verification", {}),
    }


def run_eval(
    cfg: dict[str, Any],
    adapter: Any,
    golden_path: str | Path,
    strategies: list[str],
    out_dir: str | Path = "reports",
    limit: int | None = None,
    skip_judge_metrics: bool = False,
) -> dict[str, Any]:
    """Run the golden suite across retrieval strategies.

    `skip_judge_metrics=True` omits the complementary DeepEval metrics
    (faithfulness / relevancy / contextual precision) for a faster
    accuracy-focused run; deterministic scoring + G-Eval correctness still run.
    """
    from harness.judge import DeepEvalScorer

    cases = load_cases(golden_path)[:limit]
    scorer = DeepEvalScorer(cfg)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = _run_meta(cfg, adapter, golden_path, strategies, scorer.judge.get_model_name())
    if skip_judge_metrics:
        meta["deepeval_metrics"] = "skipped (accuracy-focused run)"
    (out_dir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    all_results: dict[str, Any] = {}

    for strategy in strategies:
        trace_dir = out_dir / "traces" / strategy
        trace_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        results_path = out_dir / f"results_{strategy}.jsonl"
        existing_rows: list[dict[str, Any]] = []
        if results_path.exists():
            try:
                for line in results_path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        existing_rows.append(json.loads(line))
            except Exception:
                existing_rows = []

        seen_completed_ids = {r["case_id"] for r in existing_rows}
        rows = list(existing_rows)

        with results_path.open("a" if existing_rows else "w", encoding="utf-8") as results_f:
            consecutive_errors = 0
            for i, case in enumerate(cases, 1):
                if case["id"] in seen_completed_ids:
                    continue

                t0 = time.perf_counter()
                result = None
                try:
                    result = adapter.run_case(
                        case, strategy=strategy, refusal_log=out_dir / "refusals.jsonl"
                    )
                    scored = score_case(
                        case, result, cfg, scorer=scorer,
                        include_deepeval_metrics=not skip_judge_metrics,
                    )
                    consecutive_errors = 0
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    scored = {
                        "case_id": case["id"],
                        "category": case["failure_category"],
                        "difficulty": case.get("difficulty"),
                        "refused": False,
                        "citation_hit": None,
                        "retrieval_hit": None,
                        "judge_reason": None,
                        "judge_score": None,
                        "deepeval": None,
                        "correct": False,
                        "outcome": "error",
                        "error": f"{type(e).__name__}: {e}"[:400],
                    }
                    result = {
                        "latency_ms": result.get("latency_ms", elapsed_ms) if result else elapsed_ms,
                        "usage": result.get("usage", {"cost_usd": None}) if result else {"cost_usd": None},
                        "verification": {"verified": False},
                        "answer": result.get("answer") if result else None,
                        "refusal_reason": None,
                        "citations": result.get("citations", []) if result else [],
                    }
                    consecutive_errors += 1

                trace = build_trace(case, result)
                (trace_dir / f"{case['id']}.json").write_text(
                    json.dumps(trace, indent=2, ensure_ascii=False, default=str)
                )

                row = {
                    **scored,
                    "input": case["input"],
                    "latency_ms": result.get("latency_ms", 0.0),
                    "cost_usd": result.get("usage", {}).get("cost_usd"),
                    "verified": bool(result.get("verified", result.get("verification", {}).get("verified", False))),
                    "answer": result.get("answer"),
                    "refusal_reason": result.get("refusal_reason"),
                    "citations": result.get("citations", []),
                    "rescued": bool((result.get("graph_rescue") or {}).get("rescued")),
                }
                rows.append(row)
                results_f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                results_f.flush()

                # Flush partial-run manifest
                manifest = {
                    "strategy": strategy,
                    "total_cases": len(cases),
                    "completed": [r["case_id"] for r in rows if r.get("outcome") != "error"],
                    "failed": [r["case_id"] for r in rows if r.get("outcome") == "error"],
                    "unattempted": [c["id"] for c in cases if c["id"] not in {r["case_id"] for r in rows}],
                    "consecutive_errors": consecutive_errors,
                    "status": "aborted" if consecutive_errors >= 5 else ("completed" if len(rows) == len(cases) else "in_progress"),
                }
                (out_dir / f"manifest_{strategy}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

                mark = "+" if scored["correct"] else "-"
                print(f"[{strategy} {i:>2}/{len(cases)}] {mark} {case['id']} {scored['outcome']}", flush=True)

                if consecutive_errors >= 5:
                    raise RuntimeError(
                        "5 consecutive case failures — aborting run "
                        f"(last error: {scored.get('error')})"
                    )

        metrics = aggregate(rows)
        metrics.update(scorer.judge.ledger.to_dict())
        metrics["model"] = getattr(adapter, "model_name", "") or meta["generation_model"]
        metrics["judge_model"] = scorer.judge.get_model_name()
        metrics["error_count"] = sum(1 for r in rows if r["outcome"] == "error")
        all_results[strategy] = {"metrics": metrics, "rows": rows}
        acc = metrics.get("accuracy") or 0.0
        suffix = f" errors={metrics['error_count']}" if metrics["error_count"] else ""
        print(f"[{strategy}] accuracy={acc:.1%} n={metrics['n']}{suffix}", flush=True)

    return all_results
