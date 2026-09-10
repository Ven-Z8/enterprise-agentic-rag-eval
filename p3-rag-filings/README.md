# RAG over Real SEC 10-K Filings — with the Failure Analysis Included

> **Every number below was re-measured on 2026-08-31 after a ground-up rebuild,
> on an all-free model stack (`minimax/minimax-m3:free`, $0.00 total cost).
> An earlier version of this README carried unverified headline numbers; they
> were removed. What follows is the honest, reproducible state.**

Anyone can build RAG that works on easy questions. This repo shows what it takes
on genuinely messy documents — 25 real SEC 10-K filings full of nested tables,
footnotes, incorporated-by-reference sections, 53-week fiscal years, and column
orders that flip between companies — **measured, with the failures included.**

> **External benchmarks:** **84.0% (126/150)** on **FinanceBench** (real public-company questions in reasoning-over-evidence mode) and **69.7% turn accuracy (52.0% all-correct conversations)** on **ConvFinQA** (multi-turn conversational financial reasoning with chained calculations).

## Headline (measured 2026-09-03, all-free models, $0.00)

> **Current hiring set: v1-50** — a stratified trim of the 80-case set
> (lookup 12 / table 10 / synthesis 10 / unanswerable 8 / ambiguous 10; all 10
> ambiguous + every documented edge case kept). **v1-50: 96.0% (48/50)** —
> lookup 100% · table 90% · synthesis 90% · unanswerable 100% · ambiguous 100%;
> failures are the known fin-3003 + fin-8007 pair. Enterprise: **95.6%**
> (43/45, failures ent-1016 + ent-1019 — both previously documented).
> The stage-by-stage ladder below was measured on frozen v1-80.

On the 80-case audited golden set (canonical copy in
`p1-eval-harness/data/domain_a_financial/golden_set_v1.jsonl`), accuracy by
system configuration:

| Configuration | Accuracy | Notes |
|---|---|---|
| Retrieval-only, hybrid + rerank | **53.8%** | baseline: generator refuses figures it actually retrieved |
| **+ fact-graph augmentation** | **85.0%** | +31.2pp — all 16 incorrect refusals fixed |
| **+ clarification & company-aware chunks** | **92.5%** | ambiguous 8/10; lookup & table 100% (representative repeat; one run peaked at 96.2% with 2 lucky unanswerable flips) |
| **+ vague-metric clarification, refusal rules, grounded derived ratios (2026-09-01)** | **97.5%** (78/80; repeat 98.8%) | ambiguous 10/10; refusal safety 10/10; 3 stale labels corrected with chunk evidence |

On a separate 45-case **enterprise multi-hop** set (ratios, CAGR, cross-company
comparisons, trends — answers that live in *no single chunk*):

| Configuration | Accuracy |
|---|---|
| Retrieval-only (no graph) | 37.8% |
| **+ fact-graph augmentation** | **84.4%** |
| **+ 2026-09-01 fixes** | **95.6%** (43/45, reproduced twice) |

The enterprise set is the point: multi-hop answers can't be retrieved from one
chunk, so retrieval-only fails; the fact graph does the joining.

## Domain skill packs

