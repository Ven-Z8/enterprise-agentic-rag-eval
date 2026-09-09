# Assessment selection: 25 core + 25 enterprise questions

Status: selected and schema-validated; no new paid run has started. The original 50-case hiring set remains excluded.

## Composition

- Core: 20 answerable, 3 refusals, 2 clarifications.
- Enterprise addition: 19 synthesis/calculation, 3 refusals, 3 clarifications.
- Combined: 39 answerable, 6 refusals, 5 clarifications; 50 unique IDs and no exact duplicate prompts.
- Original question records and source datasets are unchanged. Deliberate semantic overlap remains; this is a diagnostic/regression collection, not a held-out benchmark.

## Selected enterprise questions

### 26. ent-1002

What was the compound annual growth rate (CAGR) of Apple's net sales from fiscal year 2023 to fiscal year 2025?

Selection purpose: Two-year CAGR with annualization.

Original reference: 4.2% per year — growing from $383,285 million in fiscal year 2023 to $416,161 million in fiscal year 2025.

Original notes: enterprise builder; facts [val:AAPL:net_sales:2023, val:AAPL:net_sales:2025]. CAGR 2023->2025 = (416161.0/383285.0)^(1/2)-1

### 27. ent-1003

What was Alphabet's R&D intensity (research and development expense as a percentage of revenue) in fiscal year 2025?

Selection purpose: R&D expense divided by consolidated revenue.

Original reference: 15.2% — R&D expense of $61,087 million on revenue of $402,836 million.

Original notes: enterprise builder; facts [val:GOOGL:r&d_expense:2025, val:GOOGL:total_revenue:2025]. R&D intensity = 61087.0/402836.0 = 15.16%

### 28. ent-1004

Which company had the higher operating margin in fiscal year 2025: Microsoft or Meta Platforms?

Selection purpose: Cross-company operating-margin comparison.

Original reference: Microsoft had the higher operating margin: 45.6% versus 41.4% for Meta Platforms. (Microsoft: operating income $128,528 million on revenue $281,724 million; Meta Platforms: operating income $83,276 million on revenue $200,966 million.)

Original notes: enterprise builder; facts [val:MSFT:operating_income:2025, val:MSFT:total_revenue:2025, val:META:operating_income:2025, val:META:total_revenue:2025]. operating margin: MSFT=45.62% vs META=41.44%

### 29. ent-1005

How did Microsoft's net profit margin change from fiscal year 2024 to fiscal year 2025?

Selection purpose: Multi-year ratio change with percentage-point calculation from unrounded inputs.

Original reference: It increased from 36.0% in fiscal year 2024 to 36.1% in fiscal year 2025 (+0.2 percentage points). (Fiscal 2024: $88,136 million on revenue $245,122 million; fiscal 2025: $101,832 million on revenue $281,724 million.)

Original notes: enterprise builder; facts [val:MSFT:net_income:2024, val:MSFT:total_revenue:2024, val:MSFT:net_income:2025, val:MSFT:total_revenue:2025]. net profit margin 2024->2025: 35.96% -> 36.15%

### 30. ent-1007

What was Amazon's net profit margin in fiscal year 2025?

Selection purpose: Amazon net margin and consolidated scope.

Original reference: 10.8% — net income of $77,670 million divided by revenue of $716,924 million.

Original notes: enterprise builder; facts [val:AMZN:net_income:2025, val:AMZN:net_sales:2025]. net profit margin = Net Income / Net Sales = 10.83%

### 31. ent-1008

What was NVIDIA's net profit margin in fiscal year 2026?

Selection purpose: NVIDIA net margin with FY2026 scope.

Original reference: 55.6% — net income of $120,067 million divided by revenue of $215,938 million.

Original notes: enterprise builder; facts [val:NVDA:net_income:2026, val:NVDA:total_revenue:2026]. net profit margin = Net Income / Total Revenue = 55.60%

### 32. ent-1011

What was Tesla's operating margin in fiscal year 2025?

Selection purpose: Low operating margin; avoid substituting gross margin.

Original reference: 4.6% — operating income of $4,355 million divided by revenue of $94,827 million.

Original notes: enterprise builder; facts [val:TSLA:operating_income:2025, val:TSLA:total_revenue:2025]. operating margin = Operating Income / Total Revenue = 4.59%

### 33. ent-1012

What was Walmart's operating margin in fiscal year 2026?

Selection purpose: Retail operating margin with FY2026 scope.

Original reference: 4.2% — operating income of $29,825 million divided by revenue of $713,163 million.

Original notes: enterprise builder; facts [val:WMT:operating_income:2026, val:WMT:total_revenue:2026]. operating margin = Operating Income / Total Revenue = 4.18%

