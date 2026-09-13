"""Fetch and cache public legal benchmarks:
1. Stanford LegalBench (consumer_contracts_qa)
2. Isaacus Legal RAG Bench (qa + corpus)
"""

import json
import urllib.request
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "domain_b_legal"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_legalbench(limit: int = 50) -> None:
    print(f"Fetching {limit} cases from Stanford LegalBench (consumer_contracts_qa)...")
    url = f"https://datasets-server.huggingface.co/rows?dataset=nguha/legalbench&config=consumer_contracts_qa&split=test&offset=0&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    
    rows = data.get("rows", [])
    out_file = OUT_DIR / "legalbench_consumer_contracts_qa.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for item in rows:
            r = item["row"]
            case = {
                "id": f"legalbench-ccqa-{r['index']}",
                "input": {
                    "query": r["question"],
                    "contract": r["contract"],
                },
                "expected": {
                    "answer": r["answer"],  # "Yes" or "No"
                },
                "failure_category": "consumer_contract_qa",
                "difficulty": "medium",
                "domain": "legal",
                "metadata": {
                    "source": "nguha/legalbench",
                    "task": "consumer_contracts_qa",
                    "index": r["index"],
                },
            }
            f.write(json.dumps(case) + "\n")
    print(f" Saved {len(rows)} LegalBench cases to {out_file}")


def fetch_legalrag(limit: int = 50) -> None:
    print(f"Fetching {limit} cases from Isaacus Legal RAG Bench...")
    url_qa = f"https://datasets-server.huggingface.co/rows?dataset=isaacus/legal-rag-bench&config=qa&split=test&offset=0&limit={limit}"
    req_qa = urllib.request.Request(url_qa, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_qa, timeout=30) as resp:
        data_qa = json.loads(resp.read().decode())
    
    qa_rows = data_qa.get("rows", [])
    needed_passages = set()
    out_qa_file = OUT_DIR / "legalrag_bench_qa.jsonl"
    with open(out_qa_file, "w", encoding="utf-8") as f:
        for item in qa_rows:
            r = item["row"]
            needed_passages.add(r["relevant_passage_id"])
            case = {
                "id": f"legalrag-{r['id']}",
                "input": {
                    "query": r["question"],
                },
                "expected": {
                    "answer": r["answer"],
                    "relevant_passage_id": r["relevant_passage_id"],
                },
                "failure_category": "statutory_rag",
                "difficulty": "hard",
                "domain": "legal",
                "metadata": {
                    "source": "isaacus/legal-rag-bench",
                    "task": "criminal_benchbook_rag",
                    "relevant_passage_id": r["relevant_passage_id"],
                },
            }
            f.write(json.dumps(case) + "\n")
    print(f" Saved {len(qa_rows)} Legal RAG QA cases to {out_qa_file}")
    print(f" Cases reference {len(needed_passages)} distinct ground-truth passages.")

    # Fetch corpus rows
    print("Fetching corpus passages from Isaacus Legal RAG Bench...")
    url_corpus = "https://datasets-server.huggingface.co/rows?dataset=isaacus/legal-rag-bench&config=corpus&split=test&offset=0&limit=100"
    req_corpus = urllib.request.Request(url_corpus, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_corpus, timeout=30) as resp:
        data_corpus = json.loads(resp.read().decode())
    
    corpus_rows = data_corpus.get("rows", [])
    out_corpus_file = OUT_DIR / "legalrag_bench_corpus.jsonl"
    with open(out_corpus_file, "w", encoding="utf-8") as f:
        for item in corpus_rows:
            r = item["row"]
            f.write(json.dumps({
                "id": r["id"],
                "title": r["title"],
                "text": r["text"],
                "footnotes": r.get("footnotes", []),
            }) + "\n")
    print(f" Saved {len(corpus_rows)} corpus passages to {out_corpus_file}")


if __name__ == "__main__":
    fetch_legalbench(50)
    fetch_legalrag(50)
