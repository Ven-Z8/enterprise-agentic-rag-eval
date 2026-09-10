"""Legal pack implementation — commercial contracts (CUAD corpus)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, ClassVar

from .. import DomainPack
from .claims import verify as verify_claims
from .facts import load_defined_terms
from .rescue import LegalRescue

_PACK_ROOT = Path(__file__).resolve().parent
_SKILLS_PHASES_DIR = _PACK_ROOT.parent.parent / "skills" / "legal" / "phases"
_CORPUS_DIR = _PACK_ROOT / "corpus"

_prompt_cache: dict[str, str] = {}


class LegalPack(DomainPack):
    """Commercial contracts: clause extraction + quoted-language semantics."""

    name: ClassVar[str] = "legal"
    display_name: ClassVar[str] = "Commercial Contracts"

    # ------------------------------------------------------------- prompts

    def prompt(self, name: str) -> str:
        if name not in _prompt_cache:
            candidates = [
                _SKILLS_PHASES_DIR / f"{name}.md",
                _SKILLS_PHASES_DIR / f"{name}.prompt",
                _SKILLS_PHASES_DIR / f"{name}.txt",
            ]
            for path in candidates:
                if path.exists():
                    _prompt_cache[name] = path.read_text(encoding="utf-8").strip()
                    break
            else:
                raise FileNotFoundError(f"Legal prompt '{name}' not found. Searched {candidates}")
        return _prompt_cache[name]

    def format_prompt(self, name: str, **kwargs: Any) -> str:
        if name == "verification_retry" and isinstance(kwargs.get("failed_claims"), list):
            kwargs["failed_claims"] = ", ".join(kwargs["failed_claims"])
        return self.prompt(name).format(**kwargs)

    # ------------------------------------------- retrieval-time query shape

    def needs_decomposition(self, query: str) -> bool:
        return False  # contract questions are single-hop clause lookups in v1

    def decompose_query(self, query: str, cfg: dict[str, Any]) -> list[str]:
        return [query]

    # --------------------------------- deterministic fact layer + scope agent

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

    # --------------------------------------------------- synthesis-time tools

    def compute(
        self, query: str, chunks: list[dict[str, Any]], cfg: dict[str, Any], client: Any = None
    ) -> dict[str, Any] | None:
        return None  # no derivation tool in the legal pack v1

    # ------------------------------------------------------- claim semantics

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

    # -------------------------------------------------------------- corpus

    @property
    def index_dir(self) -> Path:
        """The legal pack owns its retrieval index (CUAD corpus)."""
        return _CORPUS_DIR / "index"


__all__ = ["LegalPack"]
