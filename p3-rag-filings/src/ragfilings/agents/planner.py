"""Planner agent — structured query planning via instructor.

Resolves company/year scope against the actual corpus inventory (never a
hardcoded dictionary) and produces typed retrieval sub-questions.
"""

from __future__ import annotations

from typing import Any

from ..llm import complete_structured
from ..prompts import PromptRegistry
from ..schemas import QueryPlan


def corpus_inventory(chunks: list[dict[str, Any]]) -> list[str]:
    """Distinct filings in the index, as 'TICKER FY<year>' lines."""
    seen: dict[str, set[str]] = {}
    for c in chunks:
        ticker = str(c.get("ticker") or "")
        year = str(c.get("fiscal_year") or "")
        if ticker:
            seen.setdefault(ticker, set()).add(year)
    return [
        f"{t} FY{', FY'.join(sorted(y for y in ys if y))}"
        for t, ys in sorted(seen.items())
    ]


def plan_query(
    query: str,
    cfg: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> tuple[QueryPlan, dict[str, Any]]:
    """Plan retrieval for `query`. Returns (plan, usage_dict)."""
    inventory = corpus_inventory(chunks)
    system = PromptRegistry.format("planner", inventory="\n".join(inventory))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]
    plan, usage = complete_structured(messages, QueryPlan, cfg, role="planning")

    known_tickers = {line.split()[0] for line in inventory}
    known_years: set[int] = set()
    for c in chunks:
        try:
            known_years.add(int(c["fiscal_year"]))
        except (KeyError, TypeError, ValueError):
            pass

    if plan.ticker and plan.ticker.upper() in known_tickers:
        plan.ticker = plan.ticker.upper()
    elif plan.ticker:
        plan.ticker = None
    if plan.fiscal_year and int(plan.fiscal_year) not in known_years:
        plan.fiscal_year = None
    if not plan.sub_questions:
        plan.sub_questions = [query]

    return plan, usage
