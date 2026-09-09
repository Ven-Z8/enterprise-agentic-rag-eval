## Problem

The repository contains redundant or apparently unconsumed scaffolding. Cleanup must be based on consumers, not a blanket deletion of compatibility modules.

## Evidence

- No in-repository consumers found for MetricScore/CaseEvalResult/AgentRunTrace beyond their own definitions in p1-eval-harness/src/harness/schema.py; GoldenCase is actively used.
- No references found for root math_specialist.prompt, analyst.prompt or auditor_verify.prompt; root synthesis.prompt is shadowed by the domain-first registry in the default profile.
- P3 declares langchain and langchain-openai but no imports were found in repository Python; langchain-core may remain transitively necessary for LangGraph.
- tools/* and graph/* shims are still used. pymupdf has a real PDF ingestion consumer; load_prompt is publicly exported and tested.
- Ruff F checks pass across P1/P3 source: there are no flagged unused-import/undefined-name findings to justify cosmetic churn.

## Acceptance criteria

- [ ] Build a consumer map including CLI entry points, exports, tests, scripts, package data and dynamic prompt loading.
- [ ] Remove or explicitly deprecate only confirmed unused contracts/templates/dependencies; record public API decisions.
- [ ] Do not delete used shims or the active PDF path based on static-name scans alone.
- [ ] Regenerate dependency locks after justified dependency changes and verify fresh environment installation plus offline suites.
- [ ] Consolidate dataset schema only after its dedicated validation issue, preserving compatibility tests.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
