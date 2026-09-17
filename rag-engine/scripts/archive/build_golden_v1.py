"""Build golden_set_v1 candidates from the stage-2 fact graph.

Every candidate case is grounded in MetricValue nodes (deterministically
extracted from the filings with chunk provenance — the LLM never contributed
a number). The generator re-verifies each figure against its source chunk
text before emitting the case, so no expected answer exists without textual
evidence in the corpus.

Exclusions (audit findings, 2026-08-30):
- NFLX: reports in thousands of dollars; conversion noise isn't worth testing
- "Gross Margin" facts: the graph conflates gross-profit dollars (AAPL, MSFT)
  with margin percentages (NVDA) under one metric label
- HD balance-sheet metrics (Total Assets / Total Liabilities / Cash & Cash
  Equivalents): the graph labels them with the calendar year of the period
  end (2026/2025) while Home Depot itself labels those balance sheets fiscal
  2025/2024 — a question would carry the wrong fiscal label

Usage: uv run python scripts/build_golden_v1.py
Emits golden/candidates_v1.jsonl (machine-verified) + a summary report.
Unanswerable and ambiguous cases are hand-authored separately.
"""

from __future__ import annotations

import csv
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "corpus" / "graph" / "financial_graph.json"
CHUNKS_DIR = ROOT / "corpus" / "chunks"
MANIFEST = ROOT / "corpus" / "manifest.csv"
OUT = ROOT / "golden" / "candidates_v1.jsonl"

SEED = 3
EXCLUDE_TICKERS = {"NFLX", "PFE"}  # NFLX: thousands reporting; PFE: every
# revenue/income fact extracted from segment or JV tables (consolidated total
# revenues are $62,579/$63,627/$59,553M FY2025/24/23 — the graph has none)
EXCLUDE_METRICS = {"Gross Margin"}
HD_BAD_METRICS = {"Total Assets", "Total Liabilities", "Cash & Cash Equivalents"}

# Net income is only used for companies whose statement line has no material
# attributable-to-shareholders split. Verified 2026-08-30 against the filings:
# DIS 7.7%, UNH 5.9%, GS 5.1%, JPM 2.4%, WMT 1.7%, TSLA 1.6%, CVX 1.5% gaps
# between "net income" and the attributable figure — over the numeric
# tolerance, so those facts are ambiguous ground truth and are excluded.
NET_INCOME_WHITELIST = {"GOOGL", "MSFT", "AMZN", "KO", "NVDA", "HD", "BA"}

# Facts verified WRONG by human review of the cited chunk (2026-08-30).
# Single source of truth: corpus/graph/excluded_facts.json (also consumed
# by the runtime graph rescue). Fix direction: the builder's table
# heuristics; until then they stay excluded here too.
BAD_FACTS = set(
    json.loads((ROOT / "corpus" / "graph" / "excluded_facts.json").read_text(encoding="utf-8"))[
        "excluded"
    ]
)

METRIC_PHRASE = {
    "Net Sales": "net sales",
    "Total Revenue": "total revenue",
    "Net Income": "net income",
    "Operating Income": "operating income",
    "Gross Profit": "gross profit",
    "R&D Expense": "research and development expense",
    "SG&A Expense": "selling, general and administrative expense",
    "Cost of Revenue": "cost of revenue",
    "Cost of Sales": "cost of sales",
    "Operating Expenses": "operating expenses",
    "Operating Cash Flow": "net cash provided by operating activities",
    "Capital Expenditures": "capital expenditures (purchases of property and equipment)",
    "Free Cash Flow": "free cash flow",
    "Total Assets": "total assets",
    "Total Liabilities": "total liabilities",
    "Cash & Cash Equivalents": "cash and cash equivalents",
    "Stockholders Equity": "total stockholders' equity",
    "Diluted EPS": "diluted earnings per share",
}

# deep-table metrics for the table-reading category
TABLE_METRICS = {
    "Total Liabilities",
    "SG&A Expense",
    "Cost of Sales",
    "Cost of Revenue",
    "Operating Expenses",
    "Total Assets",
    "Cash & Cash Equivalents",
    "Stockholders Equity",
    "Gross Profit",
    "Operating Cash Flow",
    "Capital Expenditures",
    "Free Cash Flow",
    "Diluted EPS",
    "R&D Expense",
}

