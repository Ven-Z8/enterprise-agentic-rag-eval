"""Query engine over the financial fact graph + community layer.

Every answer returned by this engine carries provenance (the chunk id the
value was parsed from), so graph-sourced facts are auditable end to end.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import networkx as nx

from .builder import KNOWN_METRICS, FinancialGraphBuilder

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9&]+")


def _canon_metric(metric_name: str) -> str:
    low = metric_name.lower().strip()
    if low in KNOWN_METRICS:
        return KNOWN_METRICS[low]
    for phrase, canon in sorted(KNOWN_METRICS.items(), key=lambda kv: len(kv[0]), reverse=True):
        if phrase in low:
            return canon
    return metric_name.strip().title()


class GraphQueryEngine:
    """High-level query interface for agent tools."""

    def __init__(
        self, builder: FinancialGraphBuilder | None = None, graph: nx.DiGraph | None = None
    ) -> None:
        self._builder = builder
        if builder is not None:
            self.graph = builder.graph
            self.communities = builder.communities
        elif graph is not None:
            self.graph = graph
            self.communities = []
        else:
            self.graph = nx.DiGraph()
            self.communities = []

    # ------------------------------------------------------------ fact queries

    def _value_nodes(
        self, ticker: str | None = None, metric: str | None = None, fiscal_year: str | None = None
    ) -> list[dict[str, Any]]:
        canon = _canon_metric(metric) if metric else None
        out = []
        for _, data in self.graph.nodes(data=True):
            if data.get("label") != "MetricValue":
                continue
            if ticker and data.get("ticker") != ticker.upper():
                continue
            if canon and data.get("metric") != canon:
                continue
            if fiscal_year and str(data.get("fiscal_year")) != str(fiscal_year):
                continue
            out.append(data)
        return out

    def get_metric_value(
        self, ticker: str, metric_name: str, fiscal_year: int | str
    ) -> dict[str, Any] | None:
        """Exact single fact: value + unit + provenance chunk."""
        rows = self._value_nodes(ticker, metric_name, fiscal_year)
        if not rows:
            return None
        d = rows[0]
        return {
            "ticker": d.get("ticker"),
            "metric": d.get("metric"),
            "fiscal_year": d.get("fiscal_year"),
            "value": d.get("value"),
            "unit": d.get("unit"),
            "chunk_id": d.get("chunk_id"),
        }

    def get_metric_history(self, ticker: str, metric_name: str) -> list[dict[str, Any]]:
        """Multi-year series for one company metric, oldest first."""
        rows = self._value_nodes(ticker, metric_name)
        series = [
            {
                "ticker": d.get("ticker"),
                "metric": d.get("metric"),
                "fiscal_year": d.get("fiscal_year"),
                "value": d.get("value"),
                "unit": d.get("unit"),
                "chunk_id": d.get("chunk_id"),
            }
            for d in rows
        ]
        return sorted(series, key=lambda x: str(x.get("fiscal_year", "")))

    def compare_metrics(
        self, tickers: list[str], metric_name: str, fiscal_year: str | int | None = None
    ) -> list[dict[str, Any]]:
        """Same metric across companies (optionally one year)."""
        results = []
        for t in tickers:
            hist = self.get_metric_history(t, metric_name)
            if fiscal_year is not None:
                hist = [h for h in hist if str(h.get("fiscal_year")) == str(fiscal_year)]
            results.extend(hist)
        return results

    # ------------------------------------------------------ narrative queries

    def community_search(self, query: str, top_k: int = 2) -> list[dict[str, Any]]:
        """Match query keywords against community profiles (members + summaries)."""
        tokens = set(_TOKEN_RE.findall(query.lower()))
        if not tokens or not self.communities:
            return []
        scored = []
        for comm in self.communities:
            profile = " ".join(comm.get("members", [])) + " " + (comm.get("summary") or "")
            profile_tokens = set(_TOKEN_RE.findall(profile.lower()))
            overlap = len(tokens & profile_tokens)
            if overlap:
                scored.append((overlap, comm))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": c["id"],
                "members": c["members"][:15],
                "size": c.get("size"),
                "n_chunks": c.get("n_chunks"),
                "chunk_ids": c.get("chunk_ids", [])[:10],
                "summary": c.get("summary"),
            }
            for _, c in scored[:top_k]
        ]

    # ---------------------------------------------------------- misc traversal

    def find_entity_subgraph(self, ticker: str, radius: int = 2) -> dict[str, Any]:
        """Ego-subgraph around a company node (for UI visualization)."""
        cid = f"company:{ticker.upper()}"
        if not self.graph.has_node(cid):
            return {"nodes": [], "edges": []}
        sub = nx.ego_graph(self.graph.to_undirected(), cid, radius=radius)
        nodes = [{"id": n, **self.graph.nodes[n]} for n in sub.nodes()]
        edges = [
            {"source": u, "target": v, **self.graph.get_edge_data(u, v, default={})}
            for u, v in sub.edges()
            if self.graph.has_edge(u, v)
        ]
        return {"nodes": nodes, "edges": edges}
