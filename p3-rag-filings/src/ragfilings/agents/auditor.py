"""Auditor agent — LLM claim-vs-citation checking with typed output.

Complements the deterministic numeric verifier: the deterministic layer
catches misquoted figures, this layer catches misattributed facts, wrong
years/companies, and narrative claims the chunks don't support.
"""

from __future__ import annotations

from typing import Any

from ..llm import complete_structured
from ..prompts import PromptRegistry
from ..schemas import AuditResult


def audit_answer(
    query: str,
    answer_text: str,
    citations: list[str],
    hits: list[dict[str, Any]],
    cfg: dict[str, Any],
    usage: dict[str, Any],
    math_result: dict[str, Any] | None = None,
) -> AuditResult:
    """Audit a candidate answer against its cited chunks. Adds real usage."""
    by_id = {h["chunk"]["id"]: h["chunk"] for h in hits}
    cited_texts = []
    missing = []
    for cid in citations:
        chunk = by_id.get(cid)
        if chunk is None:
            missing.append(cid)
        else:
            cited_texts.append(f"[{cid}] ({chunk.get('ticker')} FY{chunk.get('fiscal_year')}, "
                               f"Item {chunk.get('item')})\n{chunk['text']}")

    user_parts = [f"Question: {query}", "", f"Candidate answer: {answer_text}"]
    if cited_texts:
        user_parts += ["", "Cited 10-K chunks:"] + cited_texts
    if missing:
        user_parts.append(f"\nThese cited chunk IDs do not exist: {', '.join(missing)}")
    if math_result:
        user_parts.append(
            f"\nVERIFIED_MATH: {math_result.get('expression')} = "
            f"{math_result.get('result_value')} — figures derived from this "
            "computation are acceptable."
        )

    messages = [
        {"role": "system", "content": PromptRegistry.get_auditor()},
        {"role": "user", "content": "\n".join(user_parts)},
    ]
    instance, u = complete_structured(messages, AuditResult, cfg, role="runtime")
    for k in ("input_tokens", "output_tokens", "cost_usd"):
        usage[k] += u.get(k, 0)
    usage["calls"] += u.get("calls", 1)
    return instance
