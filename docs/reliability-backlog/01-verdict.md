## Problem

An agent can finish with an answer and refused=false after its combined audit fails. Consumers then read the numerical sub-check instead of the combined verdict, so an unsuccessful audit can look verified.

## Evidence

- p3-rag-filings/src/ragfilings/pipeline/orchestrator.py:187-212 computes all_ok, stores the combined result separately, and can reach END on audit exhaustion without refusing.
- p3-rag-filings/src/ragfilings/ui/server.py:392-408 returns verification but omits the top-level verified verdict.
- p1-eval-harness/src/harness/runner.py:140 reads verification.verified with a True default.
- Offline verification probe: Microsoft revenue was $123 million passes against an Apple passage containing $123 million. Numerical membership alone is not semantic verification.

## Acceptance criteria

- [ ] Introduce one authoritative final answer status and verification verdict across the result contract.
- [ ] Audit exhaustion, invalid citations, missing verification and disagreement between numerical/semantic checks cannot produce a successful verified answer.
- [ ] Keep numerical checks labeled separately; an answer with zero numeric claims is not automatically semantically verified.
- [ ] Add offline tests covering numerical-pass/semantic-fail, missing verdict and audit exhaustion through orchestrator, API and harness.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
