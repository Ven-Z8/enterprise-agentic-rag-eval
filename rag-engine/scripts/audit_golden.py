"""Audit the golden question set against the actual corpus.

Every answerable case's expected answer must be verifiable against the real
filing text before it can enter golden_set_v1.jsonl (schema.md rule 1). This
script automates the mechanical part:

- resolves each citation (TICKER_YEAR_10K[:ItemX]) to parsed section text
- extracts numeric claims from the expected answer and searches for them in
  the cited section first, then the whole filing
- flags unanswerable/ambiguous/judge cases for manual review
- validates schema fields (ids unique, enums legal, citations present)

Outputs audit_v1.json into the p1-eval-harness golden data dir
(machine-readable) and prints a summary.
Run: uv run python scripts/audit_golden.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ragfilings.domains.financial.verification import extract_claims  # noqa: E402

# Canonical golden data lives in the sibling eval-harness project.
GOLDEN_DIR = ROOT.parent / "eval-harness" / "data" / "domain_a_financial"
PARSED_DIR = ROOT / "corpus" / "parsed"
CHUNKS_DIR = ROOT / "corpus" / "chunks"

VALID_CATEGORIES = {"lookup", "synthesis", "table", "unanswerable", "ambiguous"}
VALID_DIFFICULTY = {"easy", "medium", "hard"}
VALID_TYPES = {"exact", "contains", "judge"}


def load_sections() -> tuple[dict[str, dict[str, str]], dict[str, str], dict[str, str]]:
    """Returns (per-ticker section text, per-ticker full text, ticker -> doc_id)."""
    sections: dict[str, dict[str, str]] = {}
    full: dict[str, str] = {}
    for path in sorted(PARSED_DIR.glob("*_sections.json")):
        ticker = path.name.split("_")[0]
        data = json.loads(path.read_text(encoding="utf-8"))
        sec_text = {item: (v.get("text") or "") for item, v in data.items()}
        sections[ticker] = sec_text
        full[ticker] = "\n".join(sec_text.values())

    doc_ids: dict[str, str] = {}
    for path in sorted(CHUNKS_DIR.glob("*_chunks.jsonl")):
        with path.open(encoding="utf-8") as f:
            first = f.readline()
        if first.strip():
            chunk = json.loads(first)
            doc_ids[chunk["ticker"]] = chunk["doc_id"]
    return sections, full, doc_ids


def load_cases() -> list[dict]:
    cases = []
    for path in sorted(GOLDEN_DIR.glob("*.jsonl")):
        if any(
            s in path.name for s in ("skeleton", "candidates", "handcrafted", "judge_calibration")
        ):
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    case = json.loads(line)
                    case["_source"] = path.name
                    cases.append(case)
    return cases


def parse_citation(cit: str) -> tuple[str, str | None]:
    """'AAPL_2025_10K:Item7:c003' -> ('AAPL', 'Item7')."""
    head = cit.split(":")[0]
    ticker = head.split("_")[0]
    item = None
    parts = cit.split(":")
    if len(parts) > 1 and parts[1].startswith("Item"):
        item = parts[1]
    return ticker, item


def number_variants(value: float, is_pct: bool, raw: str) -> list[str]:
    """Textual variants of a claimed figure as they could appear in a filing."""
    variants = {raw.strip()}
    nums = [value]
    if not is_pct:
        # scale-word re-expression: $62.6 billion <-> 62,600 million <-> 62,600,000 thousands
        for factor in (1e3, 1e6, 1e9, 1e-3, 1e-6):
            nums.append(value * factor)
    for v in nums:
        if v != int(v) and abs(v) < 1e6:
            variants.add(f"{v:,.1f}")
            variants.add(f"{v:,.2f}")
            variants.add(f"{v:g}")
        else:
            iv = int(round(v))
            if abs(iv) < 10**15:
                variants.add(f"{iv:,}")
                variants.add(str(iv))
                variants.add(f"({iv:,})")  # parenthesized negatives
                variants.add(f"({iv})")
    return [v for v in variants if v]


def find_claim(claim: dict, text: str) -> bool:
    if claim["is_pct"]:
        variants = number_variants(claim["value"], True, claim["raw"])
        return any(v in text for v in variants)
    variants = number_variants(claim["value"], False, claim["raw"])
    for v in variants:
        if v and len(v) >= 2 and v in text:
            return True
    return False


def audit_case(case: dict, sections, full, doc_ids) -> dict:
    out = {
        "id": case["id"],
        "source": case["_source"],
        "category": case.get("failure_category"),
        "type": case.get("expected", {}).get("type"),
        "verdict": None,
        "problems": [],
        "claim_checks": [],
    }

    # --- schema validation ---
    if case.get("failure_category") not in VALID_CATEGORIES:
        out["problems"].append(f"bad failure_category: {case.get('failure_category')!r}")
    if case.get("difficulty") not in VALID_DIFFICULTY:
        out["problems"].append(f"bad difficulty: {case.get('difficulty')!r}")
    if case.get("expected", {}).get("type") not in VALID_TYPES:
        out["problems"].append(f"bad expected.type: {case.get('expected', {}).get('type')!r}")

    expected = case.get("expected", {})
    citations = expected.get("citations", [])
    answer = expected.get("answer")

    # --- citation resolution ---
    cited_text = ""
    cited_where = []
    for cit in citations:
        ticker, item = parse_citation(cit)
        doc_id = doc_ids.get(ticker)
        if doc_id is None:
            out["problems"].append(f"citation ticker {ticker!r} not in corpus")
            continue
        if not cit.startswith(doc_id):
            out["problems"].append(f"citation {cit!r} != corpus doc id {doc_id!r}")
        if item is None:
            cited_text += full.get(ticker, "")
            cited_where.append(f"{ticker}:ALL")
        elif item in sections.get(ticker, {}):
            cited_text += sections[ticker][item]
            cited_where.append(f"{ticker}:{item}")
        else:
            out["problems"].append(f"citation section {item!r} not parsed for {ticker}")
    out["cited_where"] = cited_where

    if answer is None:
        out["verdict"] = "review_unanswerable"
        return out
    if out["category"] == "ambiguous":
        out["verdict"] = "review_ambiguous"
        return out
    if not citations:
        out["problems"].append("answerable case with no citations")

    claims = extract_claims(answer)
    if not claims:
        out["verdict"] = "review_text_only"
        return out

    filing_text = "\n".join(full.get(t, "") for t in {c.split("_")[0] for c in citations})
    n_section = n_filing = 0
    for claim in claims:
        in_section = bool(cited_text) and find_claim(claim, cited_text)
        in_filing = bool(filing_text) and find_claim(claim, filing_text)
        n_section += in_section
        n_filing += in_filing
        out["claim_checks"].append(
            {"raw": claim["raw"], "in_cited_section": in_section, "in_filing": in_filing}
        )

    if n_section == len(claims):
        out["verdict"] = "verified_in_cited_section"
    elif n_filing == len(claims):
        out["verdict"] = "verified_elsewhere_in_filing"
    elif n_filing > 0:
        out["verdict"] = "partially_verified"
    else:
        out["verdict"] = "not_found"
    return out


def main() -> None:
    sections, full, doc_ids = load_sections()
    cases = load_cases()
    results = [audit_case(c, sections, full, doc_ids) for c in cases]

    ids = [c["id"] for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        print(f"DUPLICATE IDS: {sorted(dupes)}")

    summary: dict[str, int] = {}
    for r in results:
        summary[r["verdict"]] = summary.get(r["verdict"], 0) + 1

    out_path = GOLDEN_DIR / "audit_v1.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Audited {len(results)} cases -> {out_path}")
    for verdict in sorted(summary):
        print(f"  {verdict:35s} {summary[verdict]:3d}")
    flagged = [r for r in results if r["problems"]]
    print(f"\nCases with schema/citation problems: {len(flagged)}")
    for r in flagged:
        print(f"  {r['id']}: {'; '.join(r['problems'])}")


if __name__ == "__main__":
    main()
