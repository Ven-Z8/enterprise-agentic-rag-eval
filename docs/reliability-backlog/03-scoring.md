## Problem

The deterministic scorer can accept an incorrect multi-part answer after matching the first expected number; citation prefix collisions also count as hits.

## Evidence

- p1-eval-harness/src/harness/metrics/engine.py:_figures_match only checks exp_claims[0].
- Offline reproduction: expected Direct 40%; indirect 60% versus actual Direct 40%; indirect 99% returns True.
- Offline reproduction: citation AAPL_2025_10K:Item1:c0019 matches expected AAPL_2025_10K:Item1:c001.
- Correctness is separate from required-source coverage; answered-case rubrics in notes are not consistently passed to the judge.

## Acceptance criteria

- [ ] Require all material claims with company, fiscal period, units and labels; swapped labels or missing second claims fail.
- [ ] Allow documented section-level citations using delimiter-aware matching; chunk IDs match exactly.
- [ ] Pass each case rubric to semantic scoring and record claim-level reasons.
- [ ] Regression fixtures include first-number-only, swapped columns, wrong units, zero values, prefix collisions and missing second source.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.

## September 9 assessment: conflicting judge score scales

`CORRECTNESS_STEPS` in `harness/judge.py` asks for a score between 0 and 1. The installed DeepEval GEval template asks for an integer between 0 and 10, and normalizes by dividing by 10. Both instructions appear in the same rendered prompt.

In phase 2 core case `v02-25-008`, the paid judge explanation says every PepsiCo claim matches, but the harness records score 0.1 and incorrect. An offline mock returning `{"score": 1, "reason": "Every required claim matches."}` reproduces that failing 0.1 verdict. Original raw API response content was not captured, so this proves the contract defect and a mechanism consistent with the observation, not the exact original response.

- [ ] Unify the prompt scale and DeepEval normalization contract; test lower bound, pass threshold and upper bound offline.
- [ ] Preserve original scores; never blindly multiply historical scores by ten because some requests already follow the 0–10 contract.
- [ ] Recalibrate the corrected judge against independently reviewed labels and rescore preserved application answers before publishing accuracy.

Local evidence: `p1-eval-harness/reports/phase2-assessment/judge_scale_reproduction.json`, `judge_scale_prompt.txt`, and `hybrid_rerank_graph/v02-25-008.scored.json`. These are assessment artifacts, not a production fix.
