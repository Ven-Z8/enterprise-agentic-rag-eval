# Case Study — RAG over Genuinely Messy Documents

*(Draft shell — fill [BRACKETS] after the eval run. Target: 900–1,200 words.
This doubles as the Week-2 published post and the video script skeleton.)*

## The problem

Anyone can demo RAG on Wikipedia. Real corporate filings are different: nested
tables, footnotes that carry the actual answer, sections that say "see Item 15"
instead of containing content, fiscal years that don't match calendar years, and
column orders that flip company to company. A system that looks 95% accurate in
a demo quietly returns wrong numbers on exactly the questions that matter.

I built RAG over 25 real SEC 10-K filings and — the part most people skip —
measured it against a 60-question hand-verified golden set, including questions
designed to make it hallucinate.

## The approach

- **Ingestion that respects the document**: [1–2 sentences: section trees, stub
  resolution for the 8/25 filings whose financials live in F-pages, table-row-safe
  chunking with header repetition, footnote linking]
- **Two retrieval strategies compared**: dense-only vs hybrid (dense + BM25).
  [Which won, by how much, on what categories]
- **Verification before answering**: every numerical claim re-checked against its
  cited chunk; refusal when confidence is low.

## The numbers

| Metric | Dense-only | Hybrid |
|---|---|---|
| Answer accuracy | [XX%] | [XX%] |
| Citation faithfulness | [XX%] | [XX%] |
| Hallucination rate (unanswerable) | [XX%] | [XX%] |
| Refusal correctness | [XX%] | [XX%] |
| Cost / query | [$0.0XX] | [$0.0XX] |
| p50 latency | [X.Xs] | [X.Xs] |

## Tradeoffs I chose

[3 bullets from ARCHITECTURE.md — verification latency vs wrong numbers,
chunk size vs table integrity, refusals vs coverage]

## What failed (the honest part)

**The [N] questions my system got wrong, and why:**

| Failure class | Count | Example | Root cause |
|---|---|---|---|
| Retrieval miss | [N] | [q id] | [why] |
| Table misread | [N] | [q id] | [why] |
| Synthesis error | [N] | [q id] | [why] |
| Judge disagreement | [N] | [q id] | [why] |

One fix, measured: [the fix] moved [metric] from [X] to [Y] — and here's why I
didn't chase the remaining failures in v1: [reason].

## What I'd do differently

[2–3 sentences. Required by the anti-slop checklist — do not skip.]

---

*Corpus and eval set are public: [repo link]. The golden set doubles as the
financial domain pack of my agent eval harness: [P1 link]. If you want this
level of measurement on your own document pipeline — [contact].*
