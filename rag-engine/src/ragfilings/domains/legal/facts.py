"""Legal fact layer — deterministic defined-term extraction.

The legal analog of the financial fact graph: facts extracted ONLY by
deterministic parsing (never an LLM), each with provenance to the chunk it
was parsed from. v1 extracts defined terms — `"Term" means ...` — which the
scope agent surfaces up front for definition questions.
"""

from __future__ import annotations

import re
from typing import Any

# A quoted term immediately followed by a definitional verb.
_DEF_RE = re.compile(
    r'"([^"\n]{2,90}?)"\s+(?:means|shall mean|has the meaning set forth|'
    r"is defined as|shall have the meaning)\b"
)

_DEF_SPAN_CAP = 700


def extract_defined_terms(chunks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{contract_code: {term: {"definition": str, "chunk_id": str}}}.

    The definition span runs from the term to the next sentence end
    (capped); duplicate terms keep the first occurrence per contract.
    """
    facts: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        code = chunk.get("contract", "")
        if not code:
            continue
        terms = facts.setdefault(code, {})
        for m in _DEF_RE.finditer(chunk["text"]):
            term = m.group(1).strip()
            if term in terms or len(term.split()) > 8:
                continue
            start = m.start()
            end = _sentence_end(chunk["text"], m.end())
            definition = chunk["text"][start : min(end, start + _DEF_SPAN_CAP)].strip()
            terms[term] = {"definition": definition, "chunk_id": chunk["id"]}
    return facts


def _sentence_end(text: str, from_idx: int) -> int:
    """End of the sentence containing from_idx (period+space or paragraph)."""
    m = re.search(r"\.\s|\n", text[from_idx:])
    return from_idx + m.end() if m else len(text)


def load_defined_terms(path: str) -> dict[str, dict[str, Any]]:
    import json
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
