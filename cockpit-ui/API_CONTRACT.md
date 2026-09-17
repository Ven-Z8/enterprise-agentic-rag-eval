# RAGFilings — Universal Cockpit Backend API Contract

This document defines the complete REST API specification expected by the **Universal Agentic Cockpit UI**. 
Any backend (FastAPI, Flask, Express, Go, etc.) implementing these endpoints will connect seamlessly to this frontend.

---

## 1. Architectural Overview

The frontend operates on a **Dual-Mode Bridge**:
1. **Live Backend Mode**: When the backend server is reachable, all queries, presets, graphs, and histories are fetched live from `/api/*`.
2. **Offline / Standby Preview Mode**: If the backend is offline or during testing, the frontend falls back to the active `DomainPack` mock data with zero crashes.

```
┌─────────────────────────────────────────────────────────────┐
│                    Universal Cockpit UI                     │
│         (HTML5 + Vanilla JS + CSS Grid + Canvas 2D)         │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       FastAPI Server                        │
│            (`rag-engine/src/ragfilings/ui/server.py`)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       ▼                       ▼                       ▼
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│  Financial   │        │    Legal     │        │  Biomedical  │
│  DomainPack  │        │  DomainPack  │        │  DomainPack  │
└──────────────┘        └──────────────┘        └──────────────┘
```

---

## 2. API Endpoints Specification

### 2.1. `POST /api/query` (Primary Execution Engine)
Executes a multi-agent orchestration query across the specified domain.

#### Request Headers:
```http
Content-Type: application/json
```

#### Request Body:
```json
{
  "query": "Compare Apple Inc.'s FY2023, FY2024, and FY2025 net sales and compute the 2-year CAGR.",
  "strategy": "hybrid_rerank_graph",
  "top_k": 8,
  "session_id": "conv_a1b2c3d4e5f6",
  "domain": "financial"
}
```

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `query` | string | Yes | — | The user's prompt or investigation inquiry. |
| `strategy` | string | No | `"hybrid_rerank_graph"` | Orchestration strategy: `"hybrid_rerank_graph"`, `"agent_react"`, `"hybrid_rerank"`, `"hybrid"`, `"dense"`. |
| `top_k` | integer | No | `8` | Number of chunks to retrieve during the retrieval phase. |
| `session_id` | string | No | `null` | Persistent session ID for conversational memory and follow-up query rewriting. |
| `domain` | string | No | `"financial"` | Active domain pack: `"financial"`, `"legal"`, `"biomedical"`, or custom slug. |

#### Response Body (HTTP 200 OK):
```json
{
  "session_id": "conv_a1b2c3d4e5f6",
  "query": "Compare Apple Inc.'s FY2023, FY2024, and FY2025 net sales and compute the 2-year CAGR.",
  "rewritten_query": "Compare Apple Inc.'s FY2023, FY2024, and FY2025 net sales and compute the 2-year CAGR.",
  "strategy": "hybrid_rerank_graph",
  "answer": "Based on audited SEC 10-K filings, Apple's net sales were $383,285M in FY23, $391,035M in FY24... [1]",
  "refused": false,
  "refusal_reason": null,
  "citations": [
    {
      "label": "AAPL 10-K FY24 Item 8 (p.32)",
      "text": "Net sales was $391,035 million in 2024 compared to $383,285 million in 2023...",
      "doc": "AAPL-10K-FY24.pdf"
    }
  ],
  "confidence": 0.985,
  "latency_ms": 1420.0,
  "usage": {
    "cost_usd": 0.0078,
    "prompt_tokens": 1420,
    "completion_tokens": 310
  },
  "verified": true,
  "verification": {
    "engine": "Safe Python AST Math",
    "code": "((391035 / 383285) ** (1/2) - 1) * 100",
    "output": "+1.01% 2-Yr CAGR",
    "confidence": 0.998
  },
  "math_result": {
    "expression": "((391035 / 383285) ** (1/2) - 1) * 100",
    "result_value": 1.01
  },
  "tables": [
    {
      "chunk_id": "AAPL_FY24_Item8_Table0",
      "section": "Item8",
      "title": "Filing Table · Item 8 Consolidated Statements",
      "headers": ["Metric", "FY2023 ($M)", "FY2024 ($M)"],
      "rows": [
        ["Total Net Sales", "$383,285", "$391,035"],
        ["Cost of Sales", "$214,137", "$210,352"],
        ["Gross Margin", "$169,148", "$180,683"]
      ]
    }
  ],
  "chart_data": {
    "ticker": "AAPL",
    "metric": "Net Sales Trajectory ($ Millions)",
    "labels": ["FY23", "FY24", "FY25"],
    "values": [383285, 391035, 395000]
  },
  "trajectory": [
    {
      "stage": 1,
      "name": "Lead Orchestrator",
      "latency_ms": 140,
      "details": "Decomposed query into 2 sub-queries"
    },
    {
      "stage": 2,
      "name": "Tri-Hybrid Retrieval",
      "latency_ms": 410,
      "details": "Retrieved 8 candidate chunks (BGE score > 0.88)"
    },
    {
      "stage": 3,
      "name": "Table Extraction",
      "latency_ms": 280,
      "details": "Parsed 1 structured Markdown filing table"
    },
    {
      "stage": 4,
      "name": "Safe Python AST",
      "latency_ms": 12,
      "details": "Formula parsed and evaluated without eval()"
    },
    {
      "stage": 5,
      "name": "Synthesis Specialist",
      "latency_ms": 520,
      "details": "Grounded answer synthesized with 2 citations"
    },
    {
      "stage": 6,
      "name": "Auditor Guardrail",
      "latency_ms": 60,
      "details": "Deterministic check passed: 100% numerical concordance"
    }
  ],
  "hits": [
    {
      "id": "chunk_aapl_fy24_032",
      "score": 0.942,
      "section": "Item 8",
      "text": "Total net sales were $391,035 million in fiscal year 2024..."
    }
  ]
}
```