### 34. ent-1016

What was PepsiCo's gross margin in fiscal year 2025?

Selection purpose: Known poisoned-graph-fact regression; deliberate partial overlap with core question 017.

Original reference: 54.1% — gross profit of $50,859 million divided by net revenue of $93,925 million.

Original notes: enterprise builder; LABEL FIX 2026-09-01: the builder's derived figure used a poisoned graph fact (val:PEP:total_revenue:2025 = 52, an Item 7 table fragment — since quarantined in corpus/graph/excluded_facts.json). True consolidated figures (PEP_2025_10K:Item8:c000): gross profit $50,859M, net revenue $93,925M → 54.1%.

### 35. ent-1017

What was Meta's free cash flow margin in fiscal year 2025?

Selection purpose: Free-cash-flow margin with a disclosed non-GAAP numerator.

Original reference: 21.7% — free cash flow of $43,585 million divided by revenue of $200,966 million.

Original notes: enterprise builder; facts [val:META:free_cash_flow:2025, val:META:total_revenue:2025]. free cash flow margin = Free Cash Flow / Total Revenue = 21.69%

### 36. ent-1019

What was Tesla's R&D intensity (research and development expense as a percentage of revenue) in fiscal year 2025?

Selection purpose: Known R&D-intensity rounding failure.

Original reference: 6.8% — R&D expense of $6,411 million on revenue of $94,827 million.

Original notes: enterprise builder; facts [val:TSLA:r&d_expense:2025, val:TSLA:total_revenue:2025]. R&D intensity = 6411.0/94827.0 = 6.76%

### 37. ent-1020

What was the compound annual growth rate (CAGR) of Microsoft's total revenue from fiscal year 2023 to fiscal year 2025?

Selection purpose: Microsoft two-year CAGR.

Original reference: 15.3% per year — growing from $211,915 million in fiscal year 2023 to $281,724 million in fiscal year 2025.

Original notes: enterprise builder; facts [val:MSFT:total_revenue:2023, val:MSFT:total_revenue:2025]. CAGR 2023->2025 = (281724.0/211915.0)^(1/2)-1

### 38. ent-1021

What was the compound annual growth rate (CAGR) of NVIDIA's total revenue from fiscal year 2024 to fiscal year 2026?

Selection purpose: NVIDIA high-growth CAGR across FY2024–FY2026.

Original reference: 88.3% per year — growing from $60,922 million in fiscal year 2024 to $215,938 million in fiscal year 2026.

Original notes: enterprise builder; facts [val:NVDA:total_revenue:2024, val:NVDA:total_revenue:2026]. CAGR 2024->2026 = (215938.0/60922.0)^(1/2)-1

### 39. ent-1024

What was the compound annual growth rate (CAGR) of Costco's net sales from fiscal year 2023 to fiscal year 2025?

Selection purpose: Costco net-sales CAGR; avoid membership-inclusive denominator drift.

Original reference: 6.6% per year — growing from $237,710 million in fiscal year 2023 to $269,912 million in fiscal year 2025.

Original notes: enterprise builder; facts [val:COST:net_sales:2023, val:COST:net_sales:2025]. CAGR 2023->2025 = (269912.0/237710.0)^(1/2)-1

### 40. ent-1025

Which company had the higher net profit margin in fiscal year 2025: Alphabet or Microsoft?

Selection purpose: Cross-company net-profit-margin comparison.

Original reference: Microsoft had the higher net profit margin: 36.1% versus 32.8% for Alphabet. (Microsoft: net income $101,832 million on revenue $281,724 million; Alphabet: net income $132,170 million on revenue $402,836 million.)

Original notes: enterprise builder; facts [val:MSFT:net_income:2025, val:MSFT:total_revenue:2025, val:GOOGL:net_income:2025, val:GOOGL:total_revenue:2025]. net profit margin: MSFT=36.15% vs GOOGL=32.81%

### 41. ent-1026

Which company had the higher free cash flow margin in fiscal year 2025: Meta Platforms or Amazon?

Selection purpose: Cross-company free-cash-flow margins with four supporting quantities.

Original reference: Meta Platforms had the higher free cash flow margin: 21.7% versus 1.6% for Amazon. (Meta Platforms: free cash flow $43,585 million on revenue $200,966 million; Amazon: free cash flow $11,194 million on revenue $716,924 million.)

Original notes: enterprise builder; facts [val:META:free_cash_flow:2025, val:META:total_revenue:2025, val:AMZN:free_cash_flow:2025, val:AMZN:net_sales:2025]. free cash flow margin: META=21.69% vs AMZN=1.56%

### 42. ent-1027

How did Meta's operating margin change from fiscal year 2023 to fiscal year 2025?

