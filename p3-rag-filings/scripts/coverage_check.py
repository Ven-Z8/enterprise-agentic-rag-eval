#!/usr/bin/env python3
"""Coverage check: run the parser over every filing in the manifest and classify it.

    uv run python scripts/coverage_check.py            # human table
    uv run python scripts/coverage_check.py --json      # machine-readable

Two things worth knowing about 10-K structure, learned from the corpus:
  - Items 7A (market risk) and 9A (controls) are routinely a few hundred to a few
    thousand chars — boilerplate or by-reference. Short is NORMAL, not a bug.
  - Many filers make Item 7 (MD&A) / Item 8 (financials) one-line POINTERS and put
    the real statements in an unnumbered "Financial Section" / F-pages, or under
    Part IV Item 15. The parser resolves those stubs by content anchor and marks
    the section with resolved_from ("resolved" status here). "reloc-financials"
    remains only for filings where resolution FAILED — a genuine gap.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from ragfilings import config as cfg_mod
from ragfilings import ingestion

ROOT = Path(__file__).resolve().parent.parent

# Structural core: every real 10-K has substantive Business + Risk Factors. Missing
# either means the parser lost the document's spine — a genuine failure.
CORE = ["1", "1A"]


def check_one(path: Path, min_section_chars: int, pointer_chars: int) -> dict:
    secs = ingestion.parse_file(path, min_section_chars, pointer_chars)
    chars = {s.item: s.n_chars for s in secs}
    missing_core = [i for i in CORE if i not in chars]
    reloc = [i for i in ("7", "8") if chars.get(i, 0) < pointer_chars]
    resolved = {s.item: s.resolved_from for s in secs if s.resolved_from}
    monotonic = sorted(ingestion._item_key(s.item) for s in secs)
    status = (
        "MISSING-CORE"
        if missing_core
        else "reloc-financials"
        if reloc
        else f"resolved({','.join(f'{k}<-{v}' for k, v in resolved.items())})"
        if resolved
        else "clean"
    )
    return {
        "file": path.name,
        "n_sections": len(secs),
        "missing_core": missing_core,
        "item7": chars.get("7", 0),
        "item8": chars.get("8", 0),
        "resolved": resolved,
        "biggest": max(((s.item, s.n_chars) for s in secs), key=lambda kv: kv[1], default=("-", 0)),
        "in_order": [ingestion._item_key(s.item) for s in secs] == monotonic,
        "status": status,
    }


def main() -> None:
    cfg = cfg_mod.load()
    min_chars = cfg["ingestion"]["min_section_chars"]
    pointer_chars = cfg["ingestion"]["pointer_chars"]
    rows = []
    with (ROOT / cfg["corpus"]["manifest"]).open() as f:
        for m in csv.DictReader(f):
            path = ROOT / "corpus" / m["local_file"]
            if not path.exists():
                continue
            r = check_one(path, min_chars, pointer_chars)
            r["ticker"] = m["ticker"]
            rows.append(r)

    if "--json" in sys.argv:
        print(json.dumps(rows, indent=2))
        return

    print(f"{'TICKER':<7}{'#SEC':>5}{'ORD':>5}  {'ITEM7':>9}{'ITEM8':>9}  {'BIGGEST':<14}STATUS")
    print("-" * 74)
    for r in rows:
        big = f"Item{r['biggest'][0]}={r['biggest'][1]:,}"
        ordf = "ok" if r["in_order"] else "OOO"
        miss = f" missing:{','.join(r['missing_core'])}" if r["missing_core"] else ""
        print(
            f"{r['ticker']:<7}{r['n_sections']:>5}{ordf:>5}  {r['item7']:>9,}{r['item8']:>9,}  "
            f"{big:<14}{r['status']}{miss}"
        )

    n = len(rows)
    clean = sum(r["status"] == "clean" for r in rows)
    resolved = sum(r["status"].startswith("resolved") for r in rows)
    reloc = sum(r["status"] == "reloc-financials" for r in rows)
    bad = sum(r["status"] == "MISSING-CORE" for r in rows)
    ooo = sum(not r["in_order"] for r in rows)
    print(
        f"\n{clean}/{n} clean | {resolved} resolved | {reloc} unresolved-reloc | "
        f"{bad} missing-core | {ooo} out-of-order"
    )


if __name__ == "__main__":
    main()