---

### 2.2. `GET /api/presets`
Returns predefined complex benchmark questions for the active domain.

#### Query Parameters:
- `domain` (optional, string): e.g. `"financial"`, `"legal"`, `"biomedical"`

#### Response Body (HTTP 200 OK):
```json
{
  "presets": [
    {
      "id": "q1",
      "category": "Multi-Year CAGR & Trend",
      "title": "Apple Inc. (AAPL) — FY2023-FY2025 Net Sales & 2-Year CAGR",
      "query": "Compare Apple Inc.'s FY2023, FY2024, and FY2025 net sales and compute the 2-year CAGR.",
      "ticker": "AAPL"
    },
    {
      "id": "q2",
      "category": "Profitability & Margin Variance",
      "title": "Apple Inc. (AAPL) — Gross Margin Expansion (FY25 vs FY24)",
      "query": "What was Apple Inc.'s gross margin percentage in FY2025 compared to FY2024, and what were the primary drivers?",
      "ticker": "AAPL"
    }
  ]
}
```

---

### 2.3. `GET /api/graph`
Returns the knowledge graph nodes and edges for visualization in the Force-Directed Canvas.

#### Query Parameters:
- `domain` (optional, string): e.g. `"financial"`, `"legal"`, `"biomedical"`
- `ticker` (optional, string): Filter graph by entity (e.g. `"AAPL"`)

#### Response Body (HTTP 200 OK):
```json
{
  "nodes": [
    {
      "id": "AAPL",
      "label": "AAPL",
      "type": "entity",
      "ticker": "AAPL"
    },
    {
      "id": "NET_SALES",
      "label": "Net Sales",
      "type": "metric",
      "value": 391035,
      "fiscal_year": "2024"
    },
    {
      "id": "ITEM_8",
      "label": "Item 8 Financials",
      "type": "section"
    }
  ],
  "links": [
    {
      "source": "AAPL",
      "target": "NET_SALES",
      "relation": "REPORTED_METRIC"
    },
    {
      "source": "NET_SALES",
      "target": "ITEM_8",
      "relation": "LOCATED_IN"
    }
  ],
  "stats": {
    "node_count": 3,
    "edge_count": 2
  }
}
```

---

### 2.4. `GET /api/history`
Returns recent SQLite session logs for audit trail tracking.

#### Query Parameters:
- `limit` (optional, integer, default `20`)

#### Response Body (HTTP 200 OK):
```json
{
  "sessions": [
    {
      "session_id": "conv_a1b2c3d4e5f6",
      "query": "Compare Apple and Microsoft R&D spend as a percentage of net sales...",
      "latency_ms": 1420.0,
      "cost_usd": 0.0078,
      "verified": true,
      "created_at": "2026-09-13T17:40:00Z"
    }
  ]
}
```

---

### 2.5. `POST /api/session/new`
Initializes a new conversational session for context tracking.

#### Response Body (HTTP 200 OK):
```json
{
  "session_id": "conv_3f8a9e2d1c0b"
}
```

---

### 2.6. `GET /api/domains`
Returns all registered `DomainPack` manifests.

#### Response Body (HTTP 200 OK):
```json
{
  "domains": [
    {
      "id": "financial",
      "name": "Financial (SEC 10-K)",
      "badge": "SEC 10-K",
      "eval_score": "94.0% (47/50)",
      "geval_kappa": "κ 0.723",
      "cost": "< 0.8¢",
      "latency": "1.42s"
    },
    {
      "id": "legal",
      "name": "Legal (Commercial Contracts)",
      "badge": "913 DEFINED TERMS",
      "eval_score": "92.4% (46/50)",
      "geval_kappa": "κ 0.708",
      "cost": "< 0.7¢",
      "latency": "1.25s"
    },
    {
      "id": "biomedical",
      "name": "Biomedical (PubMed + PubChem)",
      "badge": "PUBCHEM PUG-REST",
      "eval_score": "91.8% (45/50)",
      "geval_kappa": "κ 0.695",
      "cost": "< 0.9¢",
      "latency": "1.65s"
    }
  ]
}
```

---

## 3. How to Serve this UI in FastAPI

In your FastAPI backend (`rag-engine/src/ragfilings/ui/server.py`):

```python
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

COCKPIT_DIR = Path(__file__).resolve().parents[4] / "cockpit-ui"

# Mount static assets
app.mount("/cockpit", StaticFiles(directory=str(COCKPIT_DIR), html=True), name="cockpit")

@app.get("/")
async def serve_cockpit_root():
    return FileResponse(str(COCKPIT_DIR / "index.html"))
```
