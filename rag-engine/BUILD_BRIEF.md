# P3 Build Brief — Production RAG with a Published Failure Analysis

**Build time:** 2 weeks (Jul 6–19). Build this FIRST — it's the fast win and its
golden set feeds P1's financial domain pack.

## Milestone plan

### Days 1–2: Corpus + skeleton
- Run `scripts/download_corpus.py` to pull 20–25 10-K filings (manifest included).
- Project skeleton: `src/ragfilings/` with ingestion / retrieval / generation / verification modules, config-driven.
- Smoke test: parse one filing end-to-end, print section tree.

### Days 3–5: Ingestion pipeline that handles the mess
- Table extraction that preserves structure (don't flatten to word soup).
- Footnote linking.
- Section-aware chunking: respect document hierarchy, never split mid-table.
- Metadata per chunk: company, fiscal year, section type (Item 1A, Item 7, etc.) for filtered retrieval.
- Unit tests on the ugly cases: nested tables, multi-page tables, footnote refs.

### Days 6–8: Retrieval + grounded generation
- Two retrieval strategies, both implemented and comparable via config:
  1. Dense-only (baseline)
  2. Hybrid (dense + BM25) — optionally with a reranker as a third config
- Grounded generation: every answer cites specific chunk IDs.
- Verification pass: each numerical claim checked against its cited source before answering.
- Refusal path: when retrieval confidence is low, refuse — log it.

### Days 9–11: Golden set + eval suite
- Hand-build 60–100 questions using `golden/schema.md` and the skeleton in `golden/golden_set_skeleton.jsonl`. Categories:
  - simple lookup, cross-section synthesis, table-reading,
  - NOT-in-corpus (hallucination test), ambiguous (clarification test).
- Metrics: answer accuracy, retrieval hit rate, citation faithfulness,
  hallucination rate on unanswerable questions, refusal correctness, cost + latency per query.
- Run both retrieval strategies against the full golden set. The comparison IS the content.

### Days 12–14: Failure analysis + shipping
- Write the differentiator section: **"The N questions my system got wrong, and why."**
  Categorize: retrieval miss vs. table misread vs. synthesis error vs. judge disagreement.
  Show ONE fix and its measured effect on the scorecard.
- README with scorecard image in first screen-scroll, one-command repro.
- Architecture diagram (one page, honest about tradeoffs).
- 2–4 min video + written case study.

## The 5 universal deliverables (not done without all of them)
1. Working demo or recorded end-to-end run
2. Clean public repo, README a senior engineer respects
3. Architecture diagram
4. Metrics table (accuracy/eval scores, cost per query, latency)
5. Video + case study (problem → approach → tradeoffs → numbers → what failed)

## Case study angle
"Anyone can build RAG that works on easy questions. Here's what it takes on real
filings — measured, with the failures included."

## Suggested first prompt for Claude Code

> Read CLAUDE.md and BUILD_BRIEF.md. Start with Days 1–2: run
> scripts/download_corpus.py, then scaffold src/ragfilings/ with
> ingestion/retrieval/generation/verification modules and a config system.
> Parse one filing end-to-end and show me the section tree.
