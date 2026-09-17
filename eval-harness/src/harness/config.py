"""Harness config loader.

Loads config.toml (judge model + settings) and merges environment variables.
Keeps deliberately small: the harness only needs judge settings; the target
system under test (e.g. ragfilings) carries its own config.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    """Populate environment from a .env file if present (repo root or cwd)."""
    for candidate in (ROOT / ".env", ROOT.parent / ".env", Path.cwd() / ".env"):
        if candidate.exists():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
            break


def load(path: str | Path | None = None) -> dict[str, Any]:
    """Load the harness config.toml. `path` overrides the default location."""
    _load_env()
    cfg_path = Path(path) if path else ROOT / "config.toml"
    with cfg_path.open("rb") as f:
        return tomllib.load(f)