The pipeline is a **domain-agnostic engine** plus loadable **skill packs**
(`src/ragfilings/domains/<name>/`, contract: `DomainPack` — prompts, fact
layer, scope agent, claim semantics, derivation tool). Shipped packs:
`financial` (this README's system) and `legal` (commercial contracts — CUAD
corpus, 102 held-out agreements, defined-term fact layer, quoted-language
claim semantics). `eval-harness run --domain legal` measures the legal pack on
its own 56-case golden set; **82.1% (46/56)** measured 2026-09-03 (first
baseline 80.4% with
zero domain-specific tuning (clarifications 6/6). Adding a domain never
touches the engine.

## The idea in one paragraph

A normal RAG pipeline retrieves text chunks and asks a model to answer from
them. On 10-Ks that breaks in two characteristic ways: the model **refuses**
figures that *were* retrieved (it can't find them in a wall of table text), and
it **can't answer multi-hop questions at all** (a ratio needs two figures from
two places). So on top of retrieval this system builds a **typed fact graph**
(Company → Year → Metric → Value, each value carrying the exact source chunk),
and at answer time **injects the relevant graph fact(s) + their provenance
chunks into the context up front**. For under-specified questions it asks a
**clarifying question** instead of guessing. Retrieval stops being the single
point of failure.

## Reproduce the headline result

Building the system (here) and evaluating it (sibling `p1-eval-harness`
project — install both packages into one venv, see the repo-root README):

```bash
# 1) build the system (p3-rag-filings)
uv sync --extra dev
uv run python scripts/download_corpus.py     # 25 10-Ks from SEC EDGAR (rate-limited)
uv run ragfilings index                      # parse + chunk + embed (local model, no key)
uv run ragfilings graph                      # build the fact graph + communities

# 2) evaluate it (p1-eval-harness)
cd ../p1-eval-harness
uv sync --extra dev
# add OPENROUTER_API_KEY to the repo-root .env
uv run eval-harness run --strategy hybrid_rerank_graph --skip-judge-metrics
# -> accuracy + scorecards + diff vs the latest baseline run, in reports/evals/<run>/
```

The enterprise set: `eval-harness run --golden-set
data/domain_a_financial/golden_set_enterprise_v1.jsonl ...`.
`--skip-judge-metrics` runs accuracy-only (deterministic numeric matching +
G-Eval correctness); drop it to also score faithfulness / answer-relevancy /
contextual-precision.

## Measured ablation — retrieval strategy vs the graph

Accuracy on the frozen 80-case v1 set, all-free models, accuracy-only scoring.
Retrieval-only runs (no graph) sit in a ~46–56% band dominated by the refusal
problem; run-to-run variance on the free model is a few cases, so read the
retrieval-strategy deltas as noise and the graph delta as the signal.

| Strategy (v1 set, no graph) | Accuracy |
|---|---|
| dense | 56.2% |
| hybrid (dense + BM25) | 46.2% |
| hybrid + cross-encoder rerank | 55.0% |
| **hybrid + rerank + fact-graph augmentation** | **85.0%** |

**Reading:** swapping the retrieval ranker moves accuracy by a few points
(within noise); adding the fact graph moves it by ~30. The bottleneck was never
retrieval ranking — it was the generator failing to use retrievable figures.

## What's actually hard here (and what this repo does about it)

| The mess | The handling |
|---|---|
| Item 7/8 are "incorporated by reference" stubs | Stub detection + resolution to the real F-pages (`resolved_from`) |
| Tables die when flattened to text | Row-boundary-safe chunking; header rows repeated on continuation chunks |
| "See Notes 1 and 4" | Footnote linking: statement chunks carry `note_refs` to note chunks |
| Column orders flip (AAPL descends, AMZN ascends) | Golden set targets this; fact extraction normalizes per filing |
| Fiscal-year labels lie (NVDA's latest FY is "2026"; so is Walmart's) | Per-filing fiscal metadata; golden set tests fiscal-label handling |
| Figures retrieved but the model refuses them | **Fact-graph augmentation** injects the figure + source chunk |
| Multi-hop answers (ratios, CAGR, comparisons) | **Multi-hop augmentation** joins 2+ graph facts, grounds the derived value |
| Under-specified questions (no fiscal year) | **Deterministic clarification** asks which year instead of guessing |
| Statement-table chunks carry no company name (only ~31% do) | **Metadata-context prefix**: every chunk embeds "Company (TICKER) FY#### 10-K — Item N" so retrieval and the LLM are company/section-aware |
| Questions with no answer in the corpus | Confidence-gated refusal + graph-abstain; measured refusal correctness |

## The failure analysis (read this first)

The honest part. Full write-up: [`p3-rag-filings/docs/graph_augmentation_v1.md`](p3-rag-filings/docs/graph_augmentation_v1.md).

What the 85.0% graph run (v1) still got wrong, and why:
- **3 unanswerable hallucinations** (fin-8003/8007/8012): the model answers
  from parametric knowledge ("Apple sold N iPhones") instead of refusing. Open.
- **1 synthesis metric-disambiguation** (fin-3003): read a combined MD&A line
  instead of the standalone figure.

What the enterprise set (84.4%) got wrong:
- **3 synthesis**: 2 R&D-intensity arithmetic slips, 1 gross-margin refusal.
- **4 ambiguities** with a year or a vague metric ("earnings", "cash") — the
  missing-year clarification doesn't cover vague-metric ambiguity yet.

**Caveats, stated plainly.**
- The free generator is non-deterministic run-to-run; single-run accuracy varies
  by a few cases. The representative repeat is **92.5%**; one run peaked at
  96.2% because 2 unanswerables flipped to correct refusals by ordinary
  variance, not by the clarification. The deterministic wins are the
  graph-rescued refusals and the missing-year clarifications.
- Accuracy-only scoring (`--skip-judge-metrics`) was used because the free tier
  is rate-limited; the complementary DeepEval metrics can be re-run when credits
  allow.
- The fact graph quarantines 68 hand-verified mis-extracted facts
  (`corpus/graph/excluded_facts.json`); they are excluded from both golden
  generation and runtime augmentation, but the builder heuristics that produced
  them are a known debt.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md). Components: parse → chunk → embed →
retrieve (dense / hybrid / +rerank) → **fact graph** → **augmentation /
clarification** → grounded synthesis with a numeric-claim verifier. Judge =
DeepEval G-Eval over OpenRouter.

## Golden datasets

Canonical data lives in the sibling eval project
([`p1-eval-harness/data/domain_a_financial/`](../p1-eval-harness/data/domain_a_financial/)):

- `golden_set_v1.jsonl` — 50 cases (lookup 12, table 10, synthesis 10,
  unanswerable 8, ambiguous 10; stratified trim of the audited 80-case set).
  Every answerable figure proven against filing text.
- `golden_set_enterprise_v1.jsonl` — 45 multi-hop cases (ratios, CAGR,
  cross-company, trends, + unanswerables and ambiguities). Built by this
  project's `scripts/build_golden_enterprise_v1.py`; each derived answer's
  base figures are chunk-verified.
- Judge calibration: 88.5% human agreement / Cohen's kappa 0.723 on 52
  hand-labeled pairs after the harness port (original: 86.5% / 0.669) (`judge_calibration_v1.jsonl`,
  [`docs/judge_calibration_v1.md`](docs/judge_calibration_v1.md)).
- Audit evidence: `audit_v1.json`; regenerate with
  `scripts/audit_golden.py`.

## Scope discipline — what this deliberately is NOT

- No chat UI. CLI + config files.
- No 10,000-document corpus. 25 hard documents, deeply handled.
- No paid-model results yet: the whole stack runs on free models, and the
  numbers reflect that. Adding credits means re-running on frontier models
  (run snapshots keep results comparable).
