"""Financial domain pack — SEC 10-K filings.

Fact layer: deterministic table parsing into a typed fact graph
(Company → Year → Metric → Value with chunk provenance). Scope agent:
ticker/metric/fiscal-year rescue + deterministic clarifications. Claim
semantics: monetary / percentage figures with unit scaling. Derivation tool:
safe Python financial math.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from .. import DomainPack
from .math_tool import compute_financial_math
from .query_decompose import decompose_query, needs_decomposition
from .verification import verify as verify_claims


class FinancialPack(DomainPack):
    """SEC 10-K filings: modular markdown phases + deterministic financial math & rescue."""

    name: ClassVar[str] = "financial"
    display_name: ClassVar[str] = "SEC 10-K Filings"

    def __init__(self, pack_dir: str | Path | None = None) -> None:
        if pack_dir is None:
            pack_dir = Path(__file__).resolve().parent
        super().__init__(pack_dir)

    def needs_decomposition(self, query: str) -> bool:
        return needs_decomposition(query)

    def decompose_query(self, query: str, cfg: dict[str, Any]) -> list[str]:
        return decompose_query(query, cfg)

    def load_rescue(self, cfg: dict[str, Any], index: Any) -> Any | None:
        from .loader import load_rescue

        return load_rescue(cfg, index)

    def compute(
        self, query: str, chunks: list[dict[str, Any]], cfg: dict[str, Any], client: Any = None
    ) -> dict[str, Any] | None:
        return compute_financial_math(query, chunks, cfg, client=client)

    def verify(
        self,
        answer_text: str,
        chunks: list[dict[str, Any]],
        math_result: dict[str, Any] | None = None,
        derived_values: list[float] | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        return verify_claims(
            answer_text, chunks, math_result=math_result, derived_values=derived_values, query=query
        )


FinancialSkill = FinancialPack
PACK = FinancialPack()

__all__ = ["PACK", "FinancialPack", "FinancialSkill"]
