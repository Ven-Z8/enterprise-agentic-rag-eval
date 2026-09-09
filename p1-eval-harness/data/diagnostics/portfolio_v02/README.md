# Portfolio v0.2 — 25-question diagnostic set

Primary scope: the active financial index (25 SEC annual filings, 8,419 chunks). Eleven companies support the 20 answerable cases; three cases require refusal and two require clarification.

This is an assistant-authored diagnostic set, designed after reviewing the existing sets. It is not an independent held-out benchmark or a human-labeled calibration set. No paid model calls were used to author it. Existing sets remain unchanged.

All cases use judge scoring because most require multiple claims or semantic interpretation. `evidence_25.json` contains exact chunk text, source URLs, hashes, calculation provenance, per-case rubrics, and nearest existing questions. Manually enforce the rubrics: the existing harness can count a generic refusal as correct on an ambiguous question and does not require all cited sources for a correctness pass.

The separate FinanceBench corpus is not part of this set. The 50-case hiring set is excluded from execution at the user’s request.

## Questions and reference answers

### v02-25-001 — table

In Apple's FY2025 filing, what percentages of net sales came through direct and indirect distribution channels?

**Reference:** Direct 40%; indirect 60%.

**Rubric:** Require both labels and both percentages; do not swap channels.

**Evidence:** AAPL_2025_10K:Item1:c002

### v02-25-002 — synthesis

In NVIDIA's FY2026 filing, what combined percentage of total revenue came from its two disclosed major direct customers? Do not infer their identities.

**Reference:** 36% combined: 22% plus 14%; the passage does not name them.

**Rubric:** Require 36% and constituent shares; invented customer names fail.

**Evidence:** NVDA_2026_10K:Item1A:c036

### v02-25-003 — synthesis

How much did Costco's membership-fee revenue increase from FY2024 to FY2025, in USD millions and percentage terms?

**Reference:** $495 million, approximately 10.25%, from $4,828 million to $5,323 million.

**Rubric:** Require absolute and relative change. Accept 10% as filing-rounded growth if figures and $495M are correct.

**Evidence:** COST_2025_10K:Item7:c008

### v02-25-004 — synthesis

At the end of Costco FY2025, how did the U.S./Canada membership renewal rate compare with the worldwide rate? Give the gap in percentage points.

**Reference:** 92.3% versus 89.8%; U.S./Canada was 2.5 percentage points higher.

**Rubric:** Require both rates and 2.5 percentage points, not a 2.5% relative increase.

**Evidence:** COST_2025_10K:Item7:c008

### v02-25-005 — synthesis

Which Microsoft segment generated the most operating income in FY2025, and what percentage of consolidated operating income did it contribute?

**Reference:** Productivity and Business Processes: $69,773 million, about 54.29% of $128,528 million consolidated operating income.

**Rubric:** Require segment, operating-income numerator and consolidated denominator. Accept share within 0.1 percentage point.

**Evidence:** MSFT_2025_10K:Item7:c009

### v02-25-006 — synthesis

For Alphabet FY2025, combine Google Search & other and YouTube ads revenue. What share of Google advertising revenue did they represent?

**Reference:** $264,899 million combined, approximately 89.89% of Google advertising revenue of $294,691 million.

**Rubric:** Require combined value and share. Denominator must be Google advertising, not consolidated revenue.

**Evidence:** GOOGL_2025_10K:Item7:c014

### v02-25-007 — synthesis

Reconcile Meta's FY2025 consolidated operating income using Family of Apps operating income and Reality Labs operating loss.

**Reference:** Family of Apps operating income of $102,469 million less Reality Labs operating loss of $19,193 million equals consolidated operating income of $83,276 million.

**Rubric:** Require all three figures and subtract the loss. Treating the loss as positive income fails.

**Evidence:** META_2025_10K:Item7:c002

### v02-25-008 — synthesis

Did PepsiCo's operating profitability improve in FY2025 despite revenue growth? Support your answer with FY2024/FY2025 operating profit and operating margin.

**Reference:** No. Revenue rose from $91,854M to $93,925M (about 2%), but operating profit fell from $12,887M to $11,498M (about 11%). Operating margin fell from 14.0% to 12.2%, a 1.8 percentage-point decline.

**Rubric:** Require negative conclusion and correctly aligned operating profit and margin for both years. Do not substitute net profit.

**Evidence:** PEP_2025_10K:Item7:c023

### v02-25-009 — lookup

According to Walmart's filing, on what dates did fiscal 2026 and fiscal 2025 end?

**Reference:** Fiscal 2026 ended January 31, 2026; fiscal 2025 ended January 31, 2025.

**Rubric:** Require both dates with correct fiscal-year mapping; do not infer calendar-year endings.

**Evidence:** WMT_2026_10K:Item7:c000

### v02-25-010 — lookup

What are Johnson & Johnson's two business segments in its FY2025 10-K?

**Reference:** Innovative Medicine and MedTech.

**Rubric:** Require both current segments. Adding Consumer Health as a current segment fails.

**Evidence:** JNJ_2025_10K:Item1:c000

### v02-25-011 — lookup

In Apple's FY2025 reporting structure, which geographic segment includes India, and what other non-European regions does that segment include?

**Reference:** Europe includes India, the Middle East and Africa, in addition to European countries.

**Rubric:** Require Europe, Middle East and Africa. Rest of Asia Pacific is incorrect for India.

**Evidence:** AAPL_2025_10K:Item1:c002

### v02-25-012 — synthesis

What happened to Microsoft Cloud gross margin percentage in FY2025, and which driver and offset did management identify?

**Reference:** It decreased to 69%, driven by scaling AI infrastructure, partly offset by efficiency gains in Azure.

