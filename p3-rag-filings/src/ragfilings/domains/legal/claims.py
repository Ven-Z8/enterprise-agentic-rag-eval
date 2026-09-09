"""Legal claim semantics for answer verification.

Contract answers must be grounded differently from financial ones: quoted
language must exist verbatim in the cited excerpts, and any money/date claim
must appear there too. Every claim type here is checked against the cited
chunks — a claim the excerpts cannot support fails verification and triggers
the corrective retry.
"""

from __future__ import annotations

import re
from typing import Any

_MONEY_RE = re.compile(r"\$\s?[\d,]+(?:\.\d+)?(?:\s?(?:million|billion|thousand))?")
_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
)
_QUOTE_RE = re.compile(r'"([^"\n]{20,400})"')


def extract_claims(text: str) -> list[dict[str, Any]]:
    """Money, date, and quoted-language claims in an answer."""
    claims: list[dict[str, Any]] = []
    for m in _MONEY_RE.finditer(text):
        claims.append({"raw": m.group().strip(), "kind": "money"})
    for m in _DATE_RE.finditer(text):
        claims.append({"raw": m.group().strip(), "kind": "date"})
    for m in _QUOTE_RE.finditer(text):
        claims.append({"raw": m.group(1).strip(), "kind": "quote"})
    return claims


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _matches(claim: dict[str, Any], chunk_text: str) -> bool:
    if claim["kind"] == "quote":
        return _normalize(claim["raw"]) in _normalize(chunk_text)
    # money / date: exact token presence in at least one excerpt
    return claim["raw"].lower() in chunk_text.lower()


def verify(
    answer_text: str,
    cited_chunks: list[dict[str, Any]],
    math_result: dict[str, Any] | None = None,
    derived_values: list[float] | None = None,
) -> dict[str, Any]:
    """Check every legal claim against the cited excerpts."""
    corpus = "\n".join(c.get("text", "") for c in cited_chunks)
    claims = [{**c, "found": _matches(c, corpus)} for c in extract_claims(answer_text)]
    return {"verified": all(c["found"] for c in claims), "claims": claims}
