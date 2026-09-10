"""Financial Domain Skill implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from ...domains.financial.math_tool import compute_financial_math
from ...domains.financial.query_decompose import decompose_query, needs_decomposition
from ...domains.financial.verification import verify as verify_claims
from ..base import DomainSkill


class FinancialSkill(DomainSkill):
    """SEC 10-K filings: modular markdown phases + deterministic financial math & rescue."""

    name: ClassVar[str] = "financial"
    display_name: ClassVar[str] = "SEC 10-K Filings"

    def __init__(self, skill_dir: str | Path | None = None) -> None:
        if skill_dir is None:
            skill_dir = Path(__file__).resolve().parent
        super().__init__(skill_dir)

    def needs_decomposition(self, query: str) -> bool:
        return needs_decomposition(query)

    def decompose_query(self, query: str, cfg: dict[str, Any]) -> list[str]:
        return decompose_query(query, cfg)

    def load_rescue(self, cfg: dict[str, Any], index: Any) -> Any | None:
        from ...domains.financial.loader import load_rescue

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
