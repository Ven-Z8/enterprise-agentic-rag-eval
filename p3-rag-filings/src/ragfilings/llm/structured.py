"""Structured completions — instructor-validated pydantic outputs.

The only place LLM outputs are parsed: instructor retries schema validation
and raises on failure instead of silently accepting malformed JSON.
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from .factory import get_llm_client, get_model_for_role
from .openrouter import OpenRouterClient, parse_usage

logger = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


def complete_structured(
    messages: list[dict[str, str]],
    response_model: type[M],
    cfg: dict[str, Any],
    role: str = "generation",
    client: OpenRouterClient | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
    max_retries: int = 2,
) -> tuple[M, dict[str, Any]]:
    """Complete `messages` and return (validated_model, usage_dict).

    usage_dict is the real API-reported usage accumulated across
    instructor retries, so cost accounting never undercounts.
    """
    import instructor

    from .. import config as cfg_mod
    cfg_mod._load_env()

    active = client or get_llm_client(cfg=cfg, role=role)
    if not isinstance(active, OpenRouterClient):
        raise TypeError("complete_structured requires an OpenRouterClient")

    patched = instructor.from_openai(active.openai_client)
    model_slug = get_model_for_role(cfg, role) or active.default_model
    tokens = max_tokens or cfg.get("generation", {}).get("max_tokens", 1200)

    usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}

    extra_body = {"usage": {"include": True}}
    # Alibaba rejects forced tool_choice while Qwen thinking mode is enabled.
    if model_slug == "qwen/qwen3.8-flash":
        extra_body["reasoning"] = {"enabled": False}
    sampling = {} if model_slug == "openai/gpt-5.6-luna" else {"temperature": temperature}
    instance, raw = patched.chat.completions.create_with_completion(
        model=model_slug,
        messages=messages,
        response_model=response_model,
        max_tokens=tokens,
        **sampling,
        max_retries=max_retries,
        extra_body=extra_body,
    )
    u = parse_usage(getattr(raw, "usage", None))
    usage["input_tokens"] += u.input_tokens
    usage["output_tokens"] += u.output_tokens
    usage["cost_usd"] += u.cost_usd
    usage["calls"] += 1

    return instance, usage
