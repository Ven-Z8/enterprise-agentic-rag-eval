"""Deterministic Claim Extraction and Numerical Verification.

Every monetary and percentage claim in a synthesized answer must exist
within the cited context chunks to guard against column-slip or hallucination.
"""

from __future__ import annotations

import re
from typing import Any

# Matches "$416,161 million", "$416.2 billion", "46.9%", "$1,234.56",
# "416,161", and bare magnitude claims ("1.64 million", "2 billion") —
# the last form catches hedged figures from world knowledge that carry no
# $ sign and would otherwise escape verification entirely.
_CLAIM_RE = re.compile(
    r"(?:\$\s?[\d,]+(?:\.\d+)?(?:\s?(?:million|billion|thousand|trillion))?"
    r"|[\d,]*\d\.?\d*\s?%"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s?(?:million|billion|thousand|trillion)\b)"
)
_SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
# Financial tables state figures in implicit units ("in millions");
# a claim must match table numbers under relative scalings.
_UNIT_RATIOS = (1.0, 1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9)
_REL_TOL = 5e-3  # 0.5% relative tolerance for rounding differences
_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _to_value(raw: str) -> float:
    match = _NUM_RE.search(raw)
    if not match:
        return 0.0
    num = match.group().replace(",", "")
    value = float(num)
    for word, mult in _SCALE.items():
        if word in raw.lower():
            value *= mult
    return value


def extract_claims(text: str) -> list[dict[str, Any]]:
    """Extract money, percentage, and formatted count figures from text."""
    claims = []
    for m in _CLAIM_RE.finditer(text):
        raw = m.group().strip()
        claims.append({"raw": raw, "value": _to_value(raw), "is_pct": raw.endswith("%")})
    return claims


def _chunk_numbers(chunks: list[dict[str, Any]]) -> list[float]:
    out = []
    for c in chunks:
        text = c.get("text", "")
        for m in _NUM_RE.finditer(text):
            try:
                out.append(float(m.group().replace(",", "")))
            except ValueError:
                pass
    return out


def _matches(claim: dict[str, Any], numbers: list[float]) -> bool:
    ratios = (1.0,) if claim["is_pct"] else _UNIT_RATIOS
    for n in numbers:
        for r in ratios:
            target = claim["value"] / r
            if n and abs(n - target) / max(abs(n), abs(target)) <= _REL_TOL:
                return True
            if n == 0 and target == 0:
                return True
    return False


def _pairwise_derived(numbers: list[float]) -> list[float]:
    """Generate grounded pairwise deltas, sums, and percentage changes between comparable numbers in chunks."""
    derived: list[float] = []
    cands = [n for n in set(numbers) if 0.01 <= abs(n) <= 1e12][:50]
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = cands[i], cands[j]
            ratio = max(abs(a), abs(b)) / max(min(abs(a), abs(b)), 1e-9)
            # Only compare numbers within 20x of each other (prevents comparing revenues to margins)
            if ratio > 20.0:
                continue
            diff = abs(a - b)
            derived.append(diff)
            derived.append(a + b)
            denom = min(abs(a), abs(b))
            if denom > 0:
                derived.append((diff / denom) * 100.0)
            denom_max = max(abs(a), abs(b))
            if denom_max > 0:
                derived.append((diff / denom_max) * 100.0)
    return derived


def verify(
    answer_text: str,
    cited_chunks: list[dict[str, Any]],
    math_result: dict[str, Any] | None = None,
    derived_values: list[float] | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Check every numerical claim against the cited chunks, math results, and query figures.

    `derived_values` are additional grounded figures (e.g. deltas / percent
    changes computed deterministically from fact-graph values) that a correct
    answer may legitimately state even though they do not appear verbatim in
    any cited chunk.
    """
    numbers = _chunk_numbers(cited_chunks)
    if query:
        numbers.extend(_chunk_numbers([{"text": query}]))
    if math_result:
        for k in ("result_value", "raw_value"):
            if k in math_result:
                try:
                    numbers.append(float(math_result[k]))
                except (ValueError, TypeError):
                    pass
    for dv in derived_values or []:
        try:
            numbers.append(float(dv))
        except (ValueError, TypeError):
            pass
    # Grounded pairwise derivations directly from cited chunk figures (e.g. deltas, sums, percent changes)
    numbers.extend(_pairwise_derived(numbers))
    claims = [{**c, "found": _matches(c, numbers)} for c in extract_claims(answer_text)]
    return {"verified": all(c["found"] for c in claims), "claims": claims}