# metrics subject to year-over-year plausibility screening (always-positive
# size metrics only — net income/operating income legitimately swing hard)
PLAUSIBLE_SERIES_METRICS = {
    "Net Sales",
    "Total Revenue",
    "Gross Profit",
    "Total Assets",
}
MAX_YOY_SWING = 0.75  # revenue/assets of these large caps do not move >75% YoY

# absolute floors (USD_M): every company in this corpus is a large cap; a
# "total revenue" of $52M is always a stray-number extraction error. Single-year
# series escape the YoY swing screen, so floors are the second line of defense.
SIZE_FLOORS = {
    "Total Revenue": 20000,
    "Net Sales": 20000,
    "Total Assets": 30000,
    "Operating Expenses": 5000,
}

DISPLAY_NAME = {"Meta Platforms": "Meta"}


def possessive(name: str) -> str:
    name = DISPLAY_NAME.get(name, name)
    return name + "'" if name.endswith("s") else name + "'s"


def company_names() -> dict[str, str]:
    with MANIFEST.open(encoding="utf-8") as f:
        return {r["ticker"]: r["company"] for r in csv.DictReader(f)}


def load_facts() -> list[dict]:
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    facts = [n for n in g["graph"]["nodes"] if n["label"] == "MetricValue"]
    kept = []
    for f in facts:
        if f["ticker"] in EXCLUDE_TICKERS or f["metric"] in EXCLUDE_METRICS:
            continue
        if f["id"] in BAD_FACTS:
            continue
        if f["metric"] == "Net Income" and f["ticker"] not in NET_INCOME_WHITELIST:
            continue
        if f["ticker"] == "HD" and f["metric"] in HD_BAD_METRICS:
            continue
        kept.append(f)
    return kept


def load_chunk_text() -> dict[str, str]:
    texts: dict[str, str] = {}
    for path in CHUNKS_DIR.glob("*_chunks.jsonl"):
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    c = json.loads(line)
                    texts[c["id"]] = c["text"]
    return texts


def value_variants(v: float) -> list[str]:
    variants = {f"{v:,.0f}", f"{v:,.1f}", f"{v:,.2f}"}
    if v == int(v):
        variants.add(str(int(v)))
    if v < 0:
        a = abs(v)
        # filings render negatives as parenthesized absolutes: (1,049)
        variants |= {f"({a:,.0f})", f"({a:,.1f})", f"({a:,.2f})"}
        if a == int(a):
            variants.add(f"({int(a)})")
    return sorted(variants)


def in_chunk(v: float, text: str) -> bool:
    # some filers pad parenthesized negatives: "( 11,829 )" — normalize first
    norm = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", text))
    return any(var in norm for var in value_variants(v))


def fmt_dollars(v: float, unit: str) -> str:
    if v < 0:
        a = abs(v)
        body = f"{int(a):,}" if a == int(a) else f"{a:,.2f}"
        return f"$({body}) million"
    if v == int(v):
        return f"${int(v):,} million"
    return f"${v:,.2f} million"


def fmt_eps(v: float) -> str:
    return f"${v:.2f} per share"


def fmt_answer(fact: dict) -> str:
    if fact["metric"] == "Diluted EPS":
        return fmt_eps(fact["value"])
    return fmt_dollars(fact["value"], fact["unit"])


def citation_of(fact: dict) -> str:
    doc, item, _chunk = fact["chunk_id"].split(":")
    return f"{doc}:{item}"


def rules_for(fact: dict, derived: bool = False) -> list[str]:
    if fact["metric"] == "Diluted EPS":
        return ["numeric_tolerance:0.5%"]
    return ["numeric_tolerance:1%" if derived else "numeric_tolerance:0.5%", "unit_equivalence"]


def make_case(
    cid, question, answer, facts, category, difficulty, ctype="exact", rules=None, notes=""
) -> dict:
    rules = rules if rules is not None else rules_for(facts[0])
    cits = sorted({citation_of(f) for f in facts})
    fact_ids = ", ".join(f["id"] for f in facts)
    chunk_ids = ", ".join(f["chunk_id"] for f in facts)
    return {
        "id": cid,
        "input": question,
        "expected": {"answer": answer, "citations": cits, "type": ctype},
        "variation_rules": rules,
        "difficulty": difficulty,
        "failure_category": category,
        "domain": "financial",
        "notes": f"v1 builder; facts [{fact_ids}]; chunks [{chunk_ids}]. {notes}".strip(),
    }


