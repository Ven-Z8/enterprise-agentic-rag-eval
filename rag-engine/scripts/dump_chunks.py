#!/usr/bin/env python3
"""Dump retrieval-ready chunks to corpus/chunks/{ticker}_chunks.jsonl.

    uv run python scripts/dump_chunks.py

One JSON object per line, id format {doc_id}:{section_id}:cNNN — a prefix
match against golden-set citations ("AAPL_2025_10K:Item8").
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ragfilings import chunking, ingestion
from ragfilings import config as cfg_mod

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    cfg = cfg_mod.load()
    ing = cfg["ingestion"]
    max_chars = cfg["chunking"]["max_chars"]
    out_dir = ROOT / "corpus" / "chunks"
    out_dir.mkdir(parents=True, exist_ok=True)

    total = n_tables = n_notes = 0
    with (ROOT / cfg["corpus"]["manifest"]).open() as f:
        for m in csv.DictReader(f):
            path = ROOT / "corpus" / m["local_file"]
            if not path.exists():
                continue
            sections = ingestion.parse_file(path, ing["min_section_chars"], ing["pointer_chars"])
            chunks = chunking.chunk_sections(sections, m, max_chars)
            with (out_dir / f"{m['ticker']}_chunks.jsonl").open("w", encoding="utf-8") as out:
                for c in chunks:
                    out.write(json.dumps(c, ensure_ascii=False) + "\n")
            total += len(chunks)
            n_tables += sum(c["has_table"] for c in chunks)
            n_notes += sum(c["note"] is not None for c in chunks)
            print(f"{m['ticker']:<6} {len(chunks):>5} chunks")

    print(f"\n{total:,} chunks ({n_tables:,} with tables, {n_notes:,} inside notes) -> {out_dir}")


if __name__ == "__main__":
    main()
