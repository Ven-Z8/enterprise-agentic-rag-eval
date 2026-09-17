# Judge calibration v1 — DeepEval G-Eval vs hand labels

- judge: `minimax/minimax-m3:free` (OpenRouter, temperature 0)
- labeled pairs: 52 (`p1-eval-harness/data/domain_a_financial/judge_calibration_v1.jsonl`)
- labels: written by the portfolio author against the filing text
- re-measure: `p1-eval-harness/scripts/calibrate_judge.py` (judge layer lives in
  the sibling `p1-eval-harness` project)

## Headline numbers

- **agreement (accuracy): 45/52 = 86.5%**
- **Cohen's kappa: 0.669**

Re-measured 2026-08-31 after the judge moved to `p1-eval-harness`
(`p1-eval-harness/scripts/calibrate_judge.py`, same 52 labels, same free
judge model): **agreement 46/52 = 88.5%, kappa 0.723**. Free-judge
run-to-run variance is a few labels; both measurements stand.

| human \ judge | correct | incorrect |
|---|---|---|
| correct | 34 | 6 |
| incorrect | 1 | 11 |

## Disagreements

### fin-9001 — human: correct, judge: incorrect (score 0.2)
- Q: What was the net income?
- expected: v1 hand-authored; no company, no year, no basis. Correct behavior: ask which company and fiscal year, not guess.
- actual: The question is too ambiguous as multiple companies' net income figures are available across the provided chunks. The relevant figures include:

- JPMorgan Chase (firmwide): $57.0 billion for 2025
- JPMorgan Chase (Consumer & Community Banking segment): $18,245 million ($18.2 billion) for 2025
- NVIDIA: $120,067 million for the year ended Jan 25, 2026
- Bank of America (consolidated): $30,509 mill
- human evidence: explicitly flags the ambiguity and lists candidate figures instead of guessing
- judge reason: The expected output indicates the correct response should be to ask which company and fiscal year, not to guess. The actual output instead provides multiple speculative net income figures for various companies (JPMorgan, NVIDIA, Bank of America, Goldman Sachs, Pfizer, P&G) without being asked to disambiguate. While the actual output does acknowledge ambiguity, it fails to follow the expected behavior of asking clarifying questions and instead guesses by listing them. This contradicts the expected output's direction.

### fin-9002 — human: correct, judge: incorrect (score 0.1)
- Q: What was Apple's net sales?
- expected: v1 hand-authored; corpus holds FY2023-FY2025 for AAPL, so the year must be pinned down. Correct behavior: ask which fiscal year.
- actual: Apple's total net sales were $416,161 million in fiscal 2025, $391,035 million in fiscal 2024, and $383,285 million in fiscal 2023.
- human evidence: presents all three fiscal years instead of committing to one
- judge reason: The expected output states the correct behavior is to ask which fiscal year, since net sales data is available for multiple years (FY2023-FY2025). The actual output instead provided specific net sales figures for all three fiscal years without asking for clarification. While the figures may be factually accurate, the expected behavior was to ask a clarifying question, not to provide all values. The actual output contradicts the expected direction by providing data instead of asking for clarification.

### fin-9003 — human: correct, judge: incorrect (score 0.1)
- Q: What was Microsoft's total revenue?
- expected: v1 hand-authored; year unspecified (FY2023-FY2025 available). Correct behavior: ask which fiscal year.
- actual: Microsoft's total revenue for fiscal year 2025 was $281,724 million ($281.724 billion), for fiscal year 2024 was $245,122 million, and for fiscal year 2023 was $211,915 million.
- human evidence: presents all three fiscal years
- judge reason: The expected output indicates that the correct behavior is to ask the user which fiscal year, since the question did not specify one. The actual output provides specific revenue figures for FY2025, FY2024, and FY2023 without asking for clarification. While the figures themselves may be factually accurate, the response fails to follow the expected behavior of seeking clarification about which fiscal year the user is asking about. The expected output emphasizes asking for the year as the correct approach rather than volunteering multiple years' data. The response does not align with the expected behavior of asking for clarification.

