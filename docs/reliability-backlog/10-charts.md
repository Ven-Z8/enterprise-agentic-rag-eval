## Problem

Chart construction can fall back from the requested metric to revenue while keeping the original metric title. Ticker substring matching can also select unrelated companies.

## Evidence

- p3-rag-filings/src/ragfilings/ui/server.py:331-386: if requested history is absent, loads Total Revenue/Net Sales but preserves detected_metric in chart_data/title.
- The same block tests ticker with `t in q_upper`; short symbols can match ordinary words.
- The chart unit is always USD_M even when metric semantics differ.

## Acceptance criteria

- [ ] Resolve chart company/metric/period from the same typed scope and sourced facts as the answer.
- [ ] Never label revenue as operating income or gross margin; omit unavailable charts or explicitly offer a correctly labeled alternative.
- [ ] Use exact entity resolution, validated units and source provenance for plotted points.
- [ ] Offline API fixtures with missing operating-income history but available revenue, incidental ticker substrings and percent metrics produce no misleading chart.

## Working agreement

Solve this as one focused change: reproduce, fix, run targeted offline checks, then review the diff. Do not rewrite adjacent modules. Announce every real LLM call before sending it. Do not execute the 50 hiring cases.

## Assessment context

Based on repository base commit `2ae5937` plus the local approved model/reranker changes on `codex/model-routing`; code line numbers refer to the assessed working tree. Diagnostic/spec artifacts currently exist locally and may not yet be committed. This issue contains the relevant evidence so it is actionable without those unpublished files.
