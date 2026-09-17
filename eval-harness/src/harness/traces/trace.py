"""Trace format (v0). A full agent run captured as structured, replayable JSON.

Every adapter's job is to produce one Trace per TestCase. The metric layer scores
Traces, never raw agent output — so anything a metric might need (tool calls,
retries, citations, cost, latency) has to live here.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

STEP_KINDS = ("reasoning", "tool_call", "response")


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: Any  # tool output, or None if it errored
    error: str | None = None
    latency_ms: float | None = None


@dataclass
class Step:
    index: int
    kind: str  # one of STEP_KINDS
    content: str | None = None  # reasoning text or final response text
    tool_call: ToolCall | None = None
    retry_of: int | None = None  # index of the step this one retries, if any


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class Trace:
    case_id: str  # TestCase.id this run answers
    input: str
    final_output: str
    steps: list[Step] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)  # citations the AGENT produced
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)  # agent version, adapter, run id...

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_dict(cls, d: dict) -> Trace:
        return cls(
            case_id=d["case_id"],
            input=d["input"],
            final_output=d["final_output"],
            steps=[
                Step(
                    index=s["index"],
                    kind=s["kind"],
                    content=s.get("content"),
                    tool_call=ToolCall(**s["tool_call"]) if s.get("tool_call") else None,
                    retry_of=s.get("retry_of"),
                )
                for s in d.get("steps", [])
            ],
            citations=d.get("citations", []),
            usage=Usage(**d.get("usage", {})),
            latency_ms=d.get("latency_ms", 0.0),
            model=d.get("model", ""),
            metadata=d.get("metadata", {}),
        )
