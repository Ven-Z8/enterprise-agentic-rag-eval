## Objective

Make the financial Agentic Graph RAG portfolio reliable through small, evidence-backed changes. This tracker contains 15 independently reviewable issues, not a request for a repository-wide rewrite.

## Start here

**First: #1 — preserve the final audit verdict through the API, harness and UI.** Reproduce the numerical-pass/semantic-fail case offline, then prevent it from appearing as a verified successful answer. Do not start another issue until this change is reviewed.

## Ordered backlog

- [x] #1 — [P0] Preserve the final audit verdict through API, harness and UI
- [x] #2 — [P0] Report the executed dataset and metric coverage truthfully
- [x] #4 — [P1] Unify dataset validation and reject duplicate or invalid cases before running
- [x] #3 — [P0] Score every required claim and enforce citation boundaries
- [x] #5 — [P0] Enforce request budgets and account for every retry and failed attempt
- [x] #6 — [P1] Persist each evaluation result and retain partial runs on failure
- [x] #7 — [P1] Derive requested financial calculations from typed, cited inputs
- [x] #8 — [P1] Ask for missing scope instead of refusing or guessing fiscal years
- [x] #12 — [P1] Reconcile Home Depot fiscal identity with versioned citation migration
- [x] #9 — [P1] Replace simulated pipeline progress with real execution events
- [x] #10 — [P1] Prevent charts from substituting the wrong metric or company
- [x] #11 — [P1] Make local API configuration and request execution predictable
- [x] #13 — [P2] Remove verified dead scaffolding and consolidate overlapping contracts
- [x] #14 — [P2] Make the parked P5 optimization stub unmistakably illustrative
- [x] #15 — [P2] Measure reranker value on identical candidate pools

## Dependencies

- #3 builds on #2.
- #6 builds on #5.
- #7 builds on #1.
- #8 builds on #1, #3.
- #9 builds on #1.
- #11 builds on #5, #9.
- #13 builds on #4.
- #15 builds on #2.

## One-issue workflow

1. Agree on the issue's concrete failure and acceptance criteria.
2. Write a minimal offline reproduction that fails for the right reason.
3. Make one focused repair on a `codex/` branch; avoid unrelated cleanup.
4. Run targeted tests, then required package checks. Inspect the actual diff.
5. For model-dependent behavior, announce each real LLM call and enforce/record its cost before running it. Keep expected answers frozen.
6. Attach evidence to the PR and close the issue only when its criteria are met. Keep at most one implementation issue in progress.

The 50 hiring cases are excluded. The new 25-case set is a diagnostic/regression set, not independent human gold. No real LLM calls were made while preparing this backlog.

## Evidence and limitations

The graph assessment completed all 25 diagnostic cases: 17/25 current-harness passes and 16/25 assistant rubric passes. An attempted agent comparison stopped on repeated Qwen upstream rate limits; there is no completed agent quality score. The local v0.2 spec and detailed run artifacts contain these limits and the incomplete spend coverage of the resumed agent attempt.

Four new offline audit probes reproduced partial-number scoring, citation-ID prefix collisions, scope-blind numerical verification and inconsistent schema validation. Static review additionally identified fabricated UI stage progression, metric-substitution charts and unused-scaffolding candidates. Existing compatibility wrappers, PDF ingestion and public prompt APIs must not be blindly removed.

P5 already has a prototype warning; its hardcoded benchmark API/tests need consistent illustrative naming, not a fabricated performance claim. The audit is targeted, not an exhaustive security/performance certification.

Local handoff files (not necessarily committed yet): `docs/PORTFOLIO_V0.2_SPEC.md`, `docs/reliability-backlog/README.md`, `docs/reliability-backlog/offline_audit_evidence.json`. Each issue includes its core evidence so it remains actionable without unpublished files.
