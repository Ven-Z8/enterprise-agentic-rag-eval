"""Native OpenAI function-calling loop with real usage accounting.

Deliberately framework-free: every request/response is visible, and token +
cost usage is accumulated from the API's own usage object on every call
(including tool-call rounds), so agent cost reporting is never estimated.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ..llm.openrouter import parse_usage


def add_usage(accumulator: dict[str, Any], u) -> None:
    """Add a parsed TokenUsage into a running usage accumulator."""
    accumulator["input_tokens"] += u.input_tokens
    accumulator["output_tokens"] += u.output_tokens
    accumulator["cost_usd"] += u.cost_usd


def run_tool_loop(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    executor: Callable[[str, dict[str, Any]], str],
    usage: dict[str, Any],
    max_steps: int = 6,
    temperature: float = 0.0,
    max_tokens: int = 1500,
) -> tuple[str, list[dict[str, Any]]]:
    """Run a tool-calling loop until the model stops issuing tool calls.

    client: OpenAI-compatible chat client (OpenRouterClient.openai_client).
    executor: maps (tool_name, args) -> string result; exceptions are
      converted into TOOL ERROR results so the model can react, not crash.
    usage: accumulator dict with input_tokens/output_tokens/cost_usd/calls.

    Returns (final assistant text, tool events).
    """
    msgs: list[dict[str, Any]] = list(messages)
    events: list[dict[str, Any]] = []
    final_text = ""

    for step in range(max_steps):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "extra_body": {"usage": {"include": True}},
        }
        if tools:
            kwargs["tools"] = tools

        resp = client.chat.completions.create(**kwargs)
        add_usage(usage, parse_usage(getattr(resp, "usage", None)))
        usage["calls"] = usage.get("calls", 0) + 1

        msg = resp.choices[0].message
        if msg.content:
            final_text = msg.content

        if not msg.tool_calls:
            break

        msgs.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = executor(tc.function.name, args)
            except Exception as e:  # noqa: BLE001 — surfaced to the model, not raised
                result = f"TOOL ERROR: {type(e).__name__}: {e}"
            events.append(
                {
                    "step": step,
                    "tool": tc.function.name,
                    "args": args,
                    "result_preview": str(result)[:300],
                }
            )
            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                }
            )

    return final_text, events