### fin-9004 — human: correct, judge: incorrect (score 0.0)
- Q: What was Tesla's total revenue?
- expected: v1 hand-authored; year unspecified. Correct behavior: ask which fiscal year.
- actual: Tesla's total revenues were $94,827 million in 2025, $97,690 million in 2024, and $96,773 million in 2023.
- human evidence: presents all three fiscal years
- judge reason: The expected output indicates that the correct behavior is to ask for clarification about the fiscal year, since none was specified. The actual output provides specific revenue figures for 2025, 2024, and 2023 without acknowledging the ambiguity in the user's question. While the actual numbers may be factually accurate, the actual output fails to follow the expected guidance to request clarification. It also introduces unsupported quantitative claims (revenue figures for specific years) that don't match the expected output's direction. Since the expected behavior is to ask a clarifying question, the actual output contradicts this approach.

### fin-9007 — human: correct, judge: incorrect (score 0.1)
- Q: What was Bank of America's total assets?
- expected: v1 hand-authored; balance-sheet date unspecified (FY2024 vs FY2025 both in corpus). Correct behavior: ask as of which year end.
- actual: Bank of America's total assets were $3,411,738 million ($3.4 trillion) as of December 31, 2025, up from $3,261,299 million as of December 31, 2024, an increase of $150,439 million (5%).
- human evidence: gives both year-end balances with dates, covering the ambiguity
- judge reason: The expected output indicates the correct behavior is to ask for clarification about the year-end, since both FY2024 and FY2025 data appear in the corpus. The actual output instead confidently provides a figure ($3,411,738 million as of December 31, 2025) without seeking clarification. While the actual output includes specific quantitative claims, the expected output contains no quantitative claims to verify—rather it specifies a behavioral expectation (asking for clarification) that the actual output fails to meet. The actual output contradicts the expected approach by not asking for the year-end, which is a significant directional/behavioral mismatch.

### fin-9009 — human: incorrect, judge: correct (score 0.5)
- Q: What was Alphabet's research and development expense?
- expected: v1 hand-authored; year unspecified (2023-2025 in corpus). Correct behavior: ask which fiscal year.
- actual: The provided context chunks do not contain Alphabet's specific research and development expense figure. The chunks describe the main components of Alphabet's R&D expenses (depreciation, employee compensation, technical infrastructure costs, and third-party services fees) but do not provide the actual dollar amount.
- human evidence: no clarification; claims figure missing though R&D 49,326/61,087 exists in GOOGL Item7
- judge reason: The expected output indicates the correct behavior is to ask which fiscal year, since the R&D expense figure is not specified. The actual output acknowledges the dollar amount is not provided and explains the chunks describe components but not the figure. However, the actual output fails to ask the user for the fiscal year clarification, which is the key correct behavior. There are no quantitative claims to contradict, but the actual output misses the core expected action (asking for year). Partial alignment but missing a critical element.

### fin-9010 — human: correct, judge: incorrect (score 0.1)
- Q: What was Home Depot's gross profit?
- expected: v1 hand-authored; year unspecified (fiscal 2023-2025 in corpus). Correct behavior: ask which fiscal year.
- actual: Home Depot's gross profit was $54,865 million in fiscal 2025, $53,308 million in fiscal 2024, and $50,960 million in fiscal 2023.
- human evidence: presents all three fiscal years
- judge reason: The expected output indicates the correct behavior is to ask which fiscal year the user is referring to, since the year is unspecified. The actual output provides specific gross profit figures for fiscal years 2023, 2024, and 2025 without asking for clarification. While the actual output does not contradict any specific quantitative claim (since the expected output intentionally contains none), it fails the key expected behavior of asking for clarification. The expected output explicitly states the correct behavior is to ask which fiscal year, and the actual output does not do this, instead providing all years' data directly.

## Reading the disagreements (2026-08-31)

The 7 disagreements are not random:

- **6 of 7 share one pattern** (fin-9001/9002/9003/9004/9007/9010): the system
  handled an ambiguous question by *enumerating every interpretation*
  (all fiscal years, both EPS bases, both balance-sheet dates) instead of
  asking a clarifying question. The hand labels accept enumeration as valid
  disambiguation; the G-Eval judge reads the rubric literally ("ask for
  clarification") and scores them incorrect. The judge is stricter than the
  scoring semantics on this behavior — known, quantified, one-directional.
- **fin-9009 is the only false positive**: the system claimed the figure was
  missing from context (it exists in GOOGL Item7) and the judge accepted the
  refusal-style answer as correct.

Implication: judge verdicts on ambiguous-category cases understate system
quality by ~6/10 in this configuration; verdicts on all other categories
agree 40/42 (95.2%). The agreement number above is published as-is; no
post-hoc correction is applied to any scorecard.
