## Problem

Ambiguous requests are not handled as a separate outcome, and the harness gives a generic refusal credit for clarification.

## Evidence

- Diagnostic 024 What was operating profit? identified missing company/year but did not ask for them; harness passed it, explicit rubric failed it.
- Diagnostic 025 How much did Microsoft revenue grow? silently selected FY2024–FY2025.
- agents/planner.py replaces an empty subquestion list with the original query, undermining the orchestrator branch that expects an empty not_in_corpus plan.

## Acceptance criteria

- [ ] Return clarification_needed with an actionable question for missing company/period; preserve known conversation scope.
- [ ] Do not fabricate comparison periods or route unresolved scope through unnecessary retrieval/synthesis.
- [ ] Score clarification separately from insufficient_evidence; generic refusal does not pass an ask-for-scope rubric.
- [ ] Offline tests cover first-turn ambiguity, resolved follow-up scope and out-of-corpus short-circuiting.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