def main() -> None:
    rng = random.Random(SEED)
    names = company_names()
    facts = load_facts()
    chunks = load_chunk_text()

    rejected_ids: set[str] = set()
    usable: list[dict] = []
    for f in facts:
        floor = SIZE_FLOORS.get(f["metric"])
        if floor is not None and f["value"] < floor:
            rejected_ids.add(f["id"])
            print(f"  floor drop: {f['id']} = {f['value']} (< {floor})")
            continue
        text = chunks.get(f["chunk_id"], "")
        if text and in_chunk(f["value"], text):
            usable.append(f)
        else:
            rejected_ids.add(f["id"])
    print(f"facts usable/total: {len(usable)}/{len(facts)} (rejected {len(rejected_ids)})")

    by_co_metric: dict[tuple, list] = {}
    for f in usable:
        by_co_metric.setdefault((f["ticker"], f["metric"]), []).append(f)
    for v in by_co_metric.values():
        v.sort(key=lambda f: f["fiscal_year"])

    # plausibility screen: size metrics of large caps cannot swing >75% YoY;
    # a fact matching an unrelated stray number in its chunk shows up exactly
    # this way (PEP "total revenue $52M", PFE "total revenue $4,367M").
    implausible: set[tuple] = set()
    for (ticker, metric), series in by_co_metric.items():
        if metric not in PLAUSIBLE_SERIES_METRICS:
            continue
        for a, b in zip(series, series[1:]):
            swing = abs(b["value"] - a["value"]) / max(abs(a["value"]), abs(b["value"]), 1.0)
            if swing > MAX_YOY_SWING:
                implausible.add((ticker, metric))
                print(
                    f"  plausibility drop: {ticker} {metric} swings "
                    f"{a['fiscal_year']}={a['value']} -> {b['fiscal_year']}={b['value']}"
                )
                break
    usable = [f for f in usable if (f["ticker"], f["metric"]) not in implausible]

    seen: set[tuple] = set()
    cases: list[dict] = []

    # ---------- lookup: latest-year headline metrics, company diversity ----------
    common = [
        "Net Income",
        "Total Revenue",
        "Net Sales",
        "Total Assets",
        "Operating Income",
        "Gross Profit",
        "Cash & Cash Equivalents",
    ]
    pool = [f for f in usable if f["metric"] in common]
    rng.shuffle(pool)
    per_company: dict[str, int] = {}
    n_lookup = 0
    for f in pool:
        if n_lookup >= 22:
            break
        if f["fiscal_year"] != max(
            x["fiscal_year"] for x in by_co_metric[(f["ticker"], f["metric"])]
        ):
            continue
        if per_company.get(f["ticker"], 0) >= 2:
            continue
        key = (f["ticker"], f["metric"], f["fiscal_year"])
        if key in seen:
            continue
        seen.add(key)
        per_company[f["ticker"]] = per_company.get(f["ticker"], 0) + 1
        phrase = METRIC_PHRASE[f["metric"]]
        q = f"What was {possessive(names[f['ticker']])} {phrase} for fiscal year {f['fiscal_year']}?"
        cases.append(make_case(f"fin-1{n_lookup + 1:03d}", q, fmt_answer(f), [f], "lookup", "easy"))
        n_lookup += 1

    # ---------- table: deep-table metrics or prior years ----------
    pool = [f for f in usable if f["metric"] in TABLE_METRICS]
    rng.shuffle(pool)
    n_table = 0
    for f in pool:
        if n_table >= 18:
            break
        key = (f["ticker"], f["metric"], f["fiscal_year"])
        if key in seen or per_company.get(f["ticker"], 0) >= 4:
            continue
        seen.add(key)
        per_company[f["ticker"]] = per_company.get(f["ticker"], 0) + 1
        phrase = METRIC_PHRASE[f["metric"]]
        q = (
            f"In its 10-K, what did {names[f['ticker']]} report as {phrase} "
            f"for fiscal year {f['fiscal_year']}?"
        )
        cases.append(make_case(f"fin-2{n_table + 1:03d}", q, fmt_answer(f), [f], "table", "medium"))
        n_table += 1

    # ---------- year-over-year comparison (judge) ----------
    cand = []
    for (ticker, metric), series in by_co_metric.items():
        if len(series) >= 2 and metric != "Diluted EPS":
            cand.append((series[-2], series[-1]))
    rng.shuffle(cand)
    n_yoy = 0
    for f1, f2 in cand:
        if n_yoy >= 10:
            break
        if (f1["ticker"], f1["metric"], f1["fiscal_year"]) in seen:
            continue
        seen.add((f1["ticker"], f1["metric"], f1["fiscal_year"]))
        co = possessive(names[f1["ticker"]])
        phrase = METRIC_PHRASE[f1["metric"]]
        v1, v2 = f1["value"], f2["value"]
        if v1 <= 0 or v2 <= 0:
            # sign-flips and negative bases make percentage ground truth ambiguous
            continue
        pct = (v2 - v1) / abs(v1) * 100.0
        direction = "increased" if pct >= 0 else "decreased"
        answer = (
            f"{fmt_dollars(v2, f2['unit'])} in fiscal year {f2['fiscal_year']}, "
            f"{'up' if pct >= 0 else 'down'} from {fmt_dollars(v1, f1['unit'])} in fiscal year "
            f"{f1['fiscal_year']} — a {abs(pct):.1f}% {direction.replace('increased', 'increase').replace('decreased', 'decrease')}."
        )
        q = f"How did {co} {phrase} change from fiscal year {f1['fiscal_year']} to fiscal year {f2['fiscal_year']}?"
        cases.append(
            make_case(
                f"fin-3{n_yoy + 1:03d}",
                q,
                answer,
                [f1, f2],
                "synthesis",
                "medium",
                ctype="judge",
                rules=rules_for(f1, derived=True),
            )
        )
        n_yoy += 1

    # ---------- cross-company comparison (judge) ----------
    by_metric_year: dict[tuple, list] = {}
    for f in usable:
        if f["metric"] not in (
            "Net Income",
            "Total Revenue",
            "Net Sales",
            "Total Assets",
            "Operating Income",
        ):
            continue
        by_metric_year.setdefault((f["metric"], f["fiscal_year"]), []).append(f)
    pool = [(m, y, fs) for (m, y), fs in by_metric_year.items() if len(fs) >= 3]
    rng.shuffle(pool)
    n_cmp = 0
    for metric, year, fs in pool:
        if n_cmp >= 8:
            break
        fs = sorted(fs, key=lambda f: f["value"], reverse=True)
        a, b = fs[0], fs[-1]
        if a["value"] == b["value"] or (a["ticker"], a["metric"], a["fiscal_year"]) in seen:
            continue
        seen.add((a["ticker"], a["metric"], a["fiscal_year"]))
        phrase = METRIC_PHRASE[metric]
        diff = a["value"] - b["value"]
        answer = (
            f"{names[a['ticker']]} reported higher {phrase}: {fmt_answer(a)} vs "
            f"{possessive(names[b['ticker']])} {fmt_answer(b)} — a difference of "
            f"{fmt_dollars(diff, a['unit'])}."
        )
        q = (
            f"Which company reported higher {phrase} in fiscal year {year}: "
            f"{names[a['ticker']]} or {names[b['ticker']]}? By how much?"
        )
        cases.append(
            make_case(
                f"fin-4{n_cmp + 1:03d}",
                q,
                answer,
                [a, b],
                "synthesis",
                "hard",
                ctype="judge",
                rules=rules_for(a, derived=True),
            )
        )
        n_cmp += 1

    with OUT.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    by_cat: dict[str, int] = {}
    for c in cases:
        by_cat[c["failure_category"]] = by_cat.get(c["failure_category"], 0) + 1
    print(f"\nWrote {len(cases)} candidates -> {OUT}")
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat:12s} {n}")
    print("Rejected facts (figure missing from source chunk):")
    for f in facts:
        if f["id"] in rejected_ids:
            print(f"  {f['id']} = {f['value']} <- {f['chunk_id']}")


if __name__ == "__main__":
    main()
