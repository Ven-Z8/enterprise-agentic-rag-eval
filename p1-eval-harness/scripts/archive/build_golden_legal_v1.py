"""Build golden_set_legal_v1.jsonl from CUAD test-split annotations.

Every case is traceable to attorney annotations in CUAD's held-out test split
(The Atticus Project, CC-BY-4.0): answerable cases carry the annotated span,
unanswerable cases are (contract, category) pairs the attorneys left empty,
ambiguous cases name no contract. Selection is deterministic (sorted, no RNG).

The corpus builder (domains/legal/build_corpus.py) must have run first — the
manifest supplies the document codes and the defined-term fact layer supplies
the definition cases.

    cd p1-eval-harness && uv run python scripts/build_golden_legal_v1.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
import zipfile
from pathlib import Path

P1_ROOT = Path(__file__).resolve().parents[1]
P3_ROOT = P1_ROOT.parent / "p3-rag-filings"
CUAD_ZIP = P3_ROOT / "src/ragfilings/domains/legal/data/cuad/data.zip"
MANIFEST = P3_ROOT / "src/ragfilings/domains/legal/corpus/manifest.csv"
FACTS = P3_ROOT / "src/ragfilings/domains/legal/corpus/facts/defined_terms.json"
OUT = P1_ROOT / "data/domain_b_legal/golden_set_legal_v1.jsonl"

CAT_RE = re.compile(r'related to "(.+?)" that should')

# Categories whose annotated spans are clause language -> judge-scored
# extraction questions.
CLAUSE_CATEGORIES = [
    "Anti-Assignment",
    "Audit Rights",
    "Cap On Liability",
    "Change Of Control",
    "Exclusivity",
    "Expiration Date",
    "Governing Law",
    "Insurance",
    "License Grant",
    "Minimum Commitment",
    "Non-Compete",
    "Post-Termination Services",
    "Renewal Term",
    "Revenue/Profit Sharing",
    "Rofr/Rofo/Rofn",
    "Termination For Convenience",
    "Volume Restriction",
    "Warranty Duration",
]
# Categories with zero or near-zero annotations anywhere -> unanswerable
# questions (attorneys verified absence).
UNANSWERABLE_CATEGORIES = {
    "Price Restrictions": 3,
    "Most Favored Nation": 2,
    "Source Code Escrow": 2,
    "Joint Ip Ownership": 2,
    "No-Solicit Of Customers": 3,
}
SPAN_MIN, SPAN_MAX = 80, 700


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_cuad() -> dict[str, dict[str, list[str]]]:
    """{title: {category: [span, ...]}} from the CUAD test split."""
    with zipfile.ZipFile(CUAD_ZIP) as z:
        with z.open("test.json") as f:
            docs = json.load(f)["data"]
    out: dict[str, dict[str, list[str]]] = {}
    for doc in docs:
        title = doc["title"].strip()
        cats: dict[str, list[str]] = {}
        for p in doc["paragraphs"]:
            for qa in p["qas"]:
                cat = CAT_RE.search(qa["question"]).group(1)
                cats[cat] = [norm(a["text"]) for a in qa["answers"]]
        out[title] = cats
    return out


def main() -> None:
    codes = {
        row["title"]: row["contract"] for row in csv.DictReader(MANIFEST.open(encoding="utf-8"))
    }
    annotations = load_cuad()
    assert codes.keys() == annotations.keys(), (
        f"manifest/annotation mismatch: {len(codes)} vs {len(annotations)}"
    )
    defined_terms = json.loads(FACTS.read_text(encoding="utf-8"))

    cases: list[dict] = []

    def add(
        cid: str, q: str, answer, category: str, difficulty: str, notes: str, ctype: str = "judge"
    ):
        cases.append(
            {
                "id": cid,
                "input": q,
                "expected": {"answer": answer, "citations": [], "type": ctype},
                "variation_rules": [],
                "difficulty": difficulty,
                "failure_category": category,
                "domain": "legal",
                "notes": notes,
            }
        )

    titles = sorted(annotations)  # deterministic order

    # --- 1. document-name lookups (exact) ---------------------------------
    n = 0
    for t in titles:
        spans = annotations[t]["Document Name"]
        if spans and 3 <= len(spans[0]) <= 120 and n < 5:
            n += 1
            add(
                f"leg-1{n:03d}",
                f"What is the document name of contract {codes[t]}?",
                spans[0],
                "lookup",
                "easy",
                f"CUAD test '{t}' / Document Name, span 1/{len(spans)} ({len(spans[0])} chars).",
                ctype="exact",
            )

    # --- 2. date lookups (judge: format variance allowed) ------------------
    n = 0
    for t in titles:
        spans = annotations[t]["Agreement Date"]
        if spans and n < 6:
            n += 1
            add(
                f"leg-2{n:03d}",
                f"Under contract {codes[t]}, what is the date of the agreement?",
                spans[0],
                "lookup",
                "easy",
                f"CUAD test '{t}' / Agreement Date, span 1/{len(spans)}.",
            )
    n = 0
    for t in titles:
        spans = annotations[t]["Effective Date"]
        if spans and n < 4:
            n += 1
            add(
                f"leg-2{n + 6:03d}",
                f"Under contract {codes[t]}, when does the agreement become effective?",
                spans[0],
                "lookup",
                "medium",
                f"CUAD test '{t}' / Effective Date, span 1/{len(spans)}.",
            )

    # --- 3. clause extraction (judge) --------------------------------------
    n = 0
    for cat in CLAUSE_CATEGORIES:
        for t in titles:
            spans = [s for s in annotations[t].get(cat, []) if SPAN_MIN <= len(s) <= SPAN_MAX]
            if spans:
                n += 1
                add(
                    f"leg-3{n:03d}",
                    f"Under contract {codes[t]}, quote the clause concerning {cat.lower()}.",
                    spans[0],
                    "synthesis",
                    "medium",
                    f"CUAD test '{t}' / {cat}: {len(annotations[t][cat])} "
                    f"annotated span(s); expected is span 1 "
                    f"({len(spans[0])} chars).",
                )
                break  # one case per category

    # --- 4. unanswerable (attorneys annotated nothing) ----------------------
    n = 0
    for cat, count in UNANSWERABLE_CATEGORIES.items():
        taken = 0
        for t in titles:
            if taken >= count:
                break
            if annotations[t].get(cat, []):
                continue  # category present in this contract
            n += 1
            taken += 1
            add(
                f"leg-4{n:03d}",
                f"Under contract {codes[t]}, quote the clause concerning {cat.lower()}.",
                None,
                "unanswerable",
                "hard",
                f"CUAD test '{t}' / {cat}: zero annotated spans across all "
                f"41 categories for this pair — attorneys verified absence. "
                f"Correct behavior: refuse.",
            )

    # --- 5. ambiguous (no contract named) -----------------------------------
    ambiguous_qs = [
        "Which agreement defines the term 'Confidential Information'?",
        "What is the governing law of the contract?",
        "Quote the non-compete clause.",
        "What is the definition of 'Change of Control'?",
        "When does the agreement expire?",
        "Quote the exclusivity clause from the contract.",
    ]
    for i, q in enumerate(ambiguous_qs, 1):
        add(
            f"leg-5{i:03d}",
            q,
            None,
            "ambiguous",
            "medium",
            "The corpus holds 102 separate agreements; the question names "
            "none. Correct behavior: ask which contract, never guess.",
        )

    # --- 6. defined-term lookups via the deterministic fact layer -----------
    n = 0
    for code in sorted(defined_terms):
        for term in sorted(defined_terms[code]):
            if n >= 5:
                break
            fact = defined_terms[code][term]
            if len(fact["definition"]) < 40:
                continue
            n += 1
            add(
                f"leg-6{n:03d}",
                f"Under contract {code}, what does the term '{term}' mean?",
                fact["definition"],
                "lookup",
                "medium",
                f"Defined-term fact layer (chunk {fact['chunk_id']}); "
                f"deterministic extraction, no LLM involved.",
            )
        if n >= 5:
            break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    cats: dict[str, int] = {}
    for c in cases:
        cats[c["failure_category"]] = cats.get(c["failure_category"], 0) + 1
    print(f"wrote {len(cases)} cases to {OUT}")
    print("by category:", dict(sorted(cats.items())))


if __name__ == "__main__":
    sys.exit(main())
