"""Build the legal-pack corpus from the CUAD test split.

CUAD (The Atticus Project, CC-BY-4.0): 510 commercial contracts with
attorney-annotated clause spans across 41 categories. This builder indexes
the held-out TEST split (102 contracts) — the golden set draws its proven
answers from those same annotations, so the corpus builder never touches
them: indexing sees contract text only, exactly like the financial corpus.

Steps: download-free (data/cuad/data.zip is unpacked once), derive a stable
document code per contract, chunk the text, extract the defined-term fact
layer, write the manifest, and embed the index.

    uv run python src/ragfilings/domains/legal/build_corpus.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
import zipfile
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parent
P3_ROOT = PACK_ROOT.parents[3]
sys.path.insert(0, str(P3_ROOT / "src"))

from ragfilings import ingestion, retrieval  # noqa: E402
from ragfilings.domains.legal.facts import extract_defined_terms  # noqa: E402

DATA_ZIP = PACK_ROOT / "data" / "cuad" / "data.zip"
CORPUS = PACK_ROOT / "corpus"
CONTRACTS_DIR = CORPUS / "contracts"
CHUNKS_DIR = CORPUS / "chunks"
INDEX_DIR = CORPUS / "index"
MANIFEST = CORPUS / "manifest.csv"
FACTS_DIR = CORPUS / "facts"

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
CHUNK_CHARS = 1800


def load_test_split() -> list[dict]:
    with zipfile.ZipFile(DATA_ZIP) as z:
        with z.open("test.json") as f:
            return json.load(f)["data"]


def contract_code(title: str, seen: dict[str, int]) -> str:
    """Stable, unique, question-friendly code from the CUAD title.

    The full first title token (never truncated mid-word) so the code reads
    as the company name it is; the code also appears in every chunk header,
    which is how retrieval pins a question to its contract.
    """
    first = re.split(r"[_\s]", title.strip())[0]
    code = re.sub(r"[^A-Za-z0-9]", "", first).upper()
    if len(code) < 3:  # too short to be unambiguous in a question
        code = f"CONTRACT{len(seen) + 1}"
    base = code
    seen[base] = seen.get(base, 0) + 1
    if seen[base] > 1:
        code = f"{base}-{seen[base]}"
    assert len(code) >= 3
    return code


def chunk_contract(code: str, title: str, text: str) -> list[dict]:
    chunks: list[dict] = []
    for sec in ingestion.sections_from_text(text, max_section_chars=6000):
        lines = sec.text.strip().split("\n")
        cur: list[str] = []
        cur_len = 0

        def flush() -> None:
            nonlocal cur, cur_len
            if not cur:
                return
            chunks.append(
                {
                    "id": f"{code}:{sec.item}:c{len([c for c in chunks if c['section_id'] == sec.item]):03d}",
                    "doc_id": code,
                    "doc_type": "contract",
                    "contract": code,
                    "contract_title": title,
                    "item": sec.item,
                    "section_id": sec.item,
                    "title": title,
                    "text": "\n".join(cur),
                    "n_chars": sum(len(ln) + 1 for ln in cur),
                }
            )
            cur, cur_len = [], 0

        for ln in lines:
            if cur and cur_len + len(ln) + 1 > CHUNK_CHARS:
                flush()
            cur.append(ln)
            cur_len += len(ln) + 1
        flush()
    return chunks


def main() -> None:
    for d in (CONTRACTS_DIR, CHUNKS_DIR, FACTS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    docs = load_test_split()
    seen: dict[str, int] = {}
    manifest_rows: list[dict] = []
    all_chunks: list[dict] = []

    for i, doc in enumerate(sorted(docs, key=lambda d: d["title"]), 1):
        title = doc["title"].strip()
        code = contract_code(title, seen)
        context = doc["paragraphs"][0]["context"]
        (CONTRACTS_DIR / f"{code}.txt").write_text(context, encoding="utf-8")
        chunks = chunk_contract(code, title, context)
        with (CHUNKS_DIR / f"{code}.jsonl").open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        all_chunks.extend(chunks)
        manifest_rows.append(
            {"contract": code, "title": title, "n_chars": len(context), "n_chunks": len(chunks)}
        )
        print(f"[{i:>3}/{len(docs)}] {code:26} {len(context):>7,} chars -> {len(chunks)} chunks")

    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["contract", "title", "n_chars", "n_chunks"])
        w.writeheader()
        w.writerows(manifest_rows)

    terms = extract_defined_terms(all_chunks)
    n_terms = sum(len(v) for v in terms.values())
    (FACTS_DIR / "defined_terms.json").write_text(
        json.dumps(terms, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"\ncontracts: {len(manifest_rows)} | chunks: {len(all_chunks)} "
        f"| defined terms: {n_terms} across {len(terms)} contracts"
    )

    print(f"embedding {len(all_chunks)} chunks with {EMBED_MODEL} ...")
    retrieval.build_index(all_chunks, INDEX_DIR, EMBED_MODEL)
    print(f"index written to {INDEX_DIR}")


if __name__ == "__main__":
    main()
