## Problem

The active index labels Home Depot as FY2026 even though the filing inline-XBRL fiscal-year focus is 2025.

## Evidence

- Local corpus inventory: HD_2026_10K is derived from HD_2026-03-18_10K.htm; DocumentFiscalYearFocus is 2025.
- Evidence is saved in p1-eval-harness/data/diagnostics/portfolio_v02/corpus_inventory.json.
- Calendar filing/period-end year must not be assumed to be the fiscal label; Walmart/NVIDIA fiscal 2026 cases are distinct.

## Acceptance criteria

- [ ] Track fiscal year, period end and filing date as separate fields validated against source metadata.
- [ ] Inventory impacted chunks, graph facts and golden references before rebuilding.
- [ ] Publish old-to-new citation mapping plus parser/index versions; preserve historical run artifacts.
- [ ] All active filings have reconciled fiscal identities and references resolve after the migration.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
