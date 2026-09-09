"""Pydantic schemas for instructor-validated structured outputs.

Every agent-to-agent contract in the pipeline is one of these models;
nothing is scraped out of free text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class DecomposedQueries(BaseModel):
    """Output schema for Financial Analyst Sub-Agent query decomposition."""

    sub_queries: list[str] = Field(
        description="List of 2-3 focused single-point retrieval sub-queries targeting SEC 10-K tables."
    )


class MathExpression(BaseModel):
    """Output schema for Quantitative Math Specialist Sub-Agent calculation formulation."""

    expression: str = Field(
        description="A single Python mathematical expression using literal numbers and arithmetic operators (+, -, *, /, **)."
    )
    explanation: str = Field(
        description="Brief financial explanation of the calculation (e.g. Growth rate from FY2023 to FY2025)."
    )


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


class SynthesizedAnswer(BaseModel):
    """Output schema for RAG Synthesis pass."""

    answer: str | None = Field(
        description="Concise, cited answer to user question or null if unanswerable."
    )
    citations: list[str] = Field(
        default_factory=list, description="List of cited chunk IDs (e.g. AAPL_2025_10K:Item8:c015)."
    )
    reason: str | None = Field(default=None, description="Refusal reason if answer is null.")
