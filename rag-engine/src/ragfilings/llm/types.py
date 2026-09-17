"""Domain Types for LLM Client Subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RoleType = Literal["system", "user", "assistant", "tool"]


@dataclass
class ChatMessage:
    role: RoleType | str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": str(self.role), "content": self.content}

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> ChatMessage:
        return cls(role=d["role"], content=d["content"])


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, float | int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
        }


@dataclass
class LLMResponse:
    content: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    raw_response: Any = None

    @property
    def cost_usd(self) -> float:
        return self.usage.cost_usd
