"""Base class for modular Markdown-backed domain skills."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..domains import DomainPack
from ..prompts import PromptRegistry
from .manifest import SkillManifest, parse_skill_markdown

logger = logging.getLogger(__name__)


class DomainSkill(DomainPack):
    """A modular domain skill backed by a `SKILL.md` manifest and phase MD files.

    Inherits from DomainPack for seamless 100% backward compatibility with
    all existing pipeline and benchmark adapters.
    """

    manifest: SkillManifest
    skill_dir: Path
    overview: str
    _phase_cache: dict[str, str]

    def __init__(self, skill_dir: str | Path) -> None:
        self.skill_dir = Path(skill_dir).resolve()
        self._phase_cache = {}

        skill_md_path = self.skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            raise FileNotFoundError(f"SKILL.md not found in {self.skill_dir}")

        manifest, overview = parse_skill_markdown(skill_md_path.read_text(encoding="utf-8"))
        self.manifest = manifest
        self.overview = overview

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.manifest.name

    @property
    def display_name(self) -> str:  # type: ignore[override]
        return self.manifest.display_name

    def get_phase_instructions(self, phase: str) -> str:
        """Load markdown instructions for a specific pipeline phase (e.g. 'synthesis')."""
        if phase in self._phase_cache:
            return self._phase_cache[phase]

        phase_path = self.skill_dir / "phases" / f"{phase}.md"
        if phase_path.exists():
            text = phase_path.read_text(encoding="utf-8").strip()
            self._phase_cache[phase] = text
            return text

        # Fallback to PromptRegistry if phase md does not exist
        try:
            raw = PromptRegistry.get_raw(phase)
            self._phase_cache[phase] = raw
            return raw
        except Exception:
            # Fallback to general skill overview
            return self.overview

    def prompt(self, name: str) -> str:
        """Satisfies DomainPack.prompt() using phase markdown files."""
        return self.get_phase_instructions(name)

    def format_prompt(self, name: str, **kwargs: Any) -> str:
        """Satisfies DomainPack.format_prompt()."""
        raw = self.prompt(name)
        if not kwargs:
            return raw
        if name == "verification_retry" and isinstance(kwargs.get("failed_claims"), list):
            kwargs["failed_claims"] = ", ".join(kwargs["failed_claims"])
        try:
            return raw.format(**kwargs)
        except KeyError:
            # If prompt template uses different placeholders or plain markdown
            return raw
