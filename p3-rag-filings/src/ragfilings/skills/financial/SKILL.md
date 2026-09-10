---
name: financial
display_name: SEC 10-K & Financial Analysis
description: Analyzes SEC 10-K/10-Q filings, financial statements, balance sheets, revenue/cost breakdowns, CAGR, margins, and financial arithmetic.
domain: financial
activation_keywords:
  - revenue
  - net income
  - operating income
  - gross margin
  - cagr
  - fiscal year
  - 10-k
  - balance sheet
  - cash flow
  - capital expenditure
  - capex
  - share repurchase
tools:
  - financial_math
  - fact_graph_rescue
verification_type: monetary_claims
version: 1.0.0
---

# Financial Analysis & SEC 10-K Domain Skill

This skill provides expert financial reasoning, document parsing, mathematical derivation, and monetary claim verification over SEC filings (Form 10-K and 10-Q).

## Capabilities
1. **Financial Statement Analysis**: Disentangles Consolidated vs Segment financials, GAAP vs Non-GAAP metrics, and table column ordering (ascending vs descending fiscal years).
2. **Deterministic Financial Math**: Formulates and verifies calculations (CAGR, growth rates, margin deltas, ratios, combined customer shares) using the safe Python math tool.
3. **Fact-Graph Grounding & Scope Clarification**: Leverages deterministic SEC XBRL/HTML fact graphs to retrieve exact figures and request clarification for underspecified queries.
4. **Strict Grounding & Refusal**: Prohibits hallucination or metric substitution (e.g., substituting dollar revenue for unit shipments).
