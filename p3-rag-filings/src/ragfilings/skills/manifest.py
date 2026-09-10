"""Pydantic schema for SKILL.md YAML frontmatter."""

from __future__ import annotations

import re
from pydantic import BaseModel, Field
import yaml


class SkillManifest(BaseModel):
    """Parsed YAML frontmatter from a SKILL.md file."""

    name: str = Field(description="Unique identifier for the skill, e.g. 'financial'.")
    display_name: str = Field(description="Human-readable title, e.g. 'SEC Financial & 10-K Analysis'.")
    description: str = Field(description="Concise description of the skill's domain and capabilities.")
    domain: str = Field(description="Target domain code, e.g. 'financial', 'legal', 'healthcare'.")
    activation_keywords: list[str] = Field(default_factory=list, description="Keywords that trigger or associate with this skill.")
    tools: list[str] = Field(default_factory=list, description="Names of tools available under this skill.")
    verification_type: str = Field(default="general", description="Verification strategy (e.g. monetary_claims, verbatim_quote).")
    version: str = Field(default="1.0.0", description="Skill semantic version.")


def parse_skill_markdown(text: str) -> tuple[SkillManifest, str]:
    """Parse a SKILL.md file into its (SkillManifest, markdown_body)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md must start with YAML frontmatter enclosed in '---'")
    frontmatter_raw, body = match.group(1), match.group(2)
    meta_dict = yaml.safe_load(frontmatter_raw) or {}
    manifest = SkillManifest.model_validate(meta_dict)
    return manifest, body.strip()