Selection purpose: Multi-year operating-margin change; percentage points versus relative growth.

Original reference: It increased from 34.7% in fiscal year 2023 to 41.4% in fiscal year 2025 (+6.8 percentage points). (Fiscal 2023: $46,751 million on revenue $134,902 million; fiscal 2025: $83,276 million on revenue $200,966 million.)

Original notes: enterprise builder; facts [val:META:operating_income:2023, val:META:total_revenue:2023, val:META:operating_income:2025, val:META:total_revenue:2025]. operating margin 2023->2025: 34.66% -> 41.44%

### 43. ent-1028

What was the trend in Microsoft's total revenue from fiscal year 2023 to fiscal year 2025?

Selection purpose: Three-year revenue series with complete year mapping.

Original reference: Total revenue showed an upward trend: $211,915 million in fiscal year 2023, $245,122 million in fiscal year 2024, $281,724 million in fiscal year 2025.

Original notes: enterprise builder; facts [val:MSFT:total_revenue:2023, val:MSFT:total_revenue:2024, val:MSFT:total_revenue:2025]. Total Revenue series [2023, 2024, 2025]

### 44. ent-1029

What was the trend in Amazon's net sales from fiscal year 2023 to fiscal year 2025?

Selection purpose: Three-year Amazon sales series.

Original reference: Net sales showed an upward trend: $574,785 million in fiscal year 2023, $637,959 million in fiscal year 2024, $716,924 million in fiscal year 2025.

Original notes: enterprise builder; facts [val:AMZN:net_sales:2023, val:AMZN:net_sales:2024, val:AMZN:net_sales:2025]. Net Sales series [2023, 2024, 2025]

### 45. ent-1031

What was Salesforce's total revenue for fiscal year 2025?

Selection purpose: Out-of-corpus company.

Original reference: Refuse or clarify according to the source notes.

Original notes: enterprise builder; Salesforce is not one of the 25 filings in the corpus. Correct behavior: refuse, note the company is out of corpus scope.

### 46. ent-1033

What was Microsoft's total revenue for fiscal year 2019?

Selection purpose: Unavailable historical period.

Original reference: Refuse or clarify according to the source notes.

Original notes: enterprise builder; MSFT 10-K in the corpus reports FY2023-2025 only; 2019 predates the corpus. Correct behavior: refuse, state the reported range.

### 47. ent-1035

What was Apple's net income for the second quarter of fiscal year 2025?

Selection purpose: Unavailable quarterly net income; annual-only corpus does not itself prove absence, inspect filing evidence.

Original reference: Refuse or clarify according to the source notes.

Original notes: enterprise builder; The corpus holds annual 10-K statements only; quarterly net income is not available. Correct behavior: refuse, note annual-only scope.

### 48. ent-1039

What was Microsoft's profit margin in fiscal year 2025?

Selection purpose: Missing margin definition.

Original reference: Refuse or clarify according to the source notes.

Original notes: enterprise builder; 'Profit margin' is undefined: gross, operating, or net? Correct behavior: ask which margin (or present all three).

### 49. ent-1043

Which company is more profitable: Microsoft or Apple?

Selection purpose: Undefined profitability measure and period.

Original reference: Refuse or clarify according to the source notes.

Original notes: enterprise builder; 'More profitable' is undefined: absolute net income, net margin, or return on equity? Correct behavior: clarify the measure.

### 50. ent-1044

What was Meta Platforms' free cash flow margin relative to its peers?

Selection purpose: Missing peer group and fiscal period.

Original reference: Refuse or clarify according to the source notes.

Original notes: enterprise builder; Which peers, and which fiscal year? Correct behavior: clarify the comparison set and year.

## Run and reporting plan

Use `assessment_50.jsonl` as the explicit dataset path. Do not use the CLI default dataset. Keep core-25 and enterprise-25 scorecards separate, with an optional combined summary. Run graph and agent strategies on the same frozen selection after compatibility and accounting checks. This is 100 application runs if both strategies complete, not 50 API requests; each application run may make several calls.

The prior $2 ceiling remains. Re-estimate after small compatibility probes and stop with durable partial results if cost or provider availability prevents completion. Announce each real model request before sending it. Retrieval-only reranker comparisons do not require paid LLM calls.

The enterprise source uses a mixture of exact and judge scoring; its inherited numeric/citation/clarification weaknesses must be accounted for. Keep originals unchanged and report rubric adjudication separately. Do not silently rewrite labels to improve results.

Review flags and provenance hashes are in `enterprise_selection.json`. Every expected section citation resolves in the index; this is structural validation, not a fresh complete source audit. Home Depot and ambiguous Chevron-denominator cases are held out of this selected subset pending label clarification.
