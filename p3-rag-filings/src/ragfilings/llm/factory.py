"""LLM Client Factory and Completion Dispatcher (OpenRouter).

Models are resolved per role from config.toml:
  generation  — grounded synthesis
  planning    — plans, decomposition, conversational rewrites
  runtime     — researcher, math extraction, auditor
  extraction  — graph/community extraction
  judge       — evaluation (canonical harness setting is in P1)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .base import BaseLLMClient
from .openrouter import OpenRouterClient
from .types import ChatMessage

logger = logging.getLogger(__name__)

_ROLES = ("generation", "extraction", "planning", "runtime", "judge")


def get_model_for_role(cfg: dict[str, Any] | None, role: str = "generation") -> str | None:
    """Resolve the configured model slug for a role (falls back to generation)."""
    if not cfg:
        return None
    section = cfg.get(role) if role in _ROLES else None
    model = (section or {}).get("model") if section else None
    if model is None and role == "judge":
        model = cfg.get("eval", {}).get("judge_model")
    if model is None and role in ("planning", "runtime"):
        model = cfg.get("extraction", {}).get("model")
    if model is None and role != "generation":
        model = cfg.get("generation", {}).get("model")
    return model


class LLMFactory:
    """Factory for creating OpenRouter LLM clients."""

    @classmethod
    def create_client(
        cls,
        cfg: dict[str, Any] | None = None,
        role: str = "generation",
        default_model: str | None = None,
    ) -> BaseLLMClient:
        """Create an OpenRouter client bound to the model for `role`."""
        from .. import config as cfg_mod
        cfg_mod._load_env()

        model = default_model or get_model_for_role(cfg, role)
        return OpenRouterClient(default_model=model)


def get_llm_client(
    provider_name: str | None = None,
    cfg: dict[str, Any] | None = None,
    default_model: str | None = None,
    role: str = "generation",
) -> BaseLLMClient:
    """Convenience functional factory. provider_name is accepted for
    backwards compatibility and ignored — OpenRouter routes all providers."""
    return LLMFactory.create_client(cfg=cfg, role=role, default_model=default_model)


def is_transient_error(exc: Exception) -> bool:
    """Classify if an error is a transient failure (eligible for retry).

    Transient:
      - 408, 429 (rate limits)
      - 500, 502, 503, 504 (server errors)
      - Network connection or timeout errors
    Permanent (fail-fast, do not retry):
      - 400 (Bad Request / invalid parameters / context limit)
      - 401 (Unauthorized / invalid API key)
      - 402 (Payment Required / out of credits)
      - 403 (Forbidden)
      - 404 (Not Found / invalid model slug)
      - 422 (Unprocessable Entity)
      - ValueError, TypeError, KeyError
    """
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

    if status_code is not None:
        if status_code in (400, 401, 402, 403, 404, 422):
            return False
        if status_code in (408, 429, 500, 502, 503, 504):
            return True

    exc_type = type(exc).__name__
    if any(perm in exc_type for perm in ("BadRequest", "Authentication", "PermissionDenied", "NotFoundError", "ValueError", "TypeError")):
        return False
    if any(trans in exc_type for trans in ("RateLimit", "Timeout", "Connection", "InternalServer", "APIConnectionError")):
        return True

    msg = str(exc).lower()
    if "credit" in msg or "payment" in msg or "unauthorized" in msg or "invalid_api_key" in msg:
        return False
    if "rate limit" in msg or "too many requests" in msg or "timeout" in msg or "connection" in msg:
        return True

    return False


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
    messages: list[ChatMessage | dict[str, str]],
    cfg: dict[str, Any],
    model: str | None = None,
    client: BaseLLMClient | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
    role: str = "generation",
) -> tuple[str, dict[str, Any]]:
    """Complete a prompt via OpenRouter with retried backoff.

    Honors the server's Retry-After header (OpenRouter sends one on 402
    in-flight-budget and 429 rate-limit responses); otherwise backs off
    exponentially. Fails fast on non-transient errors (400, 401, 402).
    Returns (content, usage_dict) where usage_dict carries real
    input_tokens / output_tokens / cost_usd reported by the API.
    """
    from .. import config as cfg_mod
    cfg_mod._load_env()

    tokens = max_tokens or cfg.get("generation", {}).get("max_tokens", 1200)
    target_model = model or get_model_for_role(cfg, role)

    active_client = client or get_llm_client(cfg=cfg, default_model=target_model)

    last_exc: Exception | None = None
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            resp = active_client.complete(
                messages=messages,
                model=target_model,
                max_tokens=tokens,
                temperature=temperature,
            )
            return resp.content, resp.usage.to_dict()
        except Exception as e:
            last_exc = e
            # Permanent errors fail fast immediately
            if not is_transient_error(e):
                logger.error("Permanent OpenRouter call failure (%s): %s", type(e).__name__, e)
                raise e

            retry_after = _retry_after_seconds(e)
            delay = min(retry_after, 180.0) if retry_after else min(2.0 ** attempt, 60.0)
            logger.warning(
                "OpenRouter call attempt %d/%d transient failure (%s); retrying in %.0fs",
                attempt + 1, max_attempts, e, delay,
            )
            if attempt < max_attempts - 1:
                time.sleep(delay)

    raise last_exc or RuntimeError("OpenRouter LLM completion failed.")
