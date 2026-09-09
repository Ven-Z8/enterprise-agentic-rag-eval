## Problem

The new 25-case run produces a scorecard paragraph claiming the old 50-case dataset, while metric averages omit failed measurements without visible coverage.

## Evidence

- p1-eval-harness/src/harness/report.py:13-20 hardcodes Golden set v1 / 50 cases.
- p1-eval-harness/src/harness/traces/build.py:105 hardcodes golden_verification=v1 proven.
- September 6 graph diagnostic: faithfulness=1.0 on only 5 valid outputs, with 8 invalid-JSON errors. This is not 100% faithfulness across 25 cases.
- The scorecard calls citation-prefix matching Citation faithfulness, which overstates what is measured.

## Acceptance criteria

- [ ] Derive dataset name, case count, hash and provenance from the actual run.
- [ ] Every metric displays successful, failed, skipped and eligible counts alongside its average.
- [ ] Rename citation matching metrics accurately; keep semantic support distinct.
- [ ] Offline report fixtures for a 25-case run and missing metrics contain no inherited 50-case/v1 claims.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
