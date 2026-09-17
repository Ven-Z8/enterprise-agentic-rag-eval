# Architecture — one page, honest about tradeoffs

```mermaid
flowchart TD
    subgraph Ingestion["Ingestion (offline, once per corpus)"]
        A[SEC EDGAR<br/>25 × 10-K HTML] --> B[Section tree parser<br/>TOC-dedup, Part grouping]
        B --> C[Stub resolver<br/>Item 8 'incorporated by reference'<br/>→ real F-pages, resolved_from flag]
        C --> D[Section-aware chunker<br/>table-row-safe splits,<br/>header repetition, note_refs]
        D --> E[(Chunk store<br/>+ metadata: company,<br/>fiscal year, section)]
    end

    subgraph Query["Query path"]
        Q[Question] --> R{Retrieval<br/>config-selected}
        R -->|strategy A| R1[Dense-only]
        R -->|strategy B| R2[Hybrid dense + BM25]
        E --> R1 & R2
        R1 & R2 --> G[Grounded generation<br/>every claim cites chunk IDs]
        G --> V[Verification pass<br/>numerical claims re-checked<br/>against cited chunks]
        V -->|confidence low| REF[Refuse + log]
        V -->|verified| ANS[Answer + citations]
    end

    subgraph Eval["Eval (sibling p1-eval-harness project)"]
        GS[(Golden sets in p1:<br/>80 audited + 45 multi-hop)] --> EV[Eval runner]
        ANS -.traces.-> EV
        EV --> SC[Scorecard + failure analysis]
    end
```

## Tradeoffs made deliberately

| Decision | What we gained | What it costs |
|---|---|---|
| Header-based section parsing + stub resolution (not an HTML-layout model) | Simple, debuggable, zero ML deps | Breaks on filings with exotic structures; JPM needed special handling |
| Chunking never splits table rows; headers repeated per chunk | Table questions actually answerable | Bigger chunks → more tokens per query |
| Verification pass re-checks numbers before answering | Catches wrong-column/wrong-year errors — our #1 failure class | Adds one model call of latency per numerical answer |
| Confidence-gated refusal | Low hallucination rate on unanswerable questions | Some answerable questions get refused (measured, reported) |
| Two retrieval strategies behind one config flag | The comparison is publishable content | Neither is tuned to its individual ceiling |

## What v1 does not attempt (with a hypothesis)

Multi-hop / agentic retrieval. Hypothesis: it would fix cross-filing synthesis
failures (e.g., comparing two companies' figures in one question) at roughly 2–3×
the cost per query. Documented in the failure analysis when we ship it.
