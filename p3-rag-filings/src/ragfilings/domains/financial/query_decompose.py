"""Query Decomposition Engine.

Detects complex, multi-year, or multi-step calculation queries and breaks them
into focused sub-queries targeting specific financial filing sections or periods.
"""

from __future__ import annotations

import json
from typing import Any

from ...llm import complete_with_resilience
from ...prompts import PromptRegistry

_MATH_KEYWORDS = (
    "growth rate",
    "cagr",
    "average",
    "percentage change",
    "increased or decreased",
    "compare",
    "difference",
    "margin delta",
    "ratio",
    "3-year",
    "multi-year",
    "how much did",
    "faster than",
    "split between",
    "combine",
    "combined",
    "percentage",
    "percent",
    "share",
    "portion",
    "fraction",
    "proportion",
    "contribution",
    "contribute",
    "contributed",
    "sum",
    "total of",
    "margin",
    "versus",
    " vs ",
    "grow",
    "grew",
)


def needs_decomposition(query: str) -> bool:
    """Return True if the query asks for multi-year math or comparative synthesis."""
    q_lower = query.lower()
    return any(kw in q_lower for kw in _MATH_KEYWORDS)


def decompose_query(query: str, cfg: dict[str, Any]) -> list[str]:
    """Decompose a complex financial question into 2-3 focused retrieval sub-queries."""
    if not needs_decomposition(query):
        return [query]

    messages = [
        {"role": "system", "content": PromptRegistry.get_query_decompose()},
        {"role": "user", "content": query},
    ]

    try:
        text, _ = complete_with_resilience(messages, cfg, role="planning")
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            sub_queries = json.loads(text[start : end + 1])
            if isinstance(sub_queries, list) and len(sub_queries) > 0:
                cleaned = [str(sq) for sq in sub_queries if isinstance(sq, str) and sq.strip()]
                return [query] + cleaned
    except Exception:
        pass

    return [query]
