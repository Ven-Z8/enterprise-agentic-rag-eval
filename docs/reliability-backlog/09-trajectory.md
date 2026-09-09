## Problem

The UI uses elapsed timers to animate all six stages and marks all of them done regardless of the selected strategy or skipped steps. Agent history also is not connected to the UI memory reader.

## Evidence

- p3-rag-filings/src/ragfilings/ui/static/app.js:371-407 schedules fixed 100–2100 ms stage timers and marks every stage done after a response.
- pipeline/engine.py:351 constructs MultiAgentOrchestrator(cfg) without memory; UI reads a separate memory manager for its trajectory.
- Initial UI displays AUDITED before a query has run.

## Acceptance criteria

- [ ] Show only observed stage events; use an honest generic in-progress indicator until event streaming exists.
- [ ] Represent skipped, failed and completed stages distinctly for each strategy and cancel stale timers/events on errors/new requests.
- [ ] Persist a shared query/trajectory identity and show non-empty real agent history after successful agent execution.
- [ ] UI tests use delayed/skipped/failed stage fixtures and prove no fabricated completion or verified badge.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
