## Problem

The graph diagnostic refused seven answerable questions. Several responses explicitly contained the inputs but refused because the derived value was not printed in the filing.

## Evidence

- New diagnostic failures: 002 NVIDIA 22%+14%; 003 Costco membership fee delta; 005 Microsoft segment share; 006 Alphabet advertising share; 016 cross-company revenue deltas; 017 gross-margin comparison; 018 Meta segment share.
- financial/math_tool.py reads only chunks[:4], extracts one expression, guesses percent formatting from query keywords, and swallows exceptions.
- financial/prompts/synthesis.prompt permits derivation but also insists on exact copying and refusal when the requested figure cannot be pointed to verbatim.
- Case 017 reports missing Costco context; diagnose candidate coverage rather than treating every failure as arithmetic.

## Acceptance criteria

- [ ] Represent each operation with cited inputs, company/period, units, output units and deterministic result.
- [ ] Support multiple outputs, percentage-point versus relative change, signs and rounded inputs.
- [ ] Route calculation intent explicitly; remove contradictory prompt behavior and expose structured calculation failures.
- [ ] Reject ungrounded constants/non-finite results and bound expression complexity.
- [ ] Reproduce the seven failures individually, distinguishing retrieval and calculation causes; keep expected answers frozen.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
