# P1 — Domain-Adaptive Agent Eval Harness ("Proving Ground")

Read BUILD_BRIEF.md before writing any code. This is the portfolio centerpiece
and open-source play. Positioning: *"Plug in any agent, any domain — get a
reliability scorecard in an afternoon."*

## What this project is

A framework that takes (a) an agent system, (b) a domain-specific golden
dataset, (c) a metric configuration — and produces a full evaluation report
with regression tracking.

## Non-negotiable constraints (scope discipline)

- NO web UI beyond the generated HTML report. CLI + config files is more credible.
- NO support for every framework. Adapters for exactly two: raw API calls + one
  popular agent framework — with a documented adapter interface for others.
- NO hosted SaaS version. Resist completely.
- LLM-as-judge MUST be calibrated: hand-label 50 cases, measure judge agreement,
  publish the agreement number even if it's mediocre. Honesty sells.

## Tech conventions

- Python 3.11+, uv, ruff. Library-first design: `pip install`able, CLI on top.
- Golden dataset format: JSONL, one test case per line
  (input, expected outcome, acceptable-variation rules, difficulty tag, failure-category tag).
- Traces: full agent runs stored as structured JSON (every tool call, reasoning
  step, retry) — replayable and diffable.
- Config-driven metric selection; metrics are pluggable classes.

## Architecture (core engine, weeks 1–2 of P1 scope)

1. **Golden dataset toolkit** — schema + semi-automated dataset builder
   (raw domain docs in → drafted candidate test cases → human approves/edits).
2. **Trajectory capture** — record full runs as structured JSON traces.
3. **Metric layer, three tiers:**
   - Deterministic: exact match, schema validation, tool-call correctness, constraint satisfaction.
   - Statistical/retrieval: precision/recall vs golden citations, latency p50/p95, cost per task.
   - LLM-as-judge: faithfulness/helpfulness/tone, with calibration workflow built in.
4. **Regression runner** — one command re-runs the suite vs a new agent version,
   produces diff report per failure category, stores history for trend charts.
5. **Report generator** — HTML/markdown scorecard: pass rate, per-category
   breakdown, cost/latency, worst 10 failures with full trajectories, trend chart.

## Definition of done

- A stranger clones the repo, runs one command, reproduces the legal-domain eval report.
- README shows the scorecard image in the first screen-scroll.
- One deep-dive post published: "I evaluated the same agent architecture across
  3 domains. Here's where it silently failed."
- Calibrated judge agreement number is published.

## Dependency

P3 (../p3-rag-filings) is the system under test for the financial domain pack.
The golden set format was designed FIRST and shared with P3, so its golden set
drops in unchanged — that is now the canonical data in
`data/domain_a_financial/`.

## Current state (2026-08-31)

Phase 0 + Phase 1 core + the financial domain pack are done. The entire
evaluation stack moved here from P3 on 2026-08-31 (P3 is now pure RAG):

- **Data** (`data/domain_a_financial/`): `golden_set_v1.jsonl` (50 cases —
  stratified 12/10/10/8/10 trim of the audited 80, 2026-09-03),
  `golden_set_enterprise_v1.jsonl` (45 multi-hop cases),
  `judge_calibration_v1.jsonl` (52 hand-labeled judge pairs), `audit_v1.json`
  (provenance evidence, 95 entries: 50 v1 + 45 enterprise). Golden builders stay in P3 (they need its corpus)
  and write into this directory. Published stage figures are frozen on v1-80
  until the paid-model re-run.
- **Scoring** (`src/harness/metrics/`): two-tier — deterministic numeric
  matching with variation rules + refusal/ambiguity matrix (`engine.py`),
  complemented by calibrated DeepEval G-Eval judge (`src/harness/judge.py`,
  judge model in `config.toml`, all calls through the harness's own
  OpenRouter client with cost ledger).
- **Runner** (`runner.py`, `regress.py`): timestamped run dirs
  (`reports/evals/<stamp>-<sha8>-<strategy>/`) with per-case traces,
  `run_meta.json`, scorecards (md/png/html), and diff vs the latest baseline.
  Circuit breaker aborts after 5 consecutive case failures.
- **Adapter**: `adapters/ragfilings_adapter.py` runs P3's `ask()` pipeline
  and returns the raw result dict unchanged (answer, citations, hits,
  verification, graph_rescue, usage). Adapters for other domains
  (legal/biomedical/support) exist but are not wired into the v1 CLI.
- **CLI**: `eval-harness run --strategy hybrid_rerank_graph
  [--skip-judge-metrics] [--limit N]` and `eval-harness diff BASE NEW`.
  Requires `ragfilings` installed in the same venv (or a sibling checkout).
- **Scripts**: `scripts/calibrate_judge.py` (judge agreement vs hand labels),
  `scripts/benchmark_financebench.py` (external benchmark, `--mode evidence`
  reasoning-over-evidence / `--mode retrieval` end-to-end),
  `scripts/build_financebench_corpus.py` (downloads FinanceBench's filings —
  EDGAR-first with fiscal-calendar period matching, HTML + PDF parsing —
  chunks + indexes them for retrieval mode).
- **Measured results on P3** (all-free models): golden v1 53.8% →
  92.5% (+graph +clarification), enterprise 37.8% → 84.4%. Write-ups live in
  P3's `docs/` (they document P3's system results).
