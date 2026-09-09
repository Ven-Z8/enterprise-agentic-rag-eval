"""Centralized Prompt Registry.

Manages all system, user, and agent prompt templates from a single typed interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_PROMPT_ROOT = Path(__file__).resolve().parent
# Prompt templates live with the domain pack that owns them; the financial
# pack's set is the engine default. Other packs load their own templates via
# their DomainPack.prompt() implementation.
_TEMPLATES_DIR = _PROMPT_ROOT.parent / "domains" / "financial" / "prompts"


class PromptRegistry:
    """Thread-safe registry for loading, caching, and formatting prompt templates."""

    _cache: dict[str, str] = {}

    @classmethod
    def get_raw(cls, name: str) -> str:
        """Load raw prompt template string by name."""
        if name in cls._cache:
            return cls._cache[name]

        candidates = [
            _TEMPLATES_DIR / f"{name}.prompt",
            _TEMPLATES_DIR / f"{name}.txt",
            _PROMPT_ROOT / f"{name}.prompt",
            _PROMPT_ROOT / f"{name}.txt",
        ]

        for p in candidates:
            if p.exists():
                text = p.read_text(encoding="utf-8").strip()
                cls._cache[name] = text
                return text

        raise FileNotFoundError(
            f"Prompt template '{name}' not found. Searched paths: {[str(p) for p in candidates]}"
        )

    @classmethod
    def format(cls, name: str, **kwargs: Any) -> str:
        """Load and format a template with kwargs."""
        raw = cls.get_raw(name)
        if not kwargs:
            return raw
        try:
            return raw.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing required prompt format variable {e} for prompt '{name}'")

    @classmethod
    def get_system_synthesis(cls) -> str:
        return cls.get_raw("synthesis")

    @classmethod
    def get_verification_retry(cls, failed_claims: list[str] | str) -> str:
        failed_str = (
            ", ".join(failed_claims) if isinstance(failed_claims, list) else str(failed_claims)
        )
        return cls.format("verification_retry", failed_claims=failed_str)

    @classmethod
    def get_math_tool(cls) -> str:
        return cls.get_raw("math_tool")

    @classmethod
    def get_query_decompose(cls) -> str:
        return cls.get_raw("query_decompose")

    @classmethod
    def get_planner(cls) -> str:
        return cls.get_raw("planner")

    @classmethod
    def get_researcher(cls) -> str:
        return cls.get_raw("researcher")

    @classmethod
    def get_auditor(cls) -> str:
        return cls.get_raw("auditor")

    @classmethod
    def get_converse_rewrite(cls) -> str:
        return cls.get_raw("converse_rewrite")


def load_prompt(name: str, **kwargs: Any) -> str:
    """Convenience functional accessor."""
    return PromptRegistry.format(name, **kwargs) if kwargs else PromptRegistry.get_raw(name)
