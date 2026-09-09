"""Researcher agent — real tool loop over retrieval.

The researcher is a genuine function-calling agent: it decides search
queries and filters via search_filings / list_filings tool calls, and every
call is recorded as a tool event with real API usage accounting.
"""

from __future__ import annotations

import json
from typing import Any

from ..llm import get_llm_client, get_model_for_role
from ..prompts import PromptRegistry
from ..schemas import QueryPlan
from .tool_loop import run_tool_loop

_SNIPPET_CHARS = 600

_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_filings",
        "description": (
            "Search the SEC 10-K chunk index. Returns ranked hits with id, "
            "ticker, fiscal year, 10-K item, title, and a text snippet."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Retrieval question."},
                "ticker": {
                    "type": "string",
                    "description": "Optional ticker filter, e.g. AAPL.",
                },
                "fiscal_year": {
                    "type": "integer",
                    "description": "Optional fiscal year filter, e.g. 2025.",
                },
                "tables_only": {
                    "type": "boolean",
                    "description": "Restrict to chunks containing tables.",
                },
            },
            "required": ["query"],
        },
    },
}

_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": "list_filings",
        "description": "List the filings (ticker + fiscal years) in the corpus.",
        "parameters": {"type": "object", "properties": {}},
    },
}

_GRAPH_TOOL = {
    "type": "function",
    "function": {
        "name": "query_graph",
        "description": (
            "Query the structured financial fact graph — values parsed "
            "deterministically from 10-K tables, each with a provenance "
            "chunk id. Operations: metric_value (ticker + metric + "
            "fiscal_year), metric_series (ticker + metric, all years), "
            "compare (tickers + metric, optionally fiscal_year), community "
            "(keyword search over narrative clusters). Prefer this over "
            "search_filings for exact figures and year-over-year series."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["metric_value", "metric_series", "compare", "community"],
                },
                "ticker": {"type": "string"},
                "tickers": {"type": "array", "items": {"type": "string"}},
                "metric": {"type": "string"},
                "fiscal_year": {"type": "integer"},
                "query": {"type": "string", "description": "Keywords for the community operation."},
            },
            "required": ["operation"],
        },
    },
}


def _run_graph_query(graph_engine: Any, args: dict[str, Any]) -> str:
    op = args.get("operation")
    try:
        if op == "metric_value":
            result = graph_engine.get_metric_value(
                args["ticker"], args["metric"], args["fiscal_year"]
            )
        elif op == "metric_series":
            result = graph_engine.get_metric_history(args["ticker"], args["metric"])
        elif op == "compare":
            tickers = args.get("tickers") or ([args["ticker"]] if args.get("ticker") else [])
            result = graph_engine.compare_metrics(tickers, args["metric"], args.get("fiscal_year"))
        elif op == "community":
            result = graph_engine.community_search(str(args.get("query", "")))
        else:
            return f"TOOL ERROR: unknown operation {op!r}"
    except (KeyError, TypeError) as e:
        return f"TOOL ERROR: missing or bad argument: {e}"
    return json.dumps(result if result is not None else {})


def _hit_summary(hit: dict[str, Any]) -> dict[str, Any]:
    chunk = hit["chunk"]
    return {
        "id": chunk["id"],
        "ticker": chunk.get("ticker"),
        "fiscal_year": chunk.get("fiscal_year"),
        "item": chunk.get("item"),
        "title": chunk.get("title"),
        "score": round(float(hit["score"]), 4),
        "dense_sim": round(float(hit["dense_sim"]), 4),
        "snippet": chunk["text"][:_SNIPPET_CHARS],
    }


