"""Synthesis agent — grounded, instructor-validated answers."""

from __future__ import annotations

from typing import Any

from ..llm import complete_structured
from ..prompts import PromptRegistry
from ..schemas import SynthesizedAnswer


def synthesize(
    query: str,
    hits: list[dict[str, Any]],
    cfg: dict[str, Any],
    usage: dict[str, Any],
    math_result: dict[str, Any] | None = None,
    feedback: str | None = None,
    system_prompt: str | None = None,
    graph_block: str | None = None,
) -> SynthesizedAnswer:
    """Synthesize a cited answer from hits. Adds real usage into `usage`."""
    context = "\n\n".join(f"[{h['chunk']['id']}]\n{h['chunk']['text']}" for h in hits)
    if math_result:
        context += (
            f"\n\n[PYTHON_MATH_TOOL_VERIFIED_RESULT]\n"
            f"Calculated {math_result.get('explanation', '')}: "
            f"{math_result.get('formatted', '')} (Formula: {math_result.get('expression', '')})"
        )
    if graph_block:
        context += f"\n\n{graph_block}"

    user_content = f"Context chunks:\n\n{context}\n\nQuestion: {query}"
    if feedback:
        user_content += f"\n\nAUDITOR FEEDBACK (fix these issues):\n{feedback}"

    system = system_prompt or PromptRegistry.get_system_synthesis()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    instance, u = complete_structured(messages, SynthesizedAnswer, cfg, role="generation")
    for k in ("input_tokens", "output_tokens", "cost_usd"):
        usage[k] += u.get(k, 0)
    usage["calls"] += u.get("calls", 1)
    return instance
