"""Scorecard generators: markdown + PNG metric scorecard, HTML case table.

write_scorecard() renders the metric comparison (md + png) from run results;
generate_reports() renders the self-contained HTML/Markdown per-case tables.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

CAVEAT = (
    "Golden set v1 (2026-09-03): 50 cases stratified across lookup / table / "
    "synthesis / unanswerable / ambiguous (12/10/10/8/10), trimmed from the "
    "audited 80-case set; every expected answer verified against filing text "
    "(see data/domain_a_financial/audit_v1.json). Judge = DeepEval G-Eval over "
    "OpenRouter; judge cost below is the eval overhead, separate from "
    "per-query generation cost."
)

CAVEAT_LEGAL = (
    "Golden set legal v1: 56 cases over 102 held-out CUAD commercial contracts "
    "(attorney-annotated spans; unanswerables are annotation-absent pairs). "
    "Judge = DeepEval G-Eval over OpenRouter; judge cost below is the eval "
    "overhead, separate from per-query generation cost."
)

_DOMAIN_META = {
    "financial": {
        "title": "Scorecard — RAG over SEC 10-K filings",
        "caveat": CAVEAT,
        "corpus": "25 filings",
    },
    "legal": {
        "title": "Scorecard — RAG over CUAD commercial contracts",
        "caveat": CAVEAT_LEGAL,
        "corpus": "102 contracts",
    },
}

_PCT_METRICS = [
    ("accuracy", "Answer accuracy"),
    ("retrieval_hit_rate", "Retrieval hit rate"),
    ("citation_faithfulness", "Citation faithfulness"),
    ("hallucination_rate", "Hallucination rate (unanswerable)"),
    ("refusal_correctness", "Refusal correctness"),
    ("deepeval_faithfulness", "DeepEval faithfulness"),
    ("deepeval_answer_relevancy", "DeepEval answer relevancy"),
    ("deepeval_contextual_precision", "DeepEval contextual precision"),
]


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0%}"


def _row(metrics: dict[str, Any], key: str) -> str:
    return _pct(metrics.get(key))


def write_scorecard(
    all_results: dict[str, dict[str, Any]],
    out_dir: str | Path,
    n_filings: int = 25,
    domain: str = "financial",
) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    strategies = list(all_results)
    md_path = out_dir / "scorecard.md"
    png_path = out_dir / "scorecard.png"

    meta = _DOMAIN_META.get(domain, _DOMAIN_META["financial"])
    first = all_results[strategies[0]]["metrics"]
    lines = [
        f"# {meta['title']}",
        "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M')} · {first['n']} golden "
        f"questions · {meta['corpus']} · generation model "
        f"`{first['model']}` · judge `{first['judge_model']}`*",
        "",
        f"> {meta['caveat']}",
        "",
        "| Metric | " + " | ".join(s.capitalize() for s in strategies) + " |",
        "|---|" + "---|" * len(strategies),
    ]
    for key, label in _PCT_METRICS:
        cells = " | ".join(_row(all_results[s]["metrics"], key) for s in strategies)
        lines.append(f"| {label} | {cells} |")
    for key, label, fmt in [
        ("refusal_rate", "Refusal rate", _pct),
        ("cost_per_query_usd", "Cost / query", lambda v: "—" if v is None else f"${v:.4f}"),
        ("latency_p50_ms", "Latency p50", lambda v: "—" if v is None else f"{v/1000:.1f}s"),
        ("latency_p95_ms", "Latency p95", lambda v: "—" if v is None else f"{v/1000:.1f}s"),
        ("judge_cost_usd", "Judge cost (eval overhead, total)", lambda v: "—" if v is None else f"${v:.3f}"),
    ]:
        cells = " | ".join(fmt(all_results[s]["metrics"].get(key)) for s in strategies)
        lines.append(f"| {label} | {cells} |")

    lines += ["", "## Accuracy by question category", ""]
    cats = sorted({c for s in strategies for c in all_results[s]["metrics"]["by_category"]})
    lines.append("| Category | " + " | ".join(f"{s.capitalize()} (n)" for s in strategies) + " |")
    lines.append("|---|" + "---|" * len(strategies))
    for cat in cats:
        cells = []
        for s in strategies:
            c = all_results[s]["metrics"]["by_category"].get(cat)
            cells.append(f"{c['accuracy']:.0%} ({c['n']})" if c else "—")
        lines.append(f"| {cat} | " + " | ".join(cells) + " |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _write_png(all_results, png_path)
    return md_path, png_path


def _write_png(all_results: dict[str, dict[str, Any]], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    strategies = list(all_results)
    labels = [label for _, label in _PCT_METRICS]
    fig, (ax, side) = plt.subplots(1, 2, figsize=(12, 5.0), width_ratios=[2.5, 1.0], dpi=150)
    x = np.arange(len(labels))
    width = 0.8 / max(len(strategies), 1)
    colors = ["#3b82f6", "#06b6d4", "#10b981", "#8b5cf6"]
    for i, s in enumerate(strategies):
        m = all_results[s]["metrics"]
        vals = [m.get(k) or 0.0 for k, _ in _PCT_METRICS]
        bars = ax.bar(x + i * width, vals, width, label=s, color=colors[i % len(colors)])
        ax.bar_label(bars, fmt="{:.0%}", fontsize=7.5, padding=2)
    ax.set_xticks(x + width * (len(strategies) - 1) / 2)
    ax.set_xticklabels([lb.replace(" (unanswerable)", "\n(unanswerable)") for lb in labels], fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.legend(frameon=False, fontsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    first = all_results[strategies[0]]["metrics"]
    ax.set_title(
        f"Strategy Comparison — {first['n']} Questions",
        fontsize=11,
        loc="left",
        fontweight="bold",
    )

    side.axis("off")
    txt = []
    for s in strategies:
        m = all_results[s]["metrics"]
        txt.append(
            f"{s.upper()}\n"
            f"  cost/query  ${(m.get('cost_per_query_usd') or 0):.4f}\n"
            f"  p50 latency {(m.get('latency_p50_ms') or 0)/1000:.1f}s\n"
            f"  p95 latency {(m.get('latency_p95_ms') or 0)/1000:.1f}s"
        )
    txt.append(f"model: {first['model']}")
    side.text(0.0, 0.95, "\n\n".join(txt), va="top", ha="left", fontsize=8.5, family="monospace", transform=side.transAxes)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Eval Harness Reliability Scorecard — {{ summary.strategy.upper() }}</title>
  <style>
    body { font-family: 'Inter', system-ui, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
    .container { max-width: 1100px; margin: 0 auto; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 24px; margin-bottom: 24px; }
    h1 { margin-top: 0; color: #38bdf8; }
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-top: 16px; }
    .stat-card { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 16px; text-align: center; }
    .stat-val { font-size: 28px; font-weight: 700; color: #10b981; }
    .stat-lbl { font-size: 12px; color: #94a3b8; margin-top: 4px; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 14px; }
    th, td { text-align: left; padding: 12px; border-bottom: 1px solid #334155; }
    th { background: #0f172a; color: #94a3b8; }
    .badge-pass { background: #064e3b; color: #34d399; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
    .badge-fail { background: #7f1d1d; color: #f87171; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1>🛡️ Agent Eval Harness Scorecard</h1>
      <p>Target Strategy: <strong>{{ summary.strategy.upper() }}</strong> | Evaluated Test Cases: <strong>{{ summary.n }}</strong></p>

      <div class="metric-grid">
        <div class="stat-card">
          <div class="stat-val">{{ "%.1f"|format(summary.accuracy * 100) }}%</div>
          <div class="stat-lbl">Overall Accuracy</div>
        </div>
        <div class="stat-card">
          <div class="stat-val" style="color: #38bdf8;">{{ summary.correct_count }} / {{ summary.n }}</div>
          <div class="stat-lbl">Passed Cases</div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>📋 Case Trajectory Results</h2>
      <table>
        <thead>
          <tr>
            <th>Case ID</th>
            <th>Outcome</th>
            <th>Query</th>
            <th>Latency</th>
          </tr>
        </thead>
        <tbody>
          {% for r in summary.results %}
          <tr>
            <td><code>{{ r.case_id }}</code></td>
            <td>
              {% if r.correct %}
                <span class="badge-pass">PASS</span>
              {% else %}
                <span class="badge-fail">FAIL</span>
              {% endif %}
            </td>
            <td>{{ r.trace.query }}</td>
            <td>{{ "%.1f"|format(r.trace.latency_ms / 1000) }}s</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""


def summary_from_rows(strategy: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the HTML-report summary shape from per-case result rows."""
    return {
        "strategy": strategy,
        "n": len(rows),
        "accuracy": (sum(bool(r["correct"]) for r in rows) / len(rows)) if rows else 0.0,
        "correct_count": sum(bool(r["correct"]) for r in rows),
        "results": [
            {
                "case_id": r["case_id"],
                "correct": bool(r["correct"]),
                "outcome": r.get("outcome", ""),
                "trace": {"query": r.get("input", ""), "latency_ms": r.get("latency_ms", 0.0)},
            }
            for r in rows
        ],
    }


def generate_reports(summary: dict[str, Any], out_dir: str | Path) -> tuple[Path, Path]:
    """Generate HTML and Markdown scorecard reports."""
    from jinja2 import Template

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html_path = out_dir / f"scorecard_{summary['strategy']}.html"
    md_path = out_dir / f"scorecard_{summary['strategy']}.md"

    tmpl = Template(HTML_TEMPLATE)
    html_content = tmpl.render(summary=summary)
    html_path.write_text(html_content, encoding="utf-8")

    md_lines = [
        f"# Eval Harness Scorecard — {summary['strategy'].upper()}",
        "",
        f"*Evaluated {summary['n']} Golden Cases | Accuracy: **{summary['accuracy']:.1%}** ({summary['correct_count']}/{summary['n']})*",
        "",
        "| Case ID | Status | Outcome | Latency |",
        "|---|---|---|---|",
    ]
    for r in summary["results"]:
        status = "✅ PASS" if r["correct"] else "❌ FAIL"
        md_lines.append(f"| `{r['case_id']}` | {status} | {r['outcome']} | {r['trace']['latency_ms']/1000:.1f}s |")

    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return html_path, md_path
