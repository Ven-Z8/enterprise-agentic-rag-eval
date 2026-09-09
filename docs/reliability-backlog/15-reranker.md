## Problem

The configured v2-m3 reranker now reaches standard and agent retrieval paths, but loading it and passing routing tests do not establish a quality improvement over the previous model.

## Evidence

- Local model loading/inference and routing tests passed.
- Graph diagnostic annotated-source coverage: any source 17/20; all sources 16/20. These are exact annotated-ID coverage measures, not exhaustive relevance judgments.
- No controlled base-versus-v2-m3 comparison has been completed.

## Acceptance criteria

- [ ] Freeze index, embedding, queries and candidate pools; compare BGE base versus v2-m3 with no generation changes.
- [ ] Report any/all required-source coverage, ranking metrics only where labels support them, and cold/warm reranking latency.
- [ ] Inspect alternative supporting chunks before classifying exact-ID misses as retrieval failures.
- [ ] Publish regressions and retain the model supported by the measured tradeoff; do not declare v2 superior in advance.
- [ ] Use the 25-case diagnostic, not the excluded 50 hiring cases. Retrieval-only evaluation needs no paid LLM calls.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
