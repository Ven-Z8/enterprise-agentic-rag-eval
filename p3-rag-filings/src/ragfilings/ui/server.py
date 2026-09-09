"""FastAPI backend service for the RAGFilings agentic Graph RAG platform."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import load as load_cfg
from ..graph.builder import FinancialGraphBuilder
from ..graph.query import GraphQueryEngine
from ..pipeline.converse import rewrite_followup
from ..pipeline.engine import ask
from ..pipeline.memory import SessionMemoryManager
from ..retrieval import load_index

logger = logging.getLogger(__name__)

P3_ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="RAGFilings Agentic Graph RAG API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Shared state
_cfg: dict[str, Any] | None = None
_index: Any | None = None
_graph_engine: GraphQueryEngine | None = None
_memory = SessionMemoryManager()

# In-memory conversational sessions: session_id -> ordered turns
# [{"role": "user"|"assistant", "content": str}]
_CONVERSATIONS: dict[str, list[dict[str, str]]] = {}

PRESET_QUESTIONS = [
    {
        "id": "q1",
        "category": "Multi-Year CAGR & Trend",
        "title": "Apple Inc. (AAPL) — FY2023-FY2025 Net Sales & 2-Year CAGR",
        "query": "Compare Apple Inc.'s FY2023, FY2024, and FY2025 net sales and compute the 2-year CAGR.",
        "ticker": "AAPL",
    },
    {
        "id": "q2",
        "category": "Profitability & Margin Variance",
        "title": "Apple Inc. (AAPL) — Gross Margin Percentage Expansion (FY25 vs FY24)",
        "query": "What was Apple Inc.'s gross margin percentage in FY2025 compared to FY2024, and what were the primary drivers?",
        "ticker": "AAPL",
    },
    {
        "id": "q3",
        "category": "R&D Drivers & MD&A",
        "title": "Meta Platforms (META) — R&D Expense Trajectory & Key Drivers",
        "query": "What was Meta Platforms' total research and development (R&D) expense in FY2025 vs FY2024, and what were the primary driver factors in Item 7 MD&A?",
        "ticker": "META",
    },
    {
        "id": "q4",
        "category": "Hypergrowth YoY Velocity",
        "title": "NVIDIA (NVDA) — 3-Year Total Revenue & FY2025 YoY Growth",
        "query": "Analyze NVIDIA Corporation's total revenue trajectory across FY2023, FY2024, and FY2025 and compute the YoY growth rate for FY2025.",
        "ticker": "NVDA",
    },
    {
        "id": "q5",
        "category": "Cash Flow Dynamics",
        "title": "Microsoft (MSFT) — Operating Cash Flow Drivers (FY25 vs FY24)",
        "query": "What were the key drivers of Microsoft Corporation's cash flows from operating activities in FY2025 vs FY2024?",
        "ticker": "MSFT",
    },
    {
        "id": "q6",
        "category": "Segment Revenue Breakdown",
        "title": "Amazon (AMZN) — AWS Cloud vs North America Segment Sales",
        "query": "Extract Amazon.com Inc.'s AWS segment sales vs North America segment sales in FY2025 and compute AWS share of total net sales.",
        "ticker": "AMZN",
    },
    {
        "id": "q7",
        "category": "Automotive Margins & Credits",
        "title": "Tesla Inc. (TSLA) — Automotive Regulatory Credits & Gross Margin",
        "query": "What are Tesla Inc.'s automotive regulatory credit revenues and gross margin percentage trends in FY2025?",
        "ticker": "TSLA",
    },
    {
        "id": "q8",
        "category": "Advertising & Services Mix",
        "title": "Alphabet Inc. (GOOGL) — Google Search & YouTube Ad Revenue",
        "query": "Detail Google Search and YouTube advertising revenues for Alphabet Inc. in FY2025 and calculate total Google Services revenue.",
        "ticker": "GOOGL",
    },
    {
        "id": "q9",
        "category": "Banking & Net Interest Income",
        "title": "JPMorgan Chase (JPM) — Net Interest Income & Non-Interest Expense",
        "query": "What was JPMorgan Chase's net interest income and non-interest expense in FY2025 compared to FY2024?",
        "ticker": "JPM",
    },
    {
        "id": "q10",
        "category": "Retail Operating Margin",
        "title": "Walmart Inc. (WMT) — Consolidated Operating Income & Margin",
        "query": "Extract Walmart Inc.'s consolidated operating income and calculate the operating margin percentage for FY2025.",
        "ticker": "WMT",
    },
]


def get_system_components():
    global _cfg, _index, _graph_engine
    if _cfg is None:
        cfg_path = P3_ROOT / "config.toml"
        _cfg = load_cfg(str(cfg_path)) if cfg_path.exists() else {}

    if _index is None and _cfg:
        index_dir = _cfg.get("embedding", {}).get("index_dir", "corpus/index")
        model = _cfg.get("embedding", {}).get("model", "BAAI/bge-small-en-v1.5")
        if not Path(index_dir).is_absolute():
            index_dir = str(P3_ROOT / index_dir)
        try:
            _index = load_index(index_dir, model)
        except Exception as e:
            logger.warning(f"Index load warning: {e}")

    if _graph_engine is None:
        graph_path = P3_ROOT / "corpus/graph/financial_graph.json"
        if graph_path.exists():
            builder = FinancialGraphBuilder.load(graph_path)
            _graph_engine = GraphQueryEngine(builder=builder)
        else:
            builder = FinancialGraphBuilder()
            if _index and hasattr(_index, "chunks"):
                builder.build_from_chunks(_index.chunks)
                builder.save(graph_path)
            _graph_engine = GraphQueryEngine(builder=builder)

    return _cfg, _index, _graph_engine


class QueryRequest(BaseModel):
    query: str
    strategy: str = "hybrid_rerank_graph"
    top_k: int = 8
    session_id: str | None = None
    domain: str = "financial"


@app.post("/api/session/new")
async def new_session():
    """Start a fresh conversation and return its session id."""
    import uuid

    sid = f"conv_{uuid.uuid4().hex[:12]}"
    _CONVERSATIONS[sid] = []
    return {"session_id": sid}


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Return the conversation turns for a session."""
    return {"session_id": session_id, "turns": _CONVERSATIONS.get(session_id, [])}


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>RAGFilings UI</h1><p>Static files missing.</p>")
    return FileResponse(str(index_file))


