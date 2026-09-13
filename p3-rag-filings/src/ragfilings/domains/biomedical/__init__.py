"""Biomedical domain pack — Clinical literature (PubMed / PubMedQA) and Chemical Entities (PubChem).

Corpus: Peer-reviewed biomedical publications and abstracts from PubMedQA.
Tool: Live NCBI PubChem PUG-REST API for dynamic chemical entity resolution.
Claim semantics: Quantitative clinical assertions, p-values, dosages, and categorical decisions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from .. import DomainPack
from .claims import verify as verify_claims
from .tools import compute_biomedical

_CORPUS_DIR = Path(__file__).resolve().parent / "corpus"


class BiomedicalPack(DomainPack):
    """Biomedical literature and biochemical reasoning domain pack."""

    name: ClassVar[str] = "biomedical"
    display_name: ClassVar[str] = "Biomedical & Life Sciences (PubMed + PubChem)"

    def __init__(self, pack_dir: str | Path | None = None) -> None:
        if pack_dir is None:
            pack_dir = Path(__file__).resolve().parent
        super().__init__(pack_dir)

    def needs_decomposition(self, query: str) -> bool:
        q = query.lower()
        return " compare " in q or " versus " in q or " vs " in q or (" and " in q and "effect" in q)

    def decompose_query(self, query: str, cfg: dict[str, Any]) -> list[str]:
        # Simple, non-hardcoded decomposition: split comparative clauses if present
        q = query.strip()
        low = q.lower()
        for sep in (" versus ", " vs. ", " vs "):
            if sep in low:
                idx = low.find(sep)
                part1 = q[:idx].strip()
                part2 = q[idx + len(sep) :].strip()
                return [q, part1, part2]
        return [q]

    def load_rescue(self, cfg: dict[str, Any], index: Any) -> Any | None:
        return None

    def compute(
        self, query: str, chunks: list[dict[str, Any]], cfg: dict[str, Any], client: Any = None
    ) -> dict[str, Any] | None:
        return compute_biomedical(query, chunks, cfg, client=client)

    def verify(
        self,
        answer_text: str,
        chunks: list[dict[str, Any]],
        math_result: dict[str, Any] | None = None,
        derived_values: list[float] | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        return verify_claims(
            answer_text,
            chunks,
            math_result=math_result,
            derived_values=derived_values,
            query=query,
        )

    @property
    def index_dir(self) -> Path:
        return _CORPUS_DIR / "index"


BiomedicalSkill = BiomedicalPack
PACK = BiomedicalPack()

__all__ = ["PACK", "BiomedicalPack", "BiomedicalSkill"]
