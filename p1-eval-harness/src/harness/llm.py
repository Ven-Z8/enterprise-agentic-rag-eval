"""OpenRouter completion client with retried backoff.

Self-contained so the harness core has no dependency on the system under
test. Honors the server's Retry-After header (OpenRouter sends one on 402
in-flight-budget and 429 rate-limit responses); otherwise backs off
exponentially. Token usage and cost are the API-reported numbers.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def parse_usage(u: Any) -> dict[str, Any]:
    """Extract real token usage + cost from an OpenRouter/OpenAI usage object.

    Free-tier providers sometimes omit usage entirely or return it as a plain
    dict; both degrade to zeros instead of crashing the caller.
    """
    if u is None:
        return {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    if isinstance(u, dict):
        return {
            "input_tokens": u.get("prompt_tokens") or 0,
            "output_tokens": u.get("completion_tokens") or 0,
            "cost_usd": float(u.get("cost") or 0.0),
        }
    cost = getattr(u, "cost", None)
    if cost is None and getattr(u, "model_extra", None):
        cost = u.model_extra.get("cost")
    return {
        "input_tokens": getattr(u, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(u, "completion_tokens", 0) or 0,
        "cost_usd": float(cost or 0.0),
    }


class OpenRouterClient:
    """Minimal OpenRouter API client (OpenAI-compatible endpoint)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL)
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self.base_url, api_key=self.api_key, timeout=self.timeout
            )
        return self._client

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int = 1500,
        temperature: float = 0.0,
    ) -> tuple[str, dict[str, Any]]:
        sampling = {} if model == "openai/gpt-5.6-luna" else {"temperature": temperature}
        resp = self._get_client().chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            **sampling,
            extra_body={"usage": {"include": True}},
        )
        if not getattr(resp, "choices", None):
            raise RuntimeError(f"provider returned no choices (model={model})")
        choice = resp.choices[0]
        content = choice.message.content or getattr(choice.message, "reasoning", "") or ""
        return content, parse_usage(resp.usage)


def _retry_after_seconds(exc: Exception) -> float | None:
    """Read the server's Retry-After hint from an API status error."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        return float(headers.get("Retry-After") or headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def complete_with_resilience(
    messages: list[dict[str, str]],
    model: str,
    max_tokens: int = 1500,
    temperature: float = 0.0,
    client: OpenRouterClient | None = None,
) -> tuple[str, dict[str, Any]]:
    """Complete a prompt via OpenRouter with retried backoff.

    Returns (content, usage_dict) where usage_dict carries real
    input_tokens / output_tokens / cost_usd reported by the API.
    """
    active_client = client or OpenRouterClient()
    last_exc: Exception | None = None
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            return active_client.complete(
                messages=messages, model=model,
                max_tokens=max_tokens, temperature=temperature,
            )
        except Exception as e:
            last_exc = e
            retry_after = _retry_after_seconds(e)
            delay = min(retry_after, 180.0) if retry_after else min(2.0 ** attempt, 60.0)
            logger.warning(
                "OpenRouter call attempt %d/%d failed (%s); retrying in %.0fs",
                attempt + 1, max_attempts, e, delay,
            )
            if attempt < max_attempts - 1:
                time.sleep(delay)

    raise last_exc or RuntimeError("OpenRouter LLM completion failed.")
