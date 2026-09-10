"""Modular Domain Skills framework for Generic RAG.

Each skill is a directory containing:
- `SKILL.md`: Manifest (YAML frontmatter) & domain overview
- `phases/*.md`: Modular instructions per pipeline phase (planning, synthesis, converse, verification)
- Deterministic tools and verification companion code
"""

from __future__ import annotations

from .base import DomainSkill
from .manifest import SkillManifest, parse_skill_markdown
from .registry import available_skills, get_skill, list_skills, register_skill

__all__ = [
    "DomainSkill",
    "SkillManifest",
    "parse_skill_markdown",
    "get_skill",
    "list_skills",
    "available_skills",
    "register_skill",
]
