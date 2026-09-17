"""Conversational follow-up handling.

Turns an elliptical follow-up ("what about FY2024?", "the CAGR between those
two years?") into a self-contained question by resolving it against the recent
conversation history. The downstream pipeline (graph augmentation,
clarification, synthesis) then operates on the self-contained question exactly
as it would a first-turn query, so multi-hop grounding still applies.
"""

from __future__ import annotations

from typing import Any

from ..domains import DomainPack, get_pack
from ..llm import complete_with_resilience

# How many prior turns to feed the rewriter (kept small for a tight prompt).
_HISTORY_TURNS = 6
# Per-turn content cap so one long answer can't blow up the rewrite prompt.
_TURN_CHAR_CAP = 400


def _transcript(history: list[dict[str, Any]]) -> str:
    lines = []
    for turn in history[-_HISTORY_TURNS:]:
        role = "User" if turn.get("role") == "user" else "Assistant"
        content = str(turn.get("content", ""))[:_TURN_CHAR_CAP]
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def rewrite_followup(
    query: str, history: list[dict[str, Any]], cfg: dict[str, Any], pack: DomainPack | None = None
) -> str:
    """Return a self-contained version of ``query`` given ``history``.

    Falls back to the original query whenever there is no history to resolve
    against or the rewrite call fails — the pipeline still works single-turn.
    """
    pack = pack or get_pack("financial")
    query = query.strip()
    if not history or not query:
        return query

    system_prompt = (
        pack.get_phase_instructions("converse")
        if hasattr(pack, "get_phase_instructions")
        else pack.prompt("converse_rewrite")
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Conversation so far:\n{_transcript(history)}\n\n"
                f"Follow-up question: {query}\n\n"
                f"Rewritten self-contained question:"
            ),
        },
    ]
    try:
        from ..llm import complete_structured
        from ..schemas import RewrittenQuery

        resp, _ = complete_structured(messages, RewrittenQuery, cfg, role="converse")
        rewritten = resp.rewritten_query.strip().strip('"').strip()
        if len(rewritten) >= 8:
            return rewritten
    except Exception:
        pass

    try:
        text, _ = complete_with_resilience(messages, cfg, role="converse")
        rewritten = text.strip().strip('"').strip()
        # If output contains preamble/fences, extract the first genuine question line
        for line in rewritten.splitlines():
            line = line.strip().strip('"').strip()
            if line and not any(p in line.lower() for p in ("here is", "rewritten", "self-contained", "sure")):
                rewritten = line
                break
        if len(rewritten) >= 8:
            return rewritten
    except Exception:
        pass
    return query