**Rubric:** Require 69%, direction of change, AI infrastructure scaling and Azure efficiency offset.

**Evidence:** MSFT_2025_10K:Item7:c008

### v02-25-013 — synthesis

Why did Costco's membership renewal rates face pressure in FY2025, and how does Costco recognize annual membership-fee revenue?

**Reference:** More online memberships, including digital promotions, entered the renewal calculation; these members renew at a slightly lower rate. Membership-fee revenue is deferred and recognized ratably over the one-year membership period.

**Rubric:** Require both the renewal explanation and ratable deferred recognition. Cite both supporting passages; this is cross-chunk synthesis.

**Evidence:** COST_2025_10K:Item7:c008, COST_2025_10K:Item7:c009

### v02-25-014 — synthesis

Approximately how many more consumer vehicles did Tesla produce than deliver in 2025? Is an exact unit difference justified by the filing's rounded figures?

**Reference:** Approximately 20,000 more: about 1.66 million produced less about 1.64 million delivered. The rounded disclosures do not establish an exact unit difference.

**Rubric:** Require approximate 20,000 and explicit rounding caveat. Claiming exactly 20,000 fails.

**Evidence:** TSLA_2025_10K:Item7:c001

### v02-25-015 — synthesis

What was Google Cloud's revenue growth from FY2024 to FY2025, in USD millions and percent?

**Reference:** $15,476 million, approximately 35.80%, from $43,229M to $58,705M.

**Rubric:** Require both delta and growth with the 2024 denominator.

**Evidence:** GOOGL_2025_10K:Item7:c014

### v02-25-016 — synthesis

Comparing each company's reported FY2025 with FY2024, which had the larger dollar increase in consolidated revenue: Alphabet or Microsoft? By how much did the increases differ?

**Reference:** Alphabet: $52,818M increase versus Microsoft $36,602M, so Alphabet’s increase was $16,216M larger. These are each company’s fiscal years, not identical calendar periods.

**Rubric:** Require both increases and difference; fiscal-period caveat welcome. Compare increases, not total revenue.

**Evidence:** GOOGL_2025_10K:Item7:c011, MSFT_2025_10K:Item7:c008

### v02-25-017 — synthesis

Using FY2025 gross profit divided by net revenue/net sales, compare PepsiCo's gross margin with Costco's. Report both margins and the percentage-point gap; this is not a claim about overall investment quality.

**Reference:** PepsiCo approximately 54.15% ($50,859M/$93,925M); Costco approximately 11.12% ($30,026M/$269,912M); PepsiCo higher by approximately 43.02 percentage points.

**Rubric:** Require both gross margins and approximately 43.02–43.03 percentage-point gap. Do not compare operating margins or infer investment quality.

**Evidence:** PEP_2025_10K:Item8:c000, COST_2025_10K:Item7:c009

### v02-25-018 — synthesis

What percentage of Meta's FY2025 consolidated revenue came from Family of Apps rather than Reality Labs?

**Reference:** Approximately 98.90%, using Family of Apps revenue of $198,759M and consolidated revenue of $200,966M.

**Rubric:** Require about 98.9% and the correct segment/consolidated denominator.

**Evidence:** META_2025_10K:Item7:c002

### v02-25-019 — lookup

Which three operating segments does Amazon identify in its FY2025 10-K?

**Reference:** North America, International, and Amazon Web Services (AWS).

**Rubric:** Require all three segments. Product categories are not operating segments.

**Evidence:** AMZN_2025_10K:Item1:c000

### v02-25-020 — synthesis

Why does NVIDIA's FY2026 filing say its purchase-order sales model creates demand risk?

**Reference:** Customers can generally cancel, change or delay purchase commitments with little notice and without penalty, exposing NVIDIA to changes in purchasing patterns.

**Rubric:** Require cancellation/change/delay flexibility and little notice/no penalty. Do not invent contractual guarantees.

**Evidence:** NVDA_2026_10K:Item1A:c036

### v02-25-021 — unanswerable

Using only the indexed filings, what was Adobe's total revenue in FY2025?

**Reference:** Do not answer with a fabricated figure; follow the rubric below.

**Rubric:** Refuse as out of corpus: no Adobe filing exists in the 25-document active financial index. Do not use the separate FinanceBench index or model memory.

**Evidence:** Scope/clarification case; inspect the corpus manifest and question.

### v02-25-022 — unanswerable

What was Tesla's audited annual revenue in FY2030?

**Reference:** Do not answer with a fabricated figure; follow the rubric below.

**Rubric:** Refuse: FY2030 is outside the available Tesla FY2025 filing; do not substitute forecasts or another year.

**Evidence:** Scope/clarification case; inspect the corpus manifest and question.

### v02-25-023 — unanswerable

Using these filings, what was Apple's closing share price on September 4, 2026?

**Reference:** Do not answer with a fabricated figure; follow the rubric below.

**Rubric:** Refuse: requested market price/date is outside the annual-filing corpus. Do not substitute the 2025 market-value disclosure.

**Evidence:** Scope/clarification case; inspect the corpus manifest and question.

### v02-25-024 — ambiguous

What was operating profit?

**Reference:** Do not answer with a fabricated figure; follow the rubric below.

**Rubric:** Ask which company and fiscal period; do not invent scope. Generic refusal is not sufficient for the manual rubric.

**Evidence:** Scope/clarification case; inspect the corpus manifest and question.

### v02-25-025 — ambiguous

How much did Microsoft's revenue grow?

**Reference:** Do not answer with a fabricated figure; follow the rubric below.

**Rubric:** Ask for the comparison fiscal years/periods, and optionally dollars versus percent. Do not silently choose FY2024–FY2025.

**Evidence:** Scope/clarification case; inspect the corpus manifest and question.
