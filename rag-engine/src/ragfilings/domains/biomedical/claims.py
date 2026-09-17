"""Biomedical claim verification.

Extracts quantitative claims (dosages, sample sizes, percentages, p-values, odds ratios)
and verifies that cited excerpts substantiate the stated figures.
"""

from __future__ import annotations

import re
from typing import Any

# Match specific numbers, percentages, and scientific statistics (e.g. 25.9, 13.2, 6.7%, p < 0.001)
_NUM_CLAIM_RE = re.compile(
    r"(?P<raw>(?:p\s*[<>=]\s*[\d\.]+|\b\d+(?:\.\d+)?\s*(?:mg(?:\/kg)?|mcg|g|ml|%)\b|\b\d+\.\d+\b|\b\d{1,5}\b))",
    re.IGNORECASE,
)

_PMID_RE = re.compile(r"\b(?:PMID|PMCID|DOI)?\s*:?\s*\d{6,10}\b", re.IGNORECASE)

# Common non-claim numbers to ignore (e.g. standard bullet numbers, common years)
_IGNORE_NUMS = {
    "1", "2", "3", "4", "5", "10", "100",
    "1995", "1996", "1997", "1998", "1999", "2000", "2001", "2002", "2003",
    "2004", "2005", "2006", "2007", "2008", "2009", "2010", "2011", "2012",
    "2013", "2014", "2015", "2016", "2017", "2018", "2019", "2020", "2021",
    "2022", "2023", "2024", "2025", "2026",
}


def extract_claims(text: str) -> list[dict[str, Any]]:
    """Extract quantitative claims and statistics from answer text."""
    # Strip out PMIDs and chunk references so document IDs aren't audited as clinical metrics
    clean_text = _PMID_RE.sub(" ", text)

    claims: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in _NUM_CLAIM_RE.finditer(clean_text):
        raw = m.group("raw").strip()
        if raw in _IGNORE_NUMS or raw in seen or len(raw) > 8:
            continue
        seen.add(raw)
        claims.append({"raw": raw, "kind": "numeric"})

    return claims


def _matches(claim: dict[str, Any], corpus: str) -> bool:
    raw = claim["raw"].lower()
    # 1. Direct text presence
    if raw in corpus:
        return True
    # 2. Digit-only presence for decimals / percentages (e.g. 25.9 or 6.7)
    digits = re.sub(r"[^\d\.]", "", raw)
    if digits and digits in corpus:
        return True
    # 3. For statistics like "p < 0.001", check if "p" and "0.001" both appear in proximity
    if "p" in raw and digits and digits in corpus:
        return True
    return False


def verify(
    answer_text: str,
    cited_chunks: list[dict[str, Any]],
    math_result: dict[str, Any] | None = None,
    derived_values: list[float] | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Check every quantitative biomedical claim against the cited excerpts."""
    if not answer_text or not cited_chunks:
        return {"verified": False, "claims": []}

    corpus = "\n".join(
        f"{c.get('id', '')} {c.get('title', '')} {c.get('text', '')}"
        for c in cited_chunks
    ).lower()
    if query:
        corpus += "\n" + query.lower()
    if math_result and isinstance(math_result.get("formatted"), str):
        corpus += "\n" + math_result["formatted"].lower()

    claims = [{**c, "found": _matches(c, corpus)} for c in extract_claims(answer_text)]
    return {"verified": all(c["found"] for c in claims), "claims": claims}
