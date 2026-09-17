#!/usr/bin/env python3
"""Dump parsed section trees to corpus/parsed/{ticker}_sections.json.

    uv run python scripts/dump_sections.py

Structure per file: {section_id: {title, part, char_count, text}}, where
section_id is "Item7" / "Item1A" to match golden-set citations (AAPL_2025_10K:Item7).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ragfilings import config as cfg_mod
from ragfilings import ingestion

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    cfg = cfg_mod.load()
    min_chars = cfg["ingestion"]["min_section_chars"]
    pointer_chars = cfg["ingestion"]["pointer_chars"]
    out_dir = ROOT / "corpus" / "parsed"
    out_dir.mkdir(parents=True, exist_ok=True)

    with (ROOT / cfg["corpus"]["manifest"]).open() as f:
        manifest = list(csv.DictReader(f))

    total = 0
    for m in manifest:
        path = ROOT / "corpus" / m["local_file"]
        if not path.exists():
            continue
        sections = ingestion.parse_file(path, min_chars, pointer_chars)
        tree = {
            f"Item{s.item}": {
                "title": s.title,
                "part": s.part,
                "char_count": s.n_chars,
                **({"resolved_from": f"Item{s.resolved_from}"} if s.resolved_from else {}),
                "text": s.text,
            }
            for s in sections
        }
        (out_dir / f"{m['ticker']}_sections.json").write_text(
            json.dumps(tree, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        total += len(sections)
        print(f"{m['ticker']:<6} {len(sections):>2} sections")

    print(f"\n{len(manifest)} filings, {total} sections -> {out_dir}")


if __name__ == "__main__":
    main()
