"""OpenRouter Provider Client."""

from __future__ import annotations

import os
from typing import Any

from .base import BaseLLMClient
from .types import ChatMessage, LLMResponse, TokenUsage


def parse_usage(u: Any) -> TokenUsage:
    """Extract real token usage + cost from an OpenRouter/OpenAI usage object.

    Free-tier providers sometimes omit usage entirely or return it as a plain
    dict; both degrade to zeros instead of crashing the caller.
    """
    if u is None:
        return TokenUsage()
    if isinstance(u, dict):
        return TokenUsage(
            input_tokens=u.get("prompt_tokens") or 0,
            output_tokens=u.get("completion_tokens") or 0,
            cost_usd=float(u.get("cost") or 0.0),
        )
    cost = getattr(u, "cost", None)
    if cost is None and getattr(u, "model_extra", None):
        cost = u.model_extra.get("cost")
    return TokenUsage(
        input_tokens=getattr(u, "prompt_tokens", 0) or 0,
        output_tokens=getattr(u, "completion_tokens", 0) or 0,
        cost_usd=float(cost or 0.0),
    )


class OpenRouterClient(BaseLLMClient):
    """OpenRouter API client with dynamic usage cost parsing."""

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float = 60.0,
    ):
        key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        url = base_url or os.environ.get("OPENROUTER_BASE_URL", self.DEFAULT_BASE_URL)
        model = default_model or self.DEFAULT_MODEL
        super().__init__(api_key=key, base_url=url, default_model=model)
        self.timeout = timeout
        self._client = None

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("sk-or-"))

    @property
    def openai_client(self):
        """The underlying OpenAI-compatible client (for instructor / tool calls)."""
        return self._get_client()

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.base_url, api_key=self.api_key, timeout=self.timeout
            )
        return self._client

    def complete(
        self,
        messages: list[ChatMessage | dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()
        target_model = model or self.default_model
        raw_msgs = self.normalize_messages(messages)

        request_kwargs: dict[str, Any] = {
            "model": target_model,
            "messages": raw_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "extra_body": {"usage": {"include": True}},
        }
        # Luna does not advertise temperature support in the OpenRouter catalog.
        if target_model == "openai/gpt-5.6-luna":
            request_kwargs.pop("temperature", None)
        request_kwargs.update(kwargs)

        resp = client.chat.completions.create(**request_kwargs)
        if not getattr(resp, "choices", None):
            raise RuntimeError(f"provider returned no choices (model={target_model})")
        choice = resp.choices[0]
        content = choice.message.content or getattr(choice.message, "reasoning", "") or ""

        return LLMResponse(
            content=content, usage=parse_usage(resp.usage), model=target_model, raw_response=resp
        )
