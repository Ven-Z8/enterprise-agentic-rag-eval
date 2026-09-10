"""Knowledge Graph Subsystem.

Canonical implementations reside under `ragfilings.domains.financial`.
This package provides direct access to the financial graph builder, query engine,
and deterministic scope/rescue components.
"""

from __future__ import annotations

from ..domains.financial.builder import KNOWN_METRICS, FinancialGraphBuilder
from ..domains.financial.loader import graph_path, load_graph_engine, load_rescue
from ..domains.financial.query import GraphQueryEngine
from ..domains.financial.rescue import (
    GraphRescue,
    RescueOutcome,
    RescueQuery,
    load_company_aliases,
    load_company_names,
    load_excluded_facts,
)

__all__ = [
    "FinancialGraphBuilder",
    "GraphQueryEngine",
    "GraphRescue",
    "RescueOutcome",
    "RescueQuery",
    "graph_path",
    "load_company_aliases",
    "load_company_names",
    "load_excluded_facts",
    "load_graph_engine",
    "load_rescue",
    "KNOWN_METRICS",
]
