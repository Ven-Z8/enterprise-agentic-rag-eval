"""Config loading. TOML via stdlib tomllib — no dependency needed.

Usage:
    from ragfilings.config import load
    cfg = load()                 # reads ./config.toml
    cfg["retrieval"]["top_k"]    # plain dicts, nothing clever
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

# Repo root = two levels up from this file (src/ragfilings/config.py).
ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = ROOT / "config.toml"


def _load_env() -> None:
    for env_path in [ROOT / ".env", ROOT.parent / ".env"]:
        if env_path.exists():
            with env_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v


def load(path: str | Path | None = None) -> dict:
    """Load a TOML config into nested dicts. Defaults to repo-root config.toml."""
    _load_env()
    p = Path(path) if path else DEFAULT_CONFIG
    with p.open("rb") as f:
        return tomllib.load(f)
