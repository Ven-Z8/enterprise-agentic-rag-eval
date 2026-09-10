"""Pydantic schemas for instructor-validated structured outputs.

Every agent-to-agent contract in the pipeline is one of these models;
nothing is scraped out of free text.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class SynthesisResponse(BaseModel):
    """Output schema for the grounded synthesis stage."""

    status: Literal["answered", "refused", "clarification_needed"] = Field(
        default="answered",
        description="Whether the question is answered from context, refused due to lack of evidence, or needs clarification.",
    )
    answer: str | None = Field(
        default=None,
        description="Concise answer with exact figures or text as stated in the chunks or derived from calculations.",
    )
    citations: list[str] = Field(
        default_factory=list,
        description="IDs of source chunks directly supporting the answer.",
    )
    reason: str | None = Field(
        default=None,
        description="Refusal explanation if answer is null, or clarification reasoning.",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize alternative answer keys
            if "answer" not in data:
                for k in ("result", "final_answer", "response", "output", "value", "percentage_change", "change"):
                    if k in data:
                        data["answer"] = data[k]
                        break
            if "status" not in data:
                ans = data.get("answer")
                data["status"] = "refused" if ans is None else "answered"
        return data


# Canonical synthesis response contract (aliased for unified agent contracts)
SynthesizedAnswer = SynthesisResponse


class DecompositionPlan(BaseModel):
    """Output schema for query decomposition and retrieval planning."""

    needs_decomposition: bool = Field(
        description="True if the query requires multi-part, multi-year, or comparative retrieval.",
    )
    sub_queries: list[str] = Field(
        default_factory=list,
        description="List of 2-3 focused single-point retrieval sub-queries.",
    )
    reasoning: str = Field(
        default="",
        description="Brief rationale for decomposition decision.",
    )


class RewrittenQuery(BaseModel):
    """Output schema for conversational follow-up rewriting."""

    rewritten_query: str = Field(
        description="One fully self-contained question resolving all pronouns, ellipses, and chained arithmetic values.",
    )
    reasoning: str = Field(
        default="",
        description="Brief note on resolved entities or substituted values.",
    )


class QueryPlan(BaseModel):
    """Output schema for the Planner agent."""

    intent: str = Field(
        description="One of: lookup | comparison | computation | synthesis | not_in_corpus."
    )
    ticker: str | None = Field(
        default=None,
        description="Ticker of the company the question targets, only if clearly stated (e.g. AAPL).",
    )
    fiscal_year: int | None = Field(
        default=None, description="Fiscal year targeted by the question, if stated."
    )
    sub_questions: list[str] = Field(
        default_factory=list,
        description="1-3 focused retrieval questions; for simple lookups repeat the main question.",
    )
    needs_math: bool = Field(
        default=False,
        description="True only if answering requires arithmetic over retrieved figures (growth, margin, delta).",
    )
    reasoning: str = Field(default="", description="One sentence of planning rationale.")


class AuditClaim(BaseModel):
    """Audit detail for a single numerical claim."""

    figure: str = Field(description="The extracted figure or percentage claim.")
    found_in_chunk: str | None = Field(
        default=None, description="Chunk ID where figure was verified."
    )
    status: str = Field(description="VERIFIED or UNVERIFIED.")


class AuditResult(BaseModel):
    """Output schema for Compliance & Verification Auditor Sub-Agent."""

    verified: bool = Field(
        description="True if all numerical claims are present in cited 10-K context."
    )
    refuse: bool = Field(
        default=False, description="True if context lacks sufficient data to answer."
    )
    audit_claims: list[AuditClaim] = Field(
        default_factory=list, description="Detailed audit per figure."
    )
