## Problem

Cost accounting and retries are fragmented. Permanent request errors may be retried, native tool calls lack an output cap, and failed or auxiliary calls can disappear from totals.

## Evidence

- p3-rag-filings/src/ragfilings/llm/factory.py:complete_with_resilience catches all exceptions; SDK retries add another layer.
- p3-rag-filings/src/ragfilings/agents/tool_loop.py sends no max_tokens cap.
- p3-rag-filings/src/ragfilings/llm/openrouter.py:parse_usage converts absent usage/cost to zero.
- pipeline/converse.py discards usage; financial/query_decompose.py and math_tool.py swallow failures.
- Agent attempt on September 7 hit repeated upstream Qwen 429s. Its temporary observer directory had vanished; optional PYTHONPATH silently failed to load it, leaving unknown spend.

## Acceptance criteria

- [ ] Put verified request logging and budget enforcement in a shared application transport; fail closed if required accounting is absent.
- [ ] Log model/role/attempt before every request; enforce output, query and run budgets with atomic reservations.
- [ ] Retry only classified transient failures with bounded backoff; invalid parameters/credit exhaustion fail fast and SDK retries cannot bypass the budget.
- [ ] Unknown cost stays null; retain all attempts and auxiliary calls and reconcile totals without double counting.
- [ ] Offline transport tests cover 400, 402, 429, 5xx, timeout, validation retry and budget exhaustion; announce any later real LLM calls.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
