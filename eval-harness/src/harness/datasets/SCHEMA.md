# Golden Dataset Schema (v0) — canonical contract

One JSONL file, one test case per line. **This is the source of truth.** P3
(`../p3-rag-filings/golden/schema.md`) targets this format; if it must change,
change it here first, then propagate. `schema.py` in this directory is the
executable version of this document.

## Test case fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | `<domain>-NNNN` (e.g. `fin-0001`), stable forever once assigned |
| `input` | string | The task/question exactly as a user would ask it |
| `expected.answer` | string \| null | Ground-truth answer. `null` == unanswerable/ambiguous (agent must refuse or clarify) |
| `expected.citations` | list[string] | Supporting source(s), e.g. `"AAPL_2025_10K:Item7"` |
| `expected.type` | enum | `exact` \| `contains` \| `judge` — how to score |
| `variation_rules` | list[string] | Accepted variation, e.g. `numeric_tolerance:0.5%`, `unit_equivalence`, `fiscal_vs_calendar_year_ok` |
| `difficulty` | enum | `easy` \| `medium` \| `hard` |
| `failure_category` | enum | `lookup` \| `synthesis` \| `table` \| `unanswerable` \| `ambiguous` |
| `domain` | string | `financial` \| `legal` \| `support` \| ... |
| `notes` | string | Optional. Why this case exists / what it's designed to catch |

## Invariants (enforced by `validate()`)

1. `expected.type`, `difficulty`, `failure_category` must be from their enums.
2. `unanswerable` and `ambiguous` cases must have `expected.answer: null` — the
   correct behavior is a refusal or a clarifying question, which the metric layer
   detects rather than string-matching.
3. `exact`/`contains` cases need a non-null `expected.answer` (unless they are
   refusal cases per rule 2).
4. `id` is unique within a file.

## Example

```json
{"id": "fin-0001", "input": "What was Apple's total net sales for fiscal year 2025?", "expected": {"answer": "391.0 billion", "citations": ["AAPL_2025_10K:Item8"], "type": "exact"}, "variation_rules": ["numeric_tolerance:0.1%", "unit_equivalence"], "difficulty": "easy", "failure_category": "lookup", "domain": "financial", "notes": "simple lookup baseline"}
```

## Note on `null` answers vs scoring type

`unanswerable` and `ambiguous` both use `answer: null` but differ in intent:
- **unanswerable** — the fact isn't in the corpus; correct behavior is to refuse.
- **ambiguous** — the question is underspecified; correct behavior is to ask for
  clarification.

Both are refusals from a string-matching standpoint; the metric that scores them
(Phase 1) distinguishes "refused" from "answered anyway (hallucinated)". Authors
should still set `expected.type` (`exact` for unanswerable, `judge` for ambiguous
is the P3 convention) so the runner knows which refusal-detector to apply.
