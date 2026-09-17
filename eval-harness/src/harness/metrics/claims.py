"""Deterministic numeric-claim extraction for answer scoring.

Extracts money, percentage, and formatted-count figures from text so expected
and actual answers can be compared under tolerance and unit re-expression.
"""

from __future__ import annotations

import re
from typing import Any

# Matches "$416,161 million", "$416.2 billion", "46.9%", "$1,234.56",
# "416,161", and bare magnitude claims ("1.64 million", "2 billion") so
# count answers ("1.64 million vehicles" vs "1,640,000") compare as numbers.
_CLAIM_RE = re.compile(
    r"(?:\$\s?[\d,]+(?:\.\d+)?(?:\s?(?:million|billion|thousand|trillion))?"
    r"|[\d,]*\d\.?\d*\s?%"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s?(?:million|billion|thousand|trillion)\b)"
)
_SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
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