def run_researcher(
    query: str,
    plan: QueryPlan,
    index: Any,
    cfg: dict[str, Any],
    usage: dict[str, Any],
    graph_engine: Any = None,
) -> dict[str, Any]:
    """Execute the researcher tool loop. Returns hits + tool events.

    `usage` is the orchestrator's accumulator; all tool-loop API usage is
    added to it, so total cost is exact.
    """
    strat = cfg.get("retrieval", {}).get("strategy", "hybrid_rerank")
    top_k = cfg.get("retrieval", {}).get("top_k", 8)
    rerank_candidates = cfg.get("retrieval", {}).get("rerank_candidates", 25)
    inventory = {str(c.get("ticker")) for c in index.chunks if c.get("ticker")}
    chunk_by_id = {c["id"]: c for c in index.chunks if c.get("id")}

    collected: dict[str, dict[str, Any]] = {}

    def executor(name: str, args: dict[str, Any]) -> str:
        if name == "list_filings":
            years: dict[str, set[str]] = {}
            for c in index.chunks:
                if c.get("ticker"):
                    years.setdefault(str(c["ticker"]), set()).add(str(c.get("fiscal_year")))
            return json.dumps(sorted(f"{t}: FY{sorted(ys)}" for t, ys in years.items()))
        if name == "query_graph":
            if graph_engine is None:
                return "TOOL ERROR: fact graph is not available"
            out = _run_graph_query(graph_engine, args)
            try:
                data = json.loads(out)
            except json.JSONDecodeError:
                data = None
            rows = data if isinstance(data, list) else ([data] if data else [])
            for row in rows:
                cid = row.get("chunk_id") if isinstance(row, dict) else None
                if cid and cid not in collected and cid in chunk_by_id:
                    collected[cid] = {"chunk": chunk_by_id[cid], "score": 1.0, "dense_sim": 1.0}
            return out
        if name != "search_filings":
            return f"TOOL ERROR: unknown tool {name!r}"

        filters: dict[str, Any] = {}
        ticker = args.get("ticker")
        if ticker and str(ticker).upper() in inventory:
            filters["ticker"] = str(ticker).upper()
        year = args.get("fiscal_year")
        if year:
            filters["fiscal_year"] = year
        if args.get("tables_only"):
            filters["has_table"] = True

        hits = index.search(
            str(args.get("query", query)),
            strat,
            top_k,
            filters=filters or None,
            rerank_candidates=rerank_candidates,
            reranker_name=cfg.get("retrieval", {}).get("reranker"),
        )
        if not hits and filters:
            # Filtered search found nothing: retry unfiltered so the agent
            # sees evidence (or its absence) rather than a silent empty set.
            hits = index.search(
                str(args.get("query", query)),
                strat,
                top_k,
                rerank_candidates=rerank_candidates,
                reranker_name=cfg.get("retrieval", {}).get("reranker"),
            )
        for h in hits:
            collected.setdefault(h["chunk"]["id"], h)
        return json.dumps([_hit_summary(h) for h in hits])

    sub_questions = plan.sub_questions or [query]
    task = "\n".join(f"- {sq}" for sq in sub_questions)
    scope = []
    if plan.ticker:
        scope.append(f"ticker={plan.ticker}")
    if plan.fiscal_year:
        scope.append(f"fiscal_year={plan.fiscal_year}")
    scope_line = f"Plan scope filters: {', '.join(scope)}" if scope else "Plan scope: no filters."

    messages = [
        {"role": "system", "content": PromptRegistry.get_researcher()},
        {
            "role": "user",
            "content": f"Original question: {query}\n{scope_line}\n\nRetrieval questions:\n{task}",
        },
    ]

    client = get_llm_client(cfg=cfg, role="runtime")
    model = get_model_for_role(cfg, "runtime") or client.default_model

    tools = [_SEARCH_TOOL, _LIST_TOOL]
    if graph_engine is not None:
        tools.append(_GRAPH_TOOL)

    notes, events = run_tool_loop(
        client=client.openai_client,
        model=model,
        messages=messages,
        tools=tools,
        executor=executor,
        usage=usage,
        max_steps=cfg.get("researcher", {}).get("max_steps", 6),
    )

    hits = sorted(collected.values(), key=lambda h: h["dense_sim"], reverse=True)
    return {"hits": hits[: top_k * 2], "events": events, "notes": notes}
