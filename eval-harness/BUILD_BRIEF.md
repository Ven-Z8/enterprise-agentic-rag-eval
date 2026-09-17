# P1 Build Brief — Eval Harness (scaffold phase, runs parallel to P3)

**Full build time:** 3–4 weeks (core in 2, domain packs in 1–2), scheduled weeks 3–5.
**Right now (weeks 1–2):** only the scaffold + dataset format, so P3 can target it.

## Phase 0 — NOW, parallel to P3 (≤2 days of work)

The single most important early decision is the **golden dataset format**,
because P3 starts hand-building 60–100 questions against it this week.

1. Define the JSONL test-case schema (v0):
   ```json
   {
     "id": "fin-0001",
     "input": "...question or task...",
     "expected": {"answer": "...", "citations": ["chunk-ref"], "type": "exact|contains|judge"},
     "variation_rules": ["numeric_tolerance:0.5%", "unit_equivalence"],
     "difficulty": "easy|medium|hard",
     "failure_category": "lookup|synthesis|table|unanswerable|ambiguous",
     "domain": "financial|legal|support",
     "notes": "why this case exists / what it's designed to catch (optional)"
   }
   ```
   ~~Iterate on this~~ **FROZEN as of Phase 0.** Single source of truth:
   `src/harness/datasets/SCHEMA.md`. This example is illustrative only.
2. Repo skeleton: `src/harness/{datasets,traces,metrics,runner,report}/`, empty
   but importable, with the adapter interface sketched as a Protocol/ABC.
3. Trace format (v0): JSON schema for a full agent run (steps, tool calls, retries,
   tokens, cost, latency, final output).

## Phase 1 — Core engine (weeks 3–4, after P3 ships)

- Golden dataset toolkit incl. semi-automated builder (human-in-the-loop).
- Trajectory capture + replay.
- Three-tier metric layer (deterministic / statistical / calibrated LLM-judge).
- Regression runner with history + diff reports.
- HTML/markdown report generator.

## Phase 2 — Domain packs (weeks 4–5)

1. **Financial document QA** — golden set imported from P3. Metrics: numerical
   accuracy (exact figures), source-grounding rate.
2. **Legal/contract extraction** — ~50 clauses from SEC EDGAR exhibits.
   Metrics: extraction accuracy, citation faithfulness, hallucinated-clause rate.
3. **Customer-support agent** — ~50 scenarios. Metrics: resolution correctness,
   escalation-when-required rate, forbidden-action rate.

Each pack ships: golden dataset, metric config, baseline agent, full eval report,
and a writeup: *"What the harness caught in this domain that a demo would have hidden."*

## Case study angle
"95% of agent portfolios show demos. Demos hide failures. Here's a framework
that finds them — and here's what it found."

## Suggested first prompt for Claude Code

> Read CLAUDE.md and BUILD_BRIEF.md. Do Phase 0 only: finalize the golden
> dataset JSONL schema and trace format, and scaffold src/harness/ with the
> adapter interface. The schema must work for the question categories in
> ../p3-rag-filings/golden/schema.md — check consistency before finishing.
