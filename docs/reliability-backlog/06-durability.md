## Problem

Error rows replace elapsed time and incurred cost with zero, result output is buffered, and the fifth consecutive failure raises before persisting that case.

## Evidence

- p1-eval-harness/src/harness/runner.py:97-129 replaces result usage/latency after errors and raises at the fifth failure.
- September 7 agent run: 3 recorded errors, fourth case interrupted, 21 unattempted. The saved zeros do not reflect billing or elapsed time.

## Acceptance criteria

- [ ] Persist/flush each completed case and its attempts before advancing or evaluating the circuit breaker.
- [ ] Write a partial-run manifest with completed, failed, interrupted and unattempted IDs.
- [ ] Retain measured latency and incurred/unknown cost when generation or scoring fails.
- [ ] Tests interrupt after a successful request, after judge failure and on the fifth consecutive error; all prior evidence survives.
- [ ] Resume only uncompleted cases with configuration/dataset hash checks and no silent re-execution.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
