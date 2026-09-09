## Problem

P5 returns constant example measurements from a method named run_full_benchmark; its test only asserts those same constants. The README already warns that this is a parked prototype, but code/docstrings and later result headings remain misleading in isolation.

## Evidence

- p5-cost-optimization/src/optimization/optimizer.py hardcodes accuracy 85%, 75% cost reduction and 63.1% latency reduction without running a system.
- p5-cost-optimization/tests/test_optimization.py asserts hardcoded reduction/quality fields.
- p5-cost-optimization/README.md explicitly says FUTURE SCOPE / targets, but later describes a rigorous case study and Optimization Results Summary.

## Acceptance criteria

- [ ] Keep P5 parked outside v0.2 hiring claims; rename/move its example data so no executable API suggests measured benchmarking.
- [ ] Remove contradictory measured-results language from module docstrings and README sections.
- [ ] Replace circular benchmark assertions with fixture/schema tests if illustrative assets are retained.
- [ ] Any future performance claim must be computed from versioned before/after harness runs; do not implement a new optimization platform as part of this cleanup.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
