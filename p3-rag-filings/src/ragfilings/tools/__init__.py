"""Specialized RAG Tools Package.

Canonical implementations reside under `ragfilings.domains.financial`.
"""

from __future__ import annotations

from ..domains.financial.math_tool import compute_financial_math, safe_eval
from ..domains.financial.query_decompose import decompose_query, needs_decomposition
from ..domains.financial.verification import extract_claims, verify

__all__ = [
    "safe_eval",
    "compute_financial_math",
    "needs_decomposition",
    "decompose_query",
    "extract_claims",
    "verify",
]
