"""Legal Domain Skill implementation — commercial contracts (CUAD corpus)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, ClassVar

from ...domains.legal.claims import verify as verify_claims
from ...domains.legal.facts import load_defined_terms
from ...domains.legal.rescue import LegalRescue
from ..base import DomainSkill

_DOMAINS_LEGAL_DIR = Path(__file__).resolve().parents[2] / "domains" / "legal"
_CORPUS_DIR = _DOMAINS_LEGAL_DIR / "corpus"


class LegalSkill(DomainSkill):
    """Commercial contracts: modular markdown phases + defined-term rescue and quote verification."""

    name: ClassVar[str] = "legal"
    display_name: ClassVar[str] = "Commercial Contracts"

    def __init__(self, skill_dir: str | Path | None = None) -> None:
        if skill_dir is None:
            skill_dir = Path(__file__).resolve().parent
        super().__init__(skill_dir)

    def needs_decomposition(self, query: str) -> bool:
        return False

    def decompose_query(self, query: str, cfg: dict[str, Any]) -> list[str]:
        return [query]

    def load_rescue(self, cfg: dict[str, Any], index: Any) -> LegalRescue | None:
        manifest_path = _CORPUS_DIR / "manifest.csv"
        if not manifest_path.exists() or index is None:
            return None
        codes: list[str] = []
        titles: dict[str, str] = {}
        with manifest_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                codes.append(row["contract"])
                titles[row["contract"]] = row["title"]
        chunks_by_id = {c["id"]: c for c in index.chunks if c.get("id")}
        terms = load_defined_terms(_CORPUS_DIR / "facts" / "defined_terms.json")
        return LegalRescue(codes, titles, chunks_by_id, terms)

    def compute(
        self, query: str, chunks: list[dict[str, Any]], cfg: dict[str, Any], client: Any = None
    ) -> dict[str, Any] | None:
        return None

    def verify(
        self,
        answer_text: str,
        chunks: list[dict[str, Any]],
        math_result: dict[str, Any] | None = None,
        derived_values: list[float] | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        return verify_claims(
            answer_text, chunks, math_result=math_result, derived_values=derived_values
        )

    @property
    def index_dir(self) -> Path:
        return _CORPUS_DIR / "index"
