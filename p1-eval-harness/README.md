# Agent Evaluation Harness — "Proving Ground"

> **Plug in any agent, any domain — get a reliability scorecard, with the
> failures included.**
>
> The numbers below were measured on 2026-08-31 against the sibling
> [`p3-rag-filings`](../p3-rag-filings) RAG system, on an all-free model
> stack (`minimax/minimax-m3:free`, $0.00 total cost).

95% of agent portfolios show demos. Demos hide failures. This is the harness
that finds them: audited golden datasets, a two-tier scoring engine
(deterministic ground truth + a calibrated LLM judge), full trajectory traces
per case, and regression diffs between runs.

## Headline results (measuring p3-rag-filings, all-free models)

> **Current hiring set: v1-50** (stratified 12/10/10/8/10 trim of the 80-case
> set — all ambiguous + edge cases kept). **Measured on v1-50 (2026-09-03):
> 96.0% (48/50)**; enterprise 95.6% (43/45, reproduced 2026-09-03). The
> stage ladder below was measured on frozen v1-80.

**50-case audited golden set** (`data/domain_a_financial/golden_set_v1.jsonl`, trimmed 2026-09-03 from the audited 80):

| System configuration | Accuracy |
|---|---|
| Retrieval-only (hybrid + rerank) | 53.8% |
| + fact-graph augmentation | 85.0% |
| + clarification & company-aware chunks | **92.5%** |

**45-case enterprise multi-hop set** (ratios, CAGR, cross-company comparisons,
trends — answers that live in no single chunk):

| System configuration | Accuracy |
|---|---|
| Retrieval-only (no graph) | 37.8% |
| + fact-graph augmentation | **84.4%** |

**External benchmarks:**
- **FinanceBench**: **84.0% (126/150)** in reasoning-over-evidence mode (official evidence excerpt provided; system grounds + verifies + computes on top of it; retrieval step isolated) — `scripts/benchmark_financebench.py`.
- **ConvFinQA**: **69.7% turn accuracy (129/185)** and **52.0% full conversation accuracy (26/50)** over chained arithmetic & follow-up dialogues with 0 JSON errors — `scripts/benchmark_convfinqa.py`.

**Judge calibration:** the G-Eval judge agrees with hand labels on
**45/52 = 86.5%** of cases (Cohen's kappa 0.669) — measured on 52
(question, system answer) pairs labeled by a human against the filing text,
not by another LLM; re-measured after the port at **88.5% / kappa 0.723**
(same labels, same free judge). Re-run with `scripts/calibrate_judge.py`;
labels in `data/domain_a_financial/judge_calibration_v1.jsonl`.

## How scoring works

Two tiers. Deterministic checks are ground truth; judge scores complement
them, they never replace them.

1. **Deterministic** — numeric-claim extraction with variation rules
   (`numeric_tolerance:x%`, `unit_equivalence` for $1.0B ≡ $1,000M), the
   refusal/unanswerable/ambiguity matrix, and citation/retrieval prefix hits.
2. **Calibrated LLM-judge** — DeepEval G-Eval factual equivalence for
   judge-type and ambiguous cases, plus faithfulness / answer-relevancy /
   contextual-precision on every answered case. All judge calls route through
   the harness's own OpenRouter client with a per-run cost ledger — eval
   overhead is measured, not hidden.

Every case also emits a full trajectory trace (retrieval, verification,
graph-rescue steps, final answer, usage) in the standard format
(`src/harness/traces/`), and every run dir pins its git sha + config snapshot
in `run_meta.json` so results are reproducible.

## Reproduce

The harness evaluates a target system through an adapter; the v1 financial
adapter runs `p3-rag-filings`. Install both packages into one venv:

```bash
# from the repo root
cd p3-rag-filings
uv venv && source .venv/bin/activate
uv pip install -e .
uv run python scripts/download_corpus.py   # 25 SEC 10-Ks
uv run ragfilings index                    # parse + chunk + embed
uv run ragfilings graph                    # fact graph

cd ../p1-eval-harness
uv pip install -e .
# add OPENROUTER_API_KEY to the repo-root .env
eval-harness run --strategy hybrid_rerank_graph --skip-judge-metrics
# -> accuracy + scorecards (md/png/html) + diff vs the latest baseline,
#    in reports/evals/<timestamp>-<sha8>-<strategy>/
```

Useful flags:

- `--golden-set data/domain_a_financial/golden_set_enterprise_v1.jsonl` — the
  multi-hop set (or a directory of `golden_set_*.jsonl`).
- `--limit N` — smoke runs.
- drop `--skip-judge-metrics` to also score faithfulness / relevancy /
  contextual precision (more judge calls).
- `eval-harness diff <baseline-run-dir> <current-run-dir>` — compare two runs.

Other benchmarks: `python scripts/benchmark_financebench.py` (downloads
FinanceBench, CC-BY-NC-4.0, on first use) and `python scripts/calibrate_judge.py`.

## Layout

```
p1-eval-harness/
  config.toml                     # judge model + settings
  data/domain_a_financial/        # audited golden sets + calibration labels + audit evidence
  src/harness/
    schema.py                     # frozen golden-case schema (strict on load)
    metrics/{engine,claims}.py    # deterministic scoring tier
    judge.py                      # calibrated DeepEval G-Eval judge + cost ledger
    runner.py / regress.py        # eval loop, run dirs, regression diffs
    report.py                     # md/png/html scorecards
    traces/                       # standard trajectory-trace format + builder
    adapters/ragfilings_adapter.py
  scripts/                        # judge calibration, FinanceBench benchmark
```

## Caveats, stated plainly

- **Free generation + free judge.** Both sides run on
  `minimax/minimax-m3:free`; run-to-run variance is a few cases. The
  deterministic wins (graph-rescued refusals, missing-year clarifications)
  are stable; single-run accuracy wobbles.
- **Judge-scored correctness** for judge-type cases is the G-Eval verdict
  against the expected answer — and the judge's own agreement with humans is
  published above (86.5%), not assumed.
- **Golden data is audited**: every answerable figure in the v1 and
  enterprise sets is proven against filing text (`audit_v1.json`, regenerate
  from P3 with `p3-rag-filings/scripts/audit_golden.py`).
- **Two adapters are wired** (financial + legal → ragfilings, `--domain
  financial|legal`). The legal pack runs the CUAD corpus on the same engine.