@app.get("/api/presets")
async def get_presets():
    return {"presets": PRESET_QUESTIONS}


@app.get("/api/history")
async def get_history(limit: int = 20):
    sessions = _memory.get_recent_sessions(limit=limit)
    return {"sessions": sessions}


@app.get("/api/history/{session_id}/trajectory")
async def get_trajectory(session_id: str):
    traj = _memory.get_trajectory(session_id)
    return {"session_id": session_id, "trajectory": traj}


@app.get("/api/graph")
async def get_graph():
    _, _, graph_engine = get_system_components()
    if not graph_engine or not hasattr(graph_engine, "graph"):
        return {"nodes": [], "links": []}

    g = graph_engine.graph
    nodes = []
    for node_id, data in g.nodes(data=True):
        nodes.append(
            {
                "id": node_id,
                "label": data.get("name") or str(node_id),
                "type": data.get("type", "Entity"),
                "ticker": data.get("ticker"),
                "value": data.get("value"),
                "fiscal_year": data.get("fiscal_year"),
            }
        )

    links = []
    for u, v, data in g.edges(data=True):
        links.append(
            {
                "source": u,
                "target": v,
                "relation": data.get("relation", "RELATES_TO"),
            }
        )

    return {
        "nodes": nodes,
        "links": links,
        "stats": {"node_count": len(nodes), "edge_count": len(links)},
    }


