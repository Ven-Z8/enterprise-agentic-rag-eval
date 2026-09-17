# FinanceBench — external benchmark run (v1, 2026-08-31)

**Result: 122/150 = 81.3%** in *reasoning-over-evidence* mode, all-free models
(`minimax/minimax-m3:free` for generation + judging), $0.00 cost. 17 of the 150
were answered as refusals.

## What FinanceBench is

FinanceBench (Patronus AI) is an open suite of 150 questions about publicly
traded companies, grounded in real 10-K / 10-Q / 8-K / earnings documents. It
is intended as a minimum performance standard for financial QA. Each record
carries the question, the official answer, and the evidence excerpt (+ page)
the answer comes from. License: CC-BY-NC-4.0 (the dataset is downloaded at
runtime, not committed).

## How we ran it (reasoning-over-evidence)

FinanceBench references filings *outside* this repo's 25-filing corpus, and
those sources are PDFs (our ingestion parses HTML 10-Ks). So this v1 run does
**reasoning-over-evidence**: each question is given its official evidence
excerpt as the retrieved context, and the pipeline runs grounded synthesis +
numeric-claim verification + financial math on top. The fact graph is
deliberately disabled for this run (it is built from our 25 filings, not
FinanceBench's, so it would inject irrelevant facts).

What this measures: grounded synthesis, numeric-claim verification, and
financial math over provided evidence. What it does **not** measure:
retrieval (the evidence is given, not retrieved). The full-retrieval variant
is built as the v2 mode — see below.

Scoring: our calibrated G-Eval judge scores our answer against the official
FinanceBench answer (factual equivalence, threshold 0.5).

## v2: full-retrieval mode (retrieve the evidence yourself, then reason)

`p1-eval-harness/scripts/build_financebench_corpus.py` downloads the filings
FinanceBench's 150 questions reference and indexes them with the same
retrieval stack (company-aware chunk headers, hybrid + rerank):

- 10-K / 10-Q / 8-K resolve through SEC EDGAR — matched by form + fiscal
  period using each company's own fiscal-year-end (handles off-cycle filers
  like Amcor and Adobe), including delisted/renamed tickers (Activision,
  Block, Foot Locker). Primary documents arrive as HTML (parsed by the 10-K
  section parser) or PDF (pymupdf text extraction).
- Earnings releases resolve through the dataset's own links (they are not
  EDGAR filings).
- Coverage: **81/84 documents built; 145/150 questions have their document
  in the index.** The 5 missing questions reference two J&J and one PepsiCo
  earnings release whose corporate-IR links are dead and have no EDGAR
  equivalent.

Then `benchmark_financebench.py --mode retrieval` retrieves each question's
own top-k chunks from that index and answers from them — retrieval +
grounding + reasoning end-to-end, no evidence handed over.

Status: corpus + index built; the retrieval step is validated offline
(correct filing in top-3 for 15/15 of a spread sample, top-1 for 13/15 —
the two top-1 misses are cross-company confusion that still lands in top-3).
The end-to-end scored run awaits OpenRouter credits (the free quota ran out
mid-session); the evidence-mode result above remains the published number.

## Reproduce

The adapter lives in the sibling `p1-eval-harness` project (it shares the
judge layer); it needs the P3 pipeline, so install both packages into one
venv first:

```bash
cd ../p1-eval-harness
uv run python scripts/benchmark_financebench.py          # evidence mode, all 150
uv run python scripts/benchmark_financebench.py --limit 20   # subset
# v2 full-retrieval mode:
uv run python scripts/build_financebench_corpus.py       # once: download + index the filings
uv run python scripts/benchmark_financebench.py --mode retrieval
```
The adapter downloads FinanceBench from HuggingFace
(`PatronusAI/financebench`, `financebench_merged.jsonl`) on first use into
`p1-eval-harness/data/financebench/` and writes per-question results to
`p1-eval-harness/reports/financebench/`.

## Caveats, stated plainly

- **Reasoning-over-evidence, not full retrieval.** The retrieval layer is not
  exercised here; this isolates synthesis + verification + math. The
  golden-set runs in this repo measure retrieval end-to-end.
- **Free model + judge.** Generation and judging both use the free
  `minimax/minimax-m3:free` model; run-to-run variance is a few questions.
- **Judge-scored.** Correctness is the G-Eval factual-equivalence verdict
  against the official answer, not an exact string match.
