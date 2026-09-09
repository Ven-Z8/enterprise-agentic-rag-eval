"""Shared loaders for the fact graph and the rescue layer."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def graph_path(cfg: dict[str, Any] | None = None):
    from ... import config as cfg_mod

    return cfg_mod.ROOT / "corpus" / "graph" / "financial_graph.json"


def load_graph_engine(cfg: dict[str, Any], index: Any = None) -> Any:
    """Load the fact graph; build + persist it from the index on first use.

    Returns None when the graph is unavailable — it is an enhancement, not
    a gate, so callers degrade to plain retrieval.
    """
    from .builder import FinancialGraphBuilder
    from .query import GraphQueryEngine

    path = graph_path(cfg)
    try:
        builder = FinancialGraphBuilder.load(path)
        if builder.graph.number_of_nodes() == 0 and index is not None:
            builder.build_from_chunks(index.chunks)
            builder.build_communities(index.chunks)
            builder.save(path)
        return GraphQueryEngine(builder=builder)
    except Exception as e:  # noqa: BLE001 — graph is an enhancement, not a gate
        logger.warning("fact graph unavailable: %s", e)
        return None


def load_rescue(cfg: dict[str, Any], index: Any) -> Any:
    """GraphRescue wired to the corpus graph, manifest, and chunk index.

    Returns None when any dependency is missing (rescue is optional).
    """
    from .builder import FinancialGraphBuilder
    from .query import GraphQueryEngine
    from .rescue import GraphRescue, load_company_aliases, load_company_names, load_excluded_facts

    path = graph_path(cfg)
    try:
        builder = FinancialGraphBuilder.load(path)
        if builder.graph.number_of_nodes() == 0:
            return None
        engine = GraphQueryEngine(builder=builder)
        chunks_by_id = {c["id"]: c for c in index.chunks if c.get("id")}
        return GraphRescue(
            engine=engine,
            chunks_by_id=chunks_by_id,
            company_aliases=load_company_aliases(),
            excluded=load_excluded_facts(),
            company_names=load_company_names(),
        )
    except Exception as e:  # noqa: BLE001 — rescue is an enhancement, not a gate
        logger.warning("graph rescue unavailable: %s", e)
        return None
