"""Build the biomedical domain pack corpus from official PubMedQA literature.

PubMedQA (EMNLP 2019): Biomedical question-answering dataset collected from
PubMed abstracts. Each instance contains a PMID, question, structured context
sections (e.g. BACKGROUND, METHODS, RESULTS, CONCLUSIONS), publication year,
and ground-truth clinical decision.

This builder:
1. Downloads / loads the official PQA-L dataset (ori_pqal.json).
2. Chunks literature abstracts by structured scientific sections.
3. Attaches clean provenance metadata (PMID, section, year, title).
4. Persists chunks and builds the dense BGE embedding + BM25 index.

Usage:
    python src/ragfilings/domains/biomedical/build_corpus.py [--max-docs 250]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import urllib.request
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parent
P3_ROOT = PACK_ROOT.parents[3]
sys.path.insert(0, str(P3_ROOT / "src"))

from ragfilings import retrieval  # noqa: E402

DATA_DIR = PACK_ROOT / "data"
CORPUS_DIR = PACK_ROOT / "corpus"
CHUNKS_DIR = CORPUS_DIR / "chunks"
INDEX_DIR = CORPUS_DIR / "index"
MANIFEST = CORPUS_DIR / "manifest.csv"

RAW_DATA_PATH = DATA_DIR / "ori_pqal.json"
PUBMEDQA_URL = "https://raw.githubusercontent.com/pubmedqa/pubmedqa/master/data/ori_pqal.json"

EMBED_MODEL = "BAAI/bge-small-en-v1.5"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def ensure_dataset() -> dict:
    """Download or load the official PubMedQA PQA-L labeled dataset."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not RAW_DATA_PATH.exists():
        logger.info("Downloading official PubMedQA dataset from %s ...", PUBMEDQA_URL)
        req = urllib.request.Request(
            PUBMEDQA_URL,
            headers={"User-Agent": "DomainAdaptiveRAG/1.0 (biomedical-corpus-builder)"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        with RAW_DATA_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved %d articles to %s", len(data), RAW_DATA_PATH)
    else:
        with RAW_DATA_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded %d articles from %s", len(data), RAW_DATA_PATH)
    return data


def chunk_article(pmid: str, item: dict) -> list[dict]:
    """Chunk a biomedical article by its structured sections."""
    chunks: list[dict] = []
    contexts = item.get("CONTEXTS", [])
    labels = item.get("LABELS", [])
    year = str(item.get("YEAR", ""))
    question = item.get("QUESTION", "")
    meshes = item.get("MESHES", [])

    for i, ctx in enumerate(contexts):
        sec_label = labels[i] if i < len(labels) else f"SECTION_{i+1}"
        cid = f"PMID:{pmid}:{sec_label}:c{i+1:03d}"
        title = f"PubMed Article {pmid} (Re: {question[:60]}...)" if question else f"PubMed Article {pmid}"

        chunk = {
            "id": cid,
            "doc_id": pmid,
            "doc_type": "biomedical",
            "pmid": pmid,
            "year": year,
            "title": title,
            "item": sec_label,
            "section": sec_label,
            "section_id": sec_label,
            "meshes": meshes,
            "text": ctx.strip(),
            "n_chars": len(ctx.strip()),
        }
        chunks.append(chunk)

    return chunks


def main() -> None:
    ap = argparse.ArgumentParser(description="Biomedical Corpus Builder")
    ap.add_argument("--max-docs", type=int, default=300, help="Number of PubMed articles to index")
    args = ap.parse_args()

    for d in (CORPUS_DIR, CHUNKS_DIR, INDEX_DIR):
        d.mkdir(parents=True, exist_ok=True)

    data = ensure_dataset()
    sorted_pmids = sorted(data.keys())[: args.max_docs]

    all_chunks: list[dict] = []
    manifest_rows: list[dict] = []

    for i, pmid in enumerate(sorted_pmids, 1):
        item = data[pmid]
        chunks = chunk_article(pmid, item)
        all_chunks.extend(chunks)

        with (CHUNKS_DIR / f"{pmid}.jsonl").open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        manifest_rows.append(
            {
                "pmid": pmid,
                "year": item.get("YEAR", ""),
                "n_sections": len(chunks),
                "question": item.get("QUESTION", "")[:80],
                "decision": item.get("final_decision", ""),
            }
        )

        if i % 50 == 0 or i == len(sorted_pmids):
            print(f"[{i:>3}/{len(sorted_pmids)}] PMID {pmid} -> {len(chunks)} sections")

    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pmid", "year", "n_sections", "question", "decision"])
        w.writeheader()
        w.writerows(manifest_rows)

    print(f"\nIndexed {len(manifest_rows)} articles into {len(all_chunks)} chunks.")
    print(f"Building dense BGE embeddings ({EMBED_MODEL}) and BM25 index ...")
    retrieval.build_index(all_chunks, INDEX_DIR, EMBED_MODEL)
    print(f"Index successfully built and persisted at: {INDEX_DIR}\n")


if __name__ == "__main__":
    main()