@app.post("/api/query")
async def execute_query(req: QueryRequest):
    cfg, index, graph_engine = get_system_components()
    if not index:
        raise HTTPException(
            status_code=500, detail="Search index not available. Please run indexing first."
        )

    # Conversational session: get-or-create, then resolve elliptical follow-ups
    # into a self-contained question so multi-hop grounding still applies.
    session_id = req.session_id
    if not session_id or session_id not in _CONVERSATIONS:
        import uuid

        session_id = session_id or f"conv_{uuid.uuid4().hex[:12]}"
        _CONVERSATIONS.setdefault(session_id, [])
    history = _CONVERSATIONS[session_id]
    from ..domains import get_pack

    pack = get_pack(req.domain)
    rewritten = rewrite_followup(req.query, history, cfg, pack=pack)

    res = ask(
        query=rewritten,
        cfg=cfg,
        index=index,
        strategy=req.strategy,
        domain=req.domain,
        top_k=req.top_k,
        memory=_memory,
    )

    # The orchestrator (agent_react) has its own session id for trajectories;
    # it is distinct from the conversational session_id kept above.
    orch_session_id = res.get("session_id")
    trajectory = _memory.get_trajectory(orch_session_id) if orch_session_id else []
    if not trajectory and res.get("agent_history"):
        trajectory = res["agent_history"]

    # Parse and filter discrete structured tables from retrieved chunks
    tables = []
    q_words = {w.lower() for w in req.query.split() if len(w) > 3}

    for hit in res.get("hits", []):
        chunk = hit.get("chunk", {})
        text = chunk.get("text", "")
        cid = chunk.get("id", "UNKNOWN")
        section = chunk.get("section", "Item8")

        if "|" in text and "\n" in text:
            # Parse distinct sub-tables separated by repeating header lines
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            current_headers = None
            current_rows = []

            for line in lines:
                if "|" not in line:
                    continue
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if not cells:
                    continue

                # Header detection: line with years or short column labels
                is_header_row = any(re.match(r"^(FY)?202[0-9]$", c) for c in cells) or (
                    current_headers is None and len(cells) >= 2
                )

                if is_header_row and current_rows:
                    # Flush previous sub-table
                    if current_headers and len(current_rows) >= 1:
                        # Check relevance to query words
                        table_blob = " ".join(
                            [current_headers[0]] + [r[0] for r in current_rows if r]
                        ).lower()
                        relevance = sum(1 for w in q_words if w in table_blob)
                        tables.append(
                            {
                                "chunk_id": cid,
                                "section": section,
                                "title": f"Filing Table · {section}",
                                "headers": current_headers,
                                "rows": current_rows,
                                "relevance": relevance,
                            }
                        )
                    current_headers = cells
                    current_rows = []
                elif current_headers is None:
                    current_headers = cells
                else:
                    # Clean up data cells, removing spaces inside parentheses like "( 338 )" -> "($338)"
                    cleaned_cells = [re.sub(r"\(\s*([0-9,]+)\s*\)", r"(\1)", c) for c in cells]
                    # Filter out purely non-data rows like "Basic 3,225" if incomplete
                    if len(cleaned_cells) >= 2:
                        current_rows.append(cleaned_cells)

            if current_headers and len(current_rows) >= 1:
                table_blob = " ".join(
                    [current_headers[0]] + [r[0] for r in current_rows if r]
                ).lower()
                relevance = sum(1 for w in q_words if w in table_blob)
                tables.append(
                    {
                        "chunk_id": cid,
                        "section": section,
                        "title": f"Filing Table · {section}",
                        "headers": current_headers,
                        "rows": current_rows,
                        "relevance": relevance,
                    }
                )

    # Sort tables by relevance to query and keep top 2 most relevant tables
    if tables:
        tables.sort(key=lambda t: t.get("relevance", 0), reverse=True)
        tables = tables[:2]

    # Prepare chart metrics dynamically from graph facts, query, or retrieved tables
    chart_data = None
    if graph_engine:
        # 1. Detect target ticker from query or top hits with word boundaries
        q_upper = req.query.upper()
        detected_ticker = None
        known_tickers = [
            "META",
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "GOOGL",
            "TSLA",
            "JPM",
            "BAC",
            "GS",
            "WMT",
            "COST",
            "JNJ",
            "PFE",
            "UNH",
            "XOM",
            "CVX",
            "KO",
            "PEP",
            "PG",
            "DIS",
            "NFLX",
            "BA",
            "CAT",
            "HD",
        ]
        for t in known_tickers:
            if re.search(rf"\b{re.escape(t)}\b", q_upper):
                detected_ticker = t
                break

        if not detected_ticker:
            name_map = {
                "META": r"\b(FACEBOOK|META)\b",
                "GOOGL": r"\b(GOOGLE|ALPHABET)\b",
                "AAPL": r"\bAPPLE\b",
                "TSLA": r"\bTESLA\b",
                "MSFT": r"\bMICROSOFT\b",
                "AMZN": r"\bAMAZON\b",
                "NVDA": r"\bNVIDIA\b",
                "JPM": r"\bJPMORGAN\b",
                "WMT": r"\bWALMART\b",
                "HD": r"\bHOME\s+DEPOT\b",
                "CAT": r"\bCATERPILLAR\b",
                "BA": r"\bBOEING\b",
            }
            for ticker, pat in name_map.items():
                if re.search(pat, q_upper):
                    detected_ticker = ticker
                    break

        if not detected_ticker and res.get("hits"):
            detected_ticker = res["hits"][0].get("chunk", {}).get("ticker")

        # 2. Detect metric candidate from query
        q_lower = req.query.lower()
        detected_metric = "Net Sales"
        if "research and development" in q_lower or "r&d" in q_lower:
            detected_metric = "R&D Expense"
        elif "cash flow" in q_lower or "operating activities" in q_lower:
            detected_metric = "Operating Cash Flow"
        elif "regulatory credit" in q_lower or "automotive" in q_lower:
            detected_metric = "Automotive Revenues"
        elif "gross margin" in q_lower:
            detected_metric = "Gross Margin"
        elif "operating margin" in q_lower or "operating income" in q_lower:
            detected_metric = "Operating Income"
        elif "revenue" in q_lower or "sales" in q_lower:
            detected_metric = "Total Revenue"

        if detected_ticker:
            metric_history = graph_engine.get_metric_history(detected_ticker, detected_metric)
            chart_metric_title = detected_metric
            if not metric_history and detected_metric != "Total Revenue":
                # Try fallback to Total Revenue or Net Sales, labeling explicitly
                fallback_hist = graph_engine.get_metric_history(
                    detected_ticker, "Total Revenue"
                ) or graph_engine.get_metric_history(detected_ticker, "Net Sales")
                if fallback_hist:
                    metric_history = fallback_hist
                    chart_metric_title = (
                        f"Total Revenue (Alternative History, {detected_metric} unavailable)"
                    )

            if metric_history:
                # Deduplicate by fiscal_year to guarantee distinct years
                unique_by_year = {}
                for m in metric_history:
                    fy = m.get("fiscal_year")
                    if fy and fy not in unique_by_year:
                        unique_by_year[fy] = m

                sorted_hist = sorted(
                    unique_by_year.values(), key=lambda x: str(x.get("fiscal_year", ""))
                )
                if len(sorted_hist) >= 2:
                    chart_data = {
                        "ticker": detected_ticker,
                        "metric": chart_metric_title,
                        "title": f"{detected_ticker} · {chart_metric_title} Trajectory ($ Millions)",
                        "labels": [f"FY{m['fiscal_year']}" for m in sorted_hist],
                        "values": [m["value"] for m in sorted_hist],
                        "unit": "USD_M",
                    }

    # Persist the conversational turns (user asked, assistant answered).
    assistant_text = res.get("answer") or res.get("refusal_reason") or ""
    _CONVERSATIONS[session_id].append({"role": "user", "content": req.query})
    _CONVERSATIONS[session_id].append({"role": "assistant", "content": assistant_text})

    return {
        "session_id": session_id,
        "query": req.query,
        "rewritten_query": rewritten,
        "strategy": req.strategy,
        "answer": res.get("answer"),
        "refused": res.get("refused", False),
        "refusal_reason": res.get("refusal_reason"),
        "citations": res.get("citations", []),
        "invalid_citations": res.get("invalid_citations", []),
        "confidence": res.get("confidence", 0.0),
        "latency_ms": res.get("latency_ms", 0.0),
        "usage": res.get("usage", {}),
        "verified": res.get("verified", False),
        "verification": res.get("verification", {}),
        "math_result": res.get("math_result"),
        "graph_facts": res.get("graph_facts", []),
        "graph_rescue": res.get("graph_rescue"),
        "tables": tables[:3],
        "chart_data": chart_data,
        "trajectory": trajectory,
        "hits": [
            {
                "id": h["chunk"]["id"],
                "score": h["score"],
                "section": h["chunk"].get("section"),
                "text": h["chunk"].get("text"),
            }
            for h in res.get("hits", [])[:6]
        ],
    }
