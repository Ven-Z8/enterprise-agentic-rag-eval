"""Judge calibration: measure the DeepEval judge's agreement with hand labels.

Publish how often the judge agrees with a human reading of the same
(question, system answer) pairs. This script re-runs the judge's G-Eval
correctness verdict on every labeled pair and reports agreement.

Labels live in data/domain_a_financial/judge_calibration_v1.jsonl (one JSON
object per pair):
  case_id, input, expected_answer, actual_output, human_label (correct |
  incorrect), evidence (what the labeler checked). Labels were written by
  the portfolio author against the filing text, not by another LLM.

Usage: uv run python scripts/calibrate_judge.py
Writes reports/judge_calibration_v1.md and prints the summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from harness import config as cfg_mod  # noqa: E402
from harness.judge import DeepEvalScorer  # noqa: E402

LABELS = ROOT / "data" / "domain_a_financial" / "judge_calibration_v1.jsonl"
OUT = ROOT / "reports" / "judge_calibration_v1.md"


def cohens_kappa(pairs: list[tuple[bool, bool]]) -> float:
    """kappa for two binary raters over (human, judge) verdict pairs."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    po = sum(h == j for h, j in pairs) / n
    ph = sum(h for h, _ in pairs) / n
    pj = sum(j for _, j in pairs) / n
    pe = ph * pj + (1 - ph) * (1 - pj)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def main() -> None:
    cfg = cfg_mod.load()
    labels = [json.loads(line) for line in LABELS.open(encoding="utf-8") if line.strip()]
    scorer = DeepEvalScorer(cfg)

    rows = []
    for i, item in enumerate(labels, 1):
        case = {
            "id": item["case_id"],
            "input": item["input"],
            "expected": {"answer": item["expected_answer"], "citations": [], "type": "judge"},
            "variation_rules": [],
            "difficulty": item.get("difficulty", "medium"),
            "failure_category": item.get("failure_category", "synthesis"),
            "notes": item.get("notes", ""),
        }
        result = {"answer": item["actual_output"], "hits": item.get("hits", [])}
        verdict = scorer.correctness(case, result)
        judge_label = "correct" if verdict["correct"] else "incorrect"
        rows.append(
            {
                **item,
                "judge_label": judge_label,
                "judge_score": verdict["score"],
                "judge_reason": verdict["reason"],
                "agree": item["human_label"] == judge_label,
            }
        )
        mark = "=" if rows[-1]["agree"] else "X"
        print(
            f"[{i:>2}/{len(labels)}] {mark} {item['case_id']} "
            f"human={item['human_label']} judge={judge_label}",
            flush=True,
        )

    n = len(rows)
    agree = sum(r["agree"] for r in rows)
    pairs = [(r["human_label"] == "correct", r["judge_label"] == "correct") for r in rows]
    tp = sum(h and j for h, j in pairs)
    fp = sum(not h and j for h, j in pairs)
    fn = sum(h and not j for h, j in pairs)
    tn = sum(not h and not j for h, j in pairs)
    kappa = cohens_kappa(pairs)

    lines = [
        "# Judge calibration v1 — DeepEval G-Eval vs hand labels",
        "",
        f"- judge: `{scorer.judge.get_model_name()}` (OpenRouter, temperature 0)",
        f"- labeled pairs: {n} (golden/judge_calibration_v1.jsonl)",
        "- labels: written by the portfolio author against the filing text",
        "",
        "## Headline numbers",
        "",
        f"- **agreement (accuracy): {agree}/{n} = {agree / n:.1%}**",
        f"- **Cohen's kappa: {kappa:.3f}**",
        "",
        "| human \\ judge | correct | incorrect |",
        "|---|---|---|",
        f"| correct | {tp} | {fn} |",
        f"| incorrect | {fp} | {tn} |",
        "",
        "## Disagreements",
        "",
    ]
    for r in rows:
        if r["agree"]:
            continue
        lines += [
            f"### {r['case_id']} — human: {r['human_label']}, judge: {r['judge_label']} "
            f"(score {r['judge_score']})",
            f"- Q: {r['input']}",
            f"- expected: {r['expected_answer']}",
            f"- actual: {r['actual_output'][:400]}",
            f"- human evidence: {r['evidence']}",
            f"- judge reason: {r['judge_reason']}",
            "",
        ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nagreement {agree}/{n} = {agree / n:.1%} | kappa {kappa:.3f} -> {OUT}")


if __name__ == "__main__":
    main()
