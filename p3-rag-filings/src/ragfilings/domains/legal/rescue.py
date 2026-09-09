"""Deterministic scope agent for the legal pack.

Mirror of the financial GraphRescue for contracts:

- ``clarification``: a clause/definition question that names no contract in a
  multi-agreement corpus is under-specified — the engine asks which agreement
  instead of guessing.
- ``rescue``: a definition question whose term is defined in exactly one
  named contract gets the definition and its provenance chunk injected up
  front, so retrieval is not a single point of failure.

Conservative by design: rescue only ever injects facts that were extracted
deterministically from the contract text, and it abstains whenever scope is
uncertain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# A contract code is an uppercase token (digits/hyphen allowed), matched
# case-sensitively so lowercase ordinary words can never collide.
_CODE_RE_SRC = r"[A-Z][A-Z0-9]*(?:-[0-9]+)?"

_TERM_RE = re.compile(r"['\"]([^'\"\n]{2,90}?)['\"]")
_DEFINITION_INTENT_RE = re.compile(
    r"\bdefin(?:ed|ition)\b|\bmeans?\b|\bwhat is meant by\b", re.IGNORECASE
)


@dataclass
class LegalRescueOutcome:
    queries: list[dict[str, str]]
    facts: list[dict[str, Any]]
    chunk_ids: list[str]
    chunks: list[dict[str, Any]]
    facts_block: str
    derived_values: list[float] = field(default_factory=list)


class LegalRescue:
    """Deterministic rescue/clarification over the contract corpus."""

    def __init__(
        self,
        contract_codes: list[str],
        contract_titles: dict[str, str],
        chunks_by_id: dict[str, dict[str, Any]],
        defined_terms: dict[str, dict[str, Any]],
    ) -> None:
        self.contract_codes = contract_codes
        self.contract_titles = contract_titles
        self.chunks_by_id = chunks_by_id
        self.defined_terms = defined_terms
        self._code_re = re.compile(
            rf"\b({'|'.join(re.escape(c) for c in sorted(contract_codes, key=len, reverse=True))})\b"
            if contract_codes
            else r"(?!x)x"
        )

    # ------------------------------------------------------------ extraction

    def find_contracts(self, query: str) -> list[str]:
        return [c for c in dict.fromkeys(self._code_re.findall(query))]

    # --------------------------------------------------------- clarification

    def clarification(self, query: str) -> str | None:
        """Ask which agreement, when a clause/definition question names none."""
        if self.find_contracts(query):
            return None  # scope already pinned to at least one contract
        if not (
            _DEFINITION_INTENT_RE.search(query)
            or re.search(
                r"\bclause\b|\bprovision\b|\bterm\b|\bagreement\b|"
                r"\bcontract\b",
                query,
                re.IGNORECASE,
            )
        ):
            return None
        n = len(self.contract_codes)
        return (
            f"The corpus holds {n} separate agreements, and the question "
            f"does not say which one. Which contract should I look at "
            f"(e.g. by its document code)?"
        )

    # ---------------------------------------------------------------- rescue

    def rescue(self, query: str) -> LegalRescueOutcome | None:
        """Definition lookup: quoted term + one named contract that defines it."""
        contracts = self.find_contracts(query)
        if len(contracts) != 1:
            return None
        code = contracts[0]
        terms = self.defined_terms.get(code, {})
        if not terms:
            return None
        for m in _TERM_RE.finditer(query):
            term = m.group(1).strip()
            hit = terms.get(term) or next(
                (v for k, v in terms.items() if k.lower() == term.lower()), None
            )
            if hit is None:
                continue
            chunk = self.chunks_by_id.get(hit["chunk_id"])
            if chunk is None:
                return None
            title = self.contract_titles.get(code, code)
            block = (
                "[CONTRACT_FACTS — deterministic extractions from the contract]\n"
                "Each line carries the source chunk ID it was parsed from. If you "
                "use one of these, cite that source chunk ID, not this block.\n"
                f'- {code} defined term "{term}": {hit["definition"]} '
                f"(source chunk: {hit['chunk_id']}; agreement: {title})"
            )
            return LegalRescueOutcome(
                queries=[{"contract": code, "term": term}],
                facts=[{"contract": code, "term": term, **hit}],
                chunk_ids=[hit["chunk_id"]],
                chunks=[chunk],
                facts_block=block,
            )
        return None
