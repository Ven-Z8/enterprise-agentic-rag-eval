## Problem

The server relies on working-directory-relative index/graph paths, ignores requested top_k, and performs synchronous inference inside an async handler while keeping unbounded shared conversation state.

## Evidence

- p3-rag-filings/src/ragfilings/ui/server.py:get_system_components uses relative index/graph paths.
- QueryRequest exposes top_k, but execute_query calls ask without propagating it.
- execute_query directly invokes blocking rewrite_followup/ask; _CONVERSATIONS has no lifecycle bound.
- Assessment tests passed from P3 cwd; a root-cwd startup exposed index loading failures.

## Acceptance criteria

- [ ] Resolve resource paths from explicit configuration/project roots and verify readiness before accepting paid work.
- [ ] Validate supported strategy/domain/top_k and honor accepted parameters or reject them explicitly.
- [ ] Keep blocking inference off the event loop and protect shared inference/session state with explicit concurrency limits.
- [ ] Define bounded session retention and cleanup.
- [ ] Offline API tests cover root/P3 startup, invalid input, top_k propagation and two concurrent independent sessions.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
