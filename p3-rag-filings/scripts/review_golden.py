"""Human-review sheet for golden candidates.

For each case in golden/candidates_v1.jsonl, prints the provenance chunk
text around every figure the answer cites, so a reviewer can confirm the
number sits in the row the question claims. This is the human-in-the-loop
step of the golden-set builder (schema.md rule 1).

Usage: uv run python scripts/review_golden.py [--radius 120]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_DIR = ROOT / "corpus" / "chunks"
CANDIDATES = ROOT / "golden" / "candidates_v1.jsonl"


def load_chunks() -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in CHUNKS_DIR.glob("*_chunks.jsonl"):
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    c = json.loads(line)
                    texts[c["id"]] = c["text"]
    return texts


def figure_patterns(text: str) -> list[str]:
    """Numeric phrases to locate in the chunk (all comma-grouped numbers)."""
    return list(dict.fromkeys(re.findall(r"\(?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?|\d+\.\d{2}\b", text)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius", type=int, default=130)
    args = ap.parse_args()

    chunks = load_chunks()
    cases = [json.loads(line) for line in CANDIDATES.open(encoding="utf-8") if line.strip()]

    for case in cases:
        notes = case.get("notes", "")
        chunk_ids = re.findall(r"[\w]+_20\d\d_10K:Item\w+:c\d+", notes)
        print("=" * 100)
        print(
            f"{case['id']} [{case['failure_category']}/{case['difficulty']}/{case['expected']['type']}]"
        )
        print(f"  Q: {case['input']}")
        print(f"  A: {case['expected']['answer']}")
        for cid in dict.fromkeys(chunk_ids):
            text = chunks.get(cid, "")
            if not text:
                print(f"  !! chunk {cid} not found")
                continue
            nums = figure_patterns(case["expected"]["answer"])
            shown = False
            norm = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", text))
            for num in nums:
                src, probe = (text, num) if num in text else (norm, num)
                i = src.find(probe)
                if i == -1:
                    continue
                shown = True
                snippet = src[max(0, i - args.radius) : i + len(probe) + args.radius]
                print(f"  [{cid}] ...{snippet.replace(chr(10), ' | ')}...")
            if not shown:
                print(f"  [{cid}] !! none of {nums} located in chunk")
        print()


if __name__ == "__main__":
    main()
