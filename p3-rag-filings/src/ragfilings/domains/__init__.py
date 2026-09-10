"""Domain skill packs.

The engine in `ragfilings.pipeline` is domain-agnostic: retrieval, the
grounded synthesis loop, confidence gating, corrective retries, and refusal
routing are the same for every domain. Everything domain-specific is supplied
by a pack — the prompts, the deterministic fact layer and scope agents
(rescue / clarification), the claim semantics for verification, and the
derivation tools (financial math, clause extraction, ...).

A pack is a module under `ragfilings/domains/<name>/` exporting a `PACK`
object that satisfies :class:`DomainPack`. Register it here (or rely on
directory discovery via :func:`get_pack`).

Current packs:
- ``financial`` — SEC 10-K filings (fact graph, metric vocabulary, monetary
  claim verification, financial-math tool). Measured: v1 97.5%, enterprise
  95.6% (all-free, accuracy-only).
- ``legal`` — commercial contracts (CUAD corpus, CC-BY-4.0): defined-term
  fact layer, clause extraction prompts, quoted-language claim semantics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import import_module
from typing import Any, ClassVar

__all__ = ["DomainPack", "get_pack", "available_packs"]

# Packs that ship in this checkout. Add the module under
# `ragfilings/domains/<name>/` exporting PACK, then register the name here.
_KNOWN_PACKS = ("financial", "legal")


class DomainPack(ABC):
    """The contract between the domain-agnostic engine and one domain."""

    name: ClassVar[str]
    display_name: ClassVar[str]

    # ------------------------------------------------------------- prompts

    @abstractmethod
    def prompt(self, name: str) -> str:
        """Raw prompt template by name (e.g. 'synthesis')."""

    @abstractmethod
    def format_prompt(self, name: str, **kwargs: Any) -> str:
        """Prompt template formatted with kwargs."""

    # ------------------------------------------- retrieval-time query shape

    @abstractmethod
    def needs_decomposition(self, query: str) -> bool:
        """True when the query should be split into retrieval sub-queries."""

    @abstractmethod
    def decompose_query(self, query: str, cfg: dict[str, Any]) -> list[str]:
        """Sub-queries for retrieval (always includes the original query)."""

    # --------------------------------- deterministic fact layer + scope agent

    @abstractmethod
    def load_rescue(self, cfg: dict[str, Any], index: Any) -> Any | None:
        """The pack's deterministic scope agent, or None when unavailable.

        The returned object must expose:
        - ``clarification(query) -> str | None`` — a deterministic clarifying
          question when the query is under-specified for this domain;
        - ``rescue(query) -> outcome | None`` — grounded facts for a
          clean-scope query (``facts_block``, ``chunks``, ``derived_values``).
        """

    # --------------------------------------------------- synthesis-time tools

    @abstractmethod
    def compute(
        self, query: str, chunks: list[dict[str, Any]], cfg: dict[str, Any], client: Any = None
    ) -> dict[str, Any] | None:
        """Pack derivation tool (financial math, clause arithmetic, ...).

        Returns ``{"explanation", "formatted", "expression", "result_value",
        "usage"}`` or None when the query does not ask for a derivation.
        """

    # ------------------------------------------------------- claim semantics

    @abstractmethod
    def verify(
        self,
        answer_text: str,
        chunks: list[dict[str, Any]],
        math_result: dict[str, Any] | None = None,
        derived_values: list[float] | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Check every domain claim in the answer against the cited chunks.

        Returns ``{"verified": bool, "claims": [...]}``.
        """


def get_pack(name: str) -> DomainPack:
    """Load a pack by name (`ragfilings.domains.<name>.PACK`)."""
    if name not in _KNOWN_PACKS:
        raise ValueError(f"unknown domain pack {name!r} — available: {', '.join(_KNOWN_PACKS)}")
    module = import_module(f"ragfilings.domains.{name}")
    pack = getattr(module, "PACK", None)
    if pack is None:
        raise ValueError(f"domain pack {name!r} exports no PACK object")
    if not isinstance(pack, DomainPack):
        raise TypeError(f"domain pack {name!r} does not satisfy DomainPack")
    return pack


def available_packs() -> tuple[str, ...]:
    return _KNOWN_PACKS
