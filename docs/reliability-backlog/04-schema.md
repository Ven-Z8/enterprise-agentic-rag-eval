## Problem

Two exported dataset schemas enforce different rules. The runtime loader accepts malformed labels and duplicate IDs that the public dataclass loader rejects.

## Evidence

- p1-eval-harness/src/harness/schema.py:GoldenCase uses unconstrained strings for type, difficulty and category.
- p1-eval-harness/src/harness/metrics/engine.py:load_cases appends cases without duplicate-ID checks.
- p1-eval-harness/src/harness/datasets/schema.py:load_jsonl and validate enforce enums and duplicates.
- Offline reproduction: runtime loader accepts 2 identical invalid-enum cases; exported loader rejects the same file.

## Acceptance criteria

- [ ] Choose one canonical validated dataset contract shared by CLI, scripts and exported loaders.
- [ ] Reject duplicate IDs across all input files, invalid enums and invalid refusal/answer combinations before any paid request.
- [ ] Preserve documented compatibility or provide an explicit migration for existing datasets.
- [ ] Both loader entry points produce equivalent results/errors on valid and invalid fixtures.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
