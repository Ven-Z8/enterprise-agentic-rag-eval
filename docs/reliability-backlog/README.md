# Reliability audit and issue handoff

Assessment: September 7, 2026. Scope: P1/P3 runtime, evaluation contracts, financial tools, UI, dependency declarations and P5 optimization scaffold. This is a targeted reliability/maintainability audit, not exhaustive dead-code detection or production security certification. No production code was changed and no paid model requests were made during this audit.

## Confirmed offline reproductions

See `offline_audit_evidence.json`:

- Expected `Direct 40%; indirect 60%` versus actual `Direct 40%; indirect 99%` passes `_figures_match`.
- Citation `AAPL_2025_10K:Item1:c0019` matches expected `AAPL_2025_10K:Item1:c001`.
- Numerical verification accepts a Microsoft $123 million claim against an Apple $123 million passage. This proves the numerical check is scope-blind; it does not prove every downstream audit accepts the claim.
- Runtime `load_cases` accepts duplicate IDs and invalid enum strings; the exported `load_jsonl` rejects the same fixture.

## Reliability shortcuts found in code

The combined audit verdict can be lost at API/harness boundaries. UI stage completion is simulated using timers. The chart builder can load revenue while retaining the requested metric's label. Retry/cost behavior is spread across transport, Instructor and helper functions. Error paths can erase cost/time and lose partial evaluation output. These are behavioral defects, not style preferences.

## Cleanup candidates and exclusions

No repository consumers were found for the unused trace/metric contract family (`AgentRunTrace`, `TrajectoryStep`, `MetricScore`, `CaseEvalResult`) beyond its internal definitions. `GoldenCase` is active and must be retained or migrated explicitly. Dataset validation currently has two competing contracts.

Root `math_specialist.prompt`, `analyst.prompt`, and `auditor_verify.prompt` have no in-repository loading references; root `synthesis.prompt` is shadowed by domain-first lookup in the default configuration. Public dynamic loaders/package exports need review before removal.

No repository Python imports were found for the declared `langchain` umbrella and `langchain-openai` dependencies. Check fresh installation and transitive LangGraph requirements before pruning. Do not remove `langchain-core` merely because direct imports are absent.

The graph/tool compatibility shims have consumers. `pymupdf` is used by PDF ingestion. `load_prompt` is publicly exported and tested. These are not established dead code.

P5 is already labeled as an unevaluated prototype in its README, but `run_full_benchmark` returns fixed example measurements and its tests assert those same constants. Make its illustrative status consistent throughout, rather than counting those assertions as empirical optimization evidence.

Ruff F checks passed over all P1/P3 source files. That checks unused imports/undefined names; it does not establish absence of unused functions, behavioral bugs, misleading tests or dependency bloat.

## Work policy

Use the GitHub tracker for ordering. One issue and one reviewable change at a time: reproduce the defect, make the smallest coherent repair, run focused offline tests, then review the diff. A passing test should distinguish correct behavior from the observed failure, not repeat a constant defined by the implementation.

Any real LLM request must be announced and accounted for. Do not execute the 50 hiring cases. The 25-case diagnostic is available for targeted regression; it is not an independent holdout. Broader architecture implementation remains in `docs/PORTFOLIO_V0.2_SPEC.md`.
