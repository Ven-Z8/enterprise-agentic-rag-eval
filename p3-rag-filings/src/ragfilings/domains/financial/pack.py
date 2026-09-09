"""Financial pack implementation — wraps the 10-K engine components."""

from __future__ import annotations

from typing import Any, ClassVar

from ...prompts import PromptRegistry
from .. import DomainPack
from .math_tool import compute_financial_math
from .query_decompose import decompose_query, needs_decomposition
from .verification import verify as verify_claims


class FinancialPack(DomainPack):
    """SEC 10-K filings: fact graph + monetary claim semantics."""

    name: ClassVar[str] = "financial"
    display_name: ClassVar[str] = "SEC 10-K Filings"

    # ------------------------------------------------------------- prompts

    def prompt(self, name: str) -> str:
        return PromptRegistry.get_raw(name)

    def format_prompt(self, name: str, **kwargs: Any) -> str:
        # verification_retry accepts a claim list; join it exactly like the
        # registry helper so the rendered prompt is byte-identical.
        if name == "verification_retry" and isinstance(kwargs.get("failed_claims"), list):
            kwargs["failed_claims"] = ", ".join(kwargs["failed_claims"])
        return PromptRegistry.format(name, **kwargs)

    # ------------------------------------------- retrieval-time query shape

    def needs_decomposition(self, query: str) -> bool:
        return needs_decomposition(query)

    def decompose_query(self, query: str, cfg: dict[str, Any]) -> list[str]:
        return decompose_query(query, cfg)

    # --------------------------------- deterministic fact layer + scope agent

    def load_rescue(self, cfg: dict[str, Any], index: Any) -> Any | None:
        from .loader import load_rescue

        return load_rescue(cfg, index)

    # --------------------------------------------------- synthesis-time tools

    def compute(
        self, query: str, chunks: list[dict[str, Any]], cfg: dict[str, Any], client: Any = None
    ) -> dict[str, Any] | None:
        return compute_financial_math(query, chunks, cfg, client=client)

    # ------------------------------------------------------- claim semantics

    def verify(
        self,
        answer_text: str,
        chunks: list[dict[str, Any]],
        math_result: dict[str, Any] | None = None,
        derived_values: list[float] | None = None,
    ) -> dict[str, Any]:
        return verify_claims(
            answer_text, chunks, math_result=math_result, derived_values=derived_values
        )


__all__ = ["FinancialPack"]
