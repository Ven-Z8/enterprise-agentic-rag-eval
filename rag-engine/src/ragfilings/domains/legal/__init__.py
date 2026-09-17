"""Legal domain pack — commercial contracts (CUAD corpus, CC-BY-4.0).

Corpus: 102 commercial agreements from the CUAD test split (The Atticus
Project), indexed with the same retrieval engine as the financial pack.
Fact layer: deterministic defined-term extraction. Claim semantics: quoted
language must exist verbatim in the cited excerpts, plus money/date claims.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, ClassVar

from .. import DomainPack
from .claims import verify as verify_claims
from .facts import load_defined_terms
from .rescue import LegalRescue

_CORPUS_DIR = Path(__file__).resolve().parent / "corpus"


class LegalPack(DomainPack):
    """Commercial contracts: modular markdown phases + defined-term rescue and quote verification."""

    name: ClassVar[str] = "legal"
    display_name: ClassVar[str] = "Commercial Contracts"

    def __init__(self, pack_dir: str | Path | None = None) -> None:
        if pack_dir is None:
            pack_dir = Path(__file__).resolve().parent
        super().__init__(pack_dir)

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


LegalSkill = LegalPack
PACK = LegalPack()

__all__ = ["PACK", "LegalPack", "LegalSkill"]
