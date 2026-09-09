"""Abstract Base Class for LLM Provider Clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import ChatMessage, LLMResponse


class BaseLLMClient(ABC):
    """Abstract interface for all LLM provider adapters."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self._default_model = default_model

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (currently only 'openrouter')."""
        pass

    @property
    def default_model(self) -> str:
        return self._default_model or "default-model"

    @abstractmethod
    def complete(
        self,
        messages: list[ChatMessage | dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute a synchronous chat completion call."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if required credentials / endpoint are present and valid."""
        pass

    @staticmethod
    def normalize_messages(messages: list[ChatMessage | dict[str, str]]) -> list[dict[str, str]]:
        """Normalize ChatMessage objects or dicts into OpenAI-style dicts."""
        out = []
        for m in messages:
            if isinstance(m, ChatMessage):
                out.append(m.to_dict())
            elif isinstance(m, dict) and "role" in m and "content" in m:
                out.append({"role": str(m["role"]), "content": str(m["content"])})
            else:
                raise ValueError(f"Invalid message format: {m!r}")
        return out
