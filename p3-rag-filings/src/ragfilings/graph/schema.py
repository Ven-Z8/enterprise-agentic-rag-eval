"""Knowledge Graph Schema Definitions and Ontologies."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class EntityNode:
    """Base graph node."""

    id: str
    label: Literal[
        "Company", "Filing", "Section", "FinancialMetric", "FiscalYear", "TableNode", "VisualFigure"
    ]
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RelationEdge:
    """Typed edge between graph entity nodes."""

    source: str
    target: str
    relation: Literal[
        "REPORTED_IN",
        "HAS_SECTION",
        "CONTAINS_METRIC",
        "RECORDED_VALUE",
        "FOR_FISCAL_YEAR",
        "CITES_CHUNK",
        "HAS_TABLE",
        "HAS_FIGURE",
        "COMPARED_WITH",
    ]
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
