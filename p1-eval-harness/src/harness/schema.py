"""Domain-Adaptive Agent Eval Harness Schema Definitions.

Defines schemas for:
  - Golden Case (v0 frozen schema)
  - Agent Run Trajectory Trace (recording every step, tool call, latency, cost)
  - Metric Results & Evaluation Summary
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

EXPECTED_TYPES = ("exact", "contains", "judge")
DIFFICULTIES = ("easy", "medium", "hard")
FAILURE_CATEGORIES = ("lookup", "synthesis", "table", "unanswerable", "ambiguous")


class ExpectedOutcome(BaseModel):
    """Ground truth expected outcome for a test case."""
    answer: Optional[str] = Field(default=None, description="Expected answer string or null if unanswerable.")
    citations: List[str] = Field(default_factory=list, description="Expected citation chunk IDs.")
    type: Literal["exact", "contains", "judge"] = Field(default="judge", description="Evaluation type: exact, contains, or judge.")


class GoldenCase(BaseModel):
    """Frozen v0 schema for evaluation test cases."""
    id: str = Field(description="Unique case identifier (e.g. fin-0001, b20-001).")
    input: str = Field(description="User prompt or question.")
    expected: ExpectedOutcome = Field(description="Expected ground truth outcome.")
    variation_rules: List[str] = Field(default_factory=list, description="Rules like numeric_tolerance:0.5%, unit_equivalence.")
    difficulty: Literal["easy", "medium", "hard"] = Field(default="medium", description="Case difficulty: easy, medium, hard.")
    failure_category: Literal["lookup", "synthesis", "table", "unanswerable", "ambiguous"] = Field(default="lookup", description="Target failure category: lookup, synthesis, table, unanswerable, ambiguous.")
    domain: str = Field(default="financial", description="Domain: financial, biomedical, legal, healthcare.")
    notes: Optional[str] = Field(default=None, description="Case notes or design objective.")

    @model_validator(mode="after")
    def validate_invariants(self) -> GoldenCase:
        if self.failure_category in ("unanswerable", "ambiguous") and self.expected.answer is not None:
            raise ValueError(f"{self.failure_category} case must have expected.answer = null")
        if self.expected.type in ("exact", "contains") and self.expected.answer is None:
            if self.failure_category not in ("unanswerable", "ambiguous"):
                raise ValueError(f"type {self.expected.type!r} requires a non-null expected.answer")
        return self


class TrajectoryStep(BaseModel):
    """[DEPRECATED] Individual execution step within an agent run trajectory.
    Kept for backward compatibility with external consumers; active harness uses harness.traces.
    """
    step_number: int = Field(description="1-based sequence index.")
    agent: str = Field(description="Name of the sub-agent or node.")
    action: str = Field(description="Action name or tool invoked.")
    input_payload: Optional[Any] = Field(default=None, description="Input parameters passed to step.")
    output_payload: Optional[Any] = Field(default=None, description="Output returned from step.")
    latency_ms: float = Field(default=0.0, description="Step latency in milliseconds.")


class AgentRunTrace(BaseModel):
    """[DEPRECATED] Structured JSON trajectory trace of a full agent run.
    Kept for backward compatibility with external consumers; active harness uses harness.traces.
    """
    case_id: str = Field(description="ID of the executed golden case.")
    domain: str = Field(description="Domain of the test case.")
    strategy: str = Field(description="Agent strategy executed.")
    query: str = Field(description="Query string.")
    answer: Optional[str] = Field(default=None, description="Generated answer.")
    citations: List[str] = Field(default_factory=list, description="Citations produced.")
    refused: bool = Field(default=False, description="Whether agent refused to answer.")
    refusal_reason: Optional[str] = Field(default=None, description="Reason for refusal.")
    steps: List[TrajectoryStep] = Field(default_factory=list, description="Trajectory steps.")
    latency_ms: float = Field(default=0.0, description="Total run latency in milliseconds.")
    cost_usd: float = Field(default=0.0, description="Estimated total run cost in USD.")
    raw_response: Dict[str, Any] = Field(default_factory=dict, description="Raw agent output dictionary.")


class MetricScore(BaseModel):
    """[DEPRECATED] Individual metric score result.
    Kept for backward compatibility with external consumers; active engine uses dict metrics.
    """
    name: str = Field(description="Metric name.")
    score: float = Field(description="Metric score (0.0 to 1.0 or raw scalar).")
    tier: str = Field(description="Metric tier: deterministic, telemetry, judge.")
    details: Dict[str, Any] = Field(default_factory=dict, description="Metric execution metadata.")


class CaseEvalResult(BaseModel):
    """[DEPRECATED] Complete evaluation result for a single case execution.
    Kept for backward compatibility with external consumers; active engine aggregates dictionary rows.
    """
    case_id: str = Field(description="Case ID.")
    correct: bool = Field(description="Overall pass/fail result.")
    outcome: str = Field(description="Outcome tag: correct_answer, incorrect_answer, correct_refusal, incorrect_refusal.")
    metrics: Dict[str, float] = Field(default_factory=dict, description="Map of metric names to numeric scores.")
    trace: AgentRunTrace = Field(description="Recorded agent run trajectory.")
