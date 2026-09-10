"""Registry and discovery for modular domain skills."""

from __future__ import annotations

import logging
from pathlib import Path

from .base import DomainSkill
from .manifest import SkillManifest, parse_skill_markdown

logger = logging.getLogger(__name__)

_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent
_REGISTRY: dict[str, DomainSkill] = {}


def register_skill(skill: DomainSkill) -> None:
    """Register an instantiated skill instance."""
    _REGISTRY[skill.manifest.name] = skill
    if skill.manifest.domain != skill.manifest.name:
        _REGISTRY[skill.manifest.domain] = skill


def get_skill(name: str) -> DomainSkill:
    """Retrieve an active DomainSkill by name or domain."""
    if name in _REGISTRY:
        return _REGISTRY[name]

    # Try loading from builtin skills directory
    skill_dir = _BUILTIN_SKILLS_DIR / name
    if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
        skill = _load_skill_from_dir(skill_dir)
        register_skill(skill)
        return skill

    # Backward compatibility with existing domains/<name>
    domains_dir = _BUILTIN_SKILLS_DIR.parent / "domains" / name
    if domains_dir.is_dir():
        import importlib

        mod = importlib.import_module(f"ragfilings.domains.{name}")
        pack = getattr(mod, "PACK", None)
        if isinstance(pack, DomainSkill):
            register_skill(pack)
            return pack
        elif pack is not None:
            return pack  # type: ignore[return-value]

    raise ValueError(f"Unknown domain skill {name!r}. Available: {available_skills()}")


def list_skills() -> list[SkillManifest]:
    """List manifests of all discovered skills."""
    manifests: list[SkillManifest] = []
    seen: set[str] = set()

    for item in _BUILTIN_SKILLS_DIR.iterdir():
        if item.is_dir() and (item / "SKILL.md").exists():
            try:
                skill_md = (item / "SKILL.md").read_text(encoding="utf-8")
                manifest, _ = parse_skill_markdown(skill_md)
                if manifest.name not in seen:
                    manifests.append(manifest)
                    seen.add(manifest.name)
            except Exception as exc:
                logger.warning("Failed to parse SKILL.md in %s: %s", item, exc)

    return manifests


def available_skills() -> tuple[str, ...]:
    """Return names of all available domain skills."""
    discovered = [m.name for m in list_skills()]
    for known in ("financial", "legal"):
        if known not in discovered:
            discovered.append(known)
    return tuple(sorted(set(discovered)))


def _load_skill_from_dir(skill_dir: Path) -> DomainSkill:
    """Helper to load a DomainSkill or domain-specific subclass from a directory."""
    name = skill_dir.name
    if name == "financial":
        from .financial.skill import FinancialSkill

        return FinancialSkill(skill_dir)
    if name == "legal":
        from .legal.skill import LegalSkill

        return LegalSkill(skill_dir)
    return DomainSkill(skill_dir)
