"""Enterprise golden-set builder: multi-hop questions with provable answers.

Stage-4 enterprise evaluation. Unlike golden_set_v1 (single-fact lookups),
these questions require joining 2+ graph facts and deriving a new figure —
the kind of analysis an enterprise reviewer actually asks for:

  - margin / intensity ratios     (net income / revenue, R&D / revenue, ...)
  - CAGR over a fiscal-year span  ((end/start)^(1/n) - 1)
  - cross-company ratio comparison
  - year-over-year ratio change

Provenance discipline matches golden_set_v1: every *base* figure is checked
against its source chunk (in_chunk) before the case is emitted; the derived
figure is computed deterministically from those verified base figures. The
audit therefore reports these as partially_verified (base figures found, the
computed figure is arithmetic over them) — the same accepted pattern as the
v1 synthesis/comparison cases.

Usage: uv run python scripts/build_golden_enterprise_v1.py [--dry-run]
Emits the enterprise set into ../p1-eval-harness/data/domain_a_financial/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_golden_v1 as v1  # noqa: E402  (audited helpers + fact filters)

# Canonical golden data lives in the sibling p1-eval-harness project.
P1_GOLDEN = ROOT.parent / "p1-eval-harness" / "data" / "domain_a_financial"
OUT = P1_GOLDEN / "golden_set_enterprise_v1.jsonl"

# metric used as the denominator for revenue-based ratios
REVENUE_METRICS = ("Total Revenue", "Net Sales")


class FactBook:
    """(ticker, metric, fiscal_year) -> fact, restricted to audited facts."""

    def __init__(self):
        self.facts = v1.load_facts()
        self.chunks = v1.load_chunk_text()
        self.names = v1.company_names()
        self._by_key = {}
        for f in self.facts:
            self._by_key[(f["ticker"], f["metric"], str(f["fiscal_year"]))] = f

    def get(self, ticker, metric, year):
        f = self._by_key.get((ticker, metric, str(year)))
        if f is None:
            return None
        # base figure must actually appear in its source chunk (audit rule)
        text = self.chunks.get(f["chunk_id"], "")
        if not text or not v1.in_chunk(f["value"], text):
            return None
        return f

    def revenue(self, ticker, year):
        """The consolidated revenue fact for (ticker, year), if any."""
        for m in REVENUE_METRICS:
            f = self.get(ticker, m, year)
            if f is not None:
                return f
        return None

    def years(self, ticker, metric):
        ys = sorted(
            int(f["fiscal_year"])
            for f in self.facts
            if f["ticker"] == ticker and f["metric"] == metric
        )
        return ys


def fmt_pct(x, nd=1):
    return f"{x:.{nd}f}%"


def fmt_m(v):
    return v1.fmt_dollars(v, "USD_M")


def enterprise_case(cid, question, answer, facts, category, difficulty, ctype, rules, notes=""):
    cits = sorted({v1.citation_of(f) for f in facts})
    fact_ids = ", ".join(f["id"] for f in facts)
    return {
        "id": cid,
        "input": question,
        "expected": {"answer": answer, "citations": cits, "type": ctype},
        "variation_rules": rules,
        "difficulty": difficulty,
        "failure_category": category,
        "domain": "financial",
        "notes": f"enterprise builder; facts [{fact_ids}]. {notes}".strip(),
    }


DERIVED_RULES = ["numeric_tolerance:1%", "unit_equivalence"]


# ---------------------------------------------------------------- builders


def margin_case(fb, cid, ticker, year, num_metric, margin_name, num_phrase):
    """net income / revenue -> '<margin_name>' as a percentage."""
    num = fb.get(ticker, num_metric, year)
    den = fb.revenue(ticker, year)
    if num is None or den is None or den["value"] == 0:
        return None
    pct = num["value"] / den["value"] * 100
    q = f"What was {v1.possessive(fb.names[ticker])} {margin_name} in fiscal year {year}?"
    a = (
        f"{fmt_pct(pct)} — {num_phrase} of {fmt_m(num['value'])} divided by "
        f"revenue of {fmt_m(den['value'])}."
    )
    return enterprise_case(
        cid,
        q,
        a,
        [num, den],
        "synthesis",
        "hard",
        "exact",
        DERIVED_RULES,
        notes=f"{margin_name} = {num['metric']} / {den['metric']} = {pct:.2f}%",
    )


def cagr_case(fb, cid, ticker, metric, y0, y1):
    v0, v1f = fb.get(ticker, metric, y0), fb.get(ticker, metric, y1)
    if v0 is None or v1f is None or v0["value"] <= 0:
        return None
    n = y1 - y0
    cagr = ((v1f["value"] / v0["value"]) ** (1 / n) - 1) * 100
    phrase = v1.METRIC_PHRASE[metric]
    q = (
        f"What was the compound annual growth rate (CAGR) of "
        f"{v1.possessive(fb.names[ticker])} {phrase} from fiscal year {y0} "
        f"to fiscal year {y1}?"
    )
    a = (
        f"{fmt_pct(cagr)} per year — growing from {fmt_m(v0['value'])} in "
        f"fiscal year {y0} to {fmt_m(v1f['value'])} in fiscal year {y1}."
    )
    return enterprise_case(
        cid,
        q,
        a,
        [v0, v1f],
        "synthesis",
        "hard",
        "exact",
        DERIVED_RULES,
        notes=f"CAGR {y0}->{y1} = ({v1f['value']}/{v0['value']})^(1/{n})-1",
    )


def compare_margin_case(fb, cid, t1, t2, year, num_metric, margin_name):
    pairs = []
    for t in (t1, t2):
        num = fb.get(t, num_metric, year)
        den = fb.revenue(t, year)
        if num is None or den is None or den["value"] == 0:
            return None
        pairs.append((t, num, den, num["value"] / den["value"] * 100))
    (wa, wn, wd, wp), (la, ln, ld, lp) = sorted(pairs, key=lambda p: -p[3])
    nphrase = v1.METRIC_PHRASE[num_metric]
    q = (
        f"Which company had the higher {margin_name} in fiscal year {year}: "
        f"{fb.names[t1]} or {fb.names[t2]}?"
    )
    a = (
        f"{fb.names[wa]} had the higher {margin_name}: {fmt_pct(wp)} versus "
        f"{fmt_pct(lp)} for {fb.names[la]}. "
        f"({fb.names[wa]}: {nphrase} {fmt_m(wn['value'])} on revenue "
        f"{fmt_m(wd['value'])}; {fb.names[la]}: {nphrase} {fmt_m(ln['value'])} "
        f"on revenue {fmt_m(ld['value'])}.)"
    )
    return enterprise_case(
        cid,
        q,
        a,
        [wn, wd, ln, ld],
        "synthesis",
        "hard",
        "judge",
        DERIVED_RULES,
        notes=f"{margin_name}: {wa}={wp:.2f}% vs {la}={lp:.2f}%",
    )


def margin_change_case(fb, cid, ticker, num_metric, margin_name, y0, y1):
    r0, r1 = fb.revenue(ticker, y0), fb.revenue(ticker, y1)
    n0, n1 = fb.get(ticker, num_metric, y0), fb.get(ticker, num_metric, y1)
    if None in (r0, r1, n0, n1) or r0["value"] == 0 or r1["value"] == 0:
        return None
    p0 = n0["value"] / r0["value"] * 100
    p1 = n1["value"] / r1["value"] * 100
    delta = p1 - p0
    direction = "increased" if delta > 0 else "decreased"
    q = (
        f"How did {v1.possessive(fb.names[ticker])} {margin_name} change "
        f"from fiscal year {y0} to fiscal year {y1}?"
    )
    a = (
        f"It {direction} from {fmt_pct(p0)} in fiscal year {y0} to "
        f"{fmt_pct(p1)} in fiscal year {y1} ({delta:+.1f} percentage points). "
        f"(Fiscal {y0}: {fmt_m(n0['value'])} on revenue {fmt_m(r0['value'])}; "
        f"fiscal {y1}: {fmt_m(n1['value'])} on revenue {fmt_m(r1['value'])}.)"
    )
    return enterprise_case(
        cid,
        q,
        a,
        [n0, r0, n1, r1],
        "synthesis",
        "hard",
        "judge",
        DERIVED_RULES,
        notes=f"{margin_name} {y0}->{y1}: {p0:.2f}% -> {p1:.2f}%",
    )


def rd_intensity_case(fb, cid, ticker, year):
    rd = fb.get(ticker, "R&D Expense", year)
    rev = fb.revenue(ticker, year)
    if rd is None or rev is None or rev["value"] == 0:
        return None
    pct = rd["value"] / rev["value"] * 100
    q = (
        f"What was {v1.possessive(fb.names[ticker])} R&D intensity "
        f"(research and development expense as a percentage of revenue) "
        f"in fiscal year {year}?"
    )
    a = f"{fmt_pct(pct)} — R&D expense of {fmt_m(rd['value'])} on revenue of {fmt_m(rev['value'])}."
    return enterprise_case(
        cid,
        q,
        a,
        [rd, rev],
        "synthesis",
        "hard",
        "exact",
        DERIVED_RULES,
        notes=f"R&D intensity = {rd['value']}/{rev['value']} = {pct:.2f}%",
    )


def trend_case(fb, cid, ticker, metric, years):
    """List a metric across >=3 fiscal years (multi-year series reading)."""
    facts = [fb.get(ticker, metric, y) for y in years]
    if any(f is None for f in facts):
        return None
    phrase = v1.METRIC_PHRASE[metric]
    parts = ", ".join(f"{fmt_m(f['value'])} in fiscal year {f['fiscal_year']}" for f in facts)
    first, last = facts[0]["value"], facts[-1]["value"]
    direction = "an upward" if last > first else ("a downward" if last < first else "a flat")
    q = (
        f"What was the trend in {v1.possessive(fb.names[ticker])} {phrase} "
        f"from fiscal year {years[0]} to fiscal year {years[-1]}?"
    )
    a = f"{phrase.capitalize()} showed {direction} trend: {parts}."
    return enterprise_case(
        cid,
        q,
        a,
        facts,
        "synthesis",
        "hard",
        "judge",
        DERIVED_RULES,
        notes=f"{metric} series {years}",
    )


def build(dry_run: bool) -> None:
    fb = FactBook()
    cases = []
    n = [0]  # mutable counter for stable ids

    def add(case):
        if case is None:
            return
        n[0] += 1
        case["id"] = f"ent-1{n[0]:03d}"
        cases.append(case)

    # ---- Batch 1: one of each flagship multi-hop type (review first) ----
    add(margin_case(fb, "", "MSFT", 2025, "Net Income", "net profit margin", "net income"))
    add(cagr_case(fb, "", "AAPL", "Net Sales", 2023, 2025))
    add(rd_intensity_case(fb, "", "GOOGL", 2025))
    add(compare_margin_case(fb, "", "MSFT", "META", 2025, "Operating Income", "operating margin"))
    add(margin_change_case(fb, "", "MSFT", "Net Income", "net profit margin", 2024, 2025))
    if dry_run:
        print(f"DRY RUN (batch 1 only): {len(cases)} cases")
        for c in cases:
            print(f"  {c['id']} [{c['expected']['type']}] {c['input']}")
            print(f"       -> {c['expected']['answer']}")
        return

    def latest(ticker, metric):
        ys = fb.years(ticker, metric)
        return ys[-1] if ys else None

    # ---- net profit margin (net-income-whitelisted tickers) ----
    for t in ("GOOGL", "AMZN", "NVDA", "HD"):
        y = latest(t, "Net Income")
        if y:
            add(margin_case(fb, "", t, y, "Net Income", "net profit margin", "net income"))

    # ---- operating margin ----
    for t in ("META", "TSLA", "WMT"):
        y = latest(t, "Operating Income")
        if y and fb.revenue(t, y):
            add(
                margin_case(
                    fb, "", t, y, "Operating Income", "operating margin", "operating income"
                )
            )

    # ---- gross margin ----
    for t in ("HD", "WMT", "TSLA", "PEP"):
        y = latest(t, "Gross Profit")
        if y and fb.revenue(t, y):
            add(margin_case(fb, "", t, y, "Gross Profit", "gross margin", "gross profit"))

    # ---- free-cash-flow margin ----
    for t in ("META", "CVX"):
        y = latest(t, "Free Cash Flow")
        if y and fb.revenue(t, y):
            add(
                margin_case(
                    fb, "", t, y, "Free Cash Flow", "free cash flow margin", "free cash flow"
                )
            )

    # ---- R&D intensity ----
    for t in ("NVDA", "TSLA"):
        y = latest(t, "R&D Expense")
        if y:
            add(rd_intensity_case(fb, "", t, y))

    # ---- CAGR over the available span ----
    cagr_specs = []
    for t in ("MSFT", "NVDA", "AMZN", "META", "COST", "WMT", "GOOGL", "KO", "HD", "JPM"):
        for m in ("Total Revenue", "Net Sales"):
            ys = fb.years(t, m)
            if len(ys) >= 3:
                cagr_specs.append((t, m, ys[0], ys[-1]))
                break
    for t, m, y0, y1 in cagr_specs[:5]:
        add(cagr_case(fb, "", t, m, y0, y1))

    # ---- cross-company ratio comparisons ----
    compare_specs = [
        ("GOOGL", "MSFT", 2025, "Net Income", "net profit margin"),
        ("META", "GOOGL", 2025, "Operating Income", "operating margin"),
        ("KO", "PEP", 2025, "Gross Profit", "gross margin"),
        ("META", "AMZN", 2025, "Free Cash Flow", "free cash flow margin"),
    ]
    for t1, t2, y, nm, mn in compare_specs:
        add(compare_margin_case(fb, "", t1, t2, y, nm, mn))

    # ---- year-over-year ratio change ----
    change_specs = [
        ("AAPL", "Net Income", "net profit margin", 2023, 2025),
        ("META", "Operating Income", "operating margin", 2023, 2025),
        ("HD", "Gross Profit", "gross margin", 2024, 2026),
    ]
    for t, nm, mn, y0, y1 in change_specs:
        add(margin_change_case(fb, "", t, nm, mn, y0, y1))

    # ---- multi-year trends ----
    trend_specs = []
    for t in ("MSFT", "AMZN", "META", "GOOGL", "NVDA", "WMT"):
        for m in ("Total Revenue", "Net Sales", "Net Income"):
            ys = fb.years(t, m)
            if len(ys) >= 3:
                trend_specs.append((t, m, ys[:3]))
                break
    for t, m, ys in trend_specs[:3]:
        add(trend_case(fb, "", t, m, ys))

    # ---- enterprise unanswerables: must refuse, state why ----
    unanswerables = [
        (
            "What was Salesforce's total revenue for fiscal year 2025?",
            "Salesforce is not one of the 25 filings in the corpus. Correct "
            "behavior: refuse, note the company is out of corpus scope.",
        ),
        (
            "What was Oracle's net income for fiscal year 2025?",
            "Oracle is not in the corpus. Correct behavior: refuse.",
        ),
        (
            "What was Microsoft's total revenue for fiscal year 2019?",
            "MSFT 10-K in the corpus reports FY2023-2025 only; 2019 predates "
            "the corpus. Correct behavior: refuse, state the reported range.",
        ),
        (
            "What was NVIDIA's net income for fiscal year 2028?",
            "FY2028 is in the future; NVDA 10-K reports FY2024-2026. Correct behavior: refuse.",
        ),
        (
            "What was Apple's net income for the second quarter of fiscal year 2025?",
            "The corpus holds annual 10-K statements only; quarterly net income "
            "is not available. Correct behavior: refuse, note annual-only scope.",
        ),
        (
            "What was Meta Platforms' adjusted EBITDA for fiscal year 2025?",
            "Adjusted EBITDA is a non-GAAP measure not reported in the GAAP "
            "financial statements. Correct behavior: refuse (or offer GAAP "
            "operating income instead).",
        ),
        (
            "What was Berkshire Hathaway's net income for fiscal year 2025?",
            "Berkshire Hathaway is not in the corpus. Correct behavior: refuse.",
        ),
        (
            "What was Walmart's total revenue for fiscal year 2027?",
            "FY2027 is in the future; WMT 10-K reports FY2024-2026. Correct behavior: refuse.",
        ),
    ]
    for q, note in unanswerables:
        add(
            {
                "id": "",
                "input": q,
                "expected": {"answer": None, "citations": [], "type": "exact"},
                "variation_rules": [],
                "difficulty": "medium",
                "failure_category": "unanswerable",
                "domain": "financial",
                "notes": f"enterprise builder; {note}",
            }
        )

    # ---- enterprise ambiguous: must clarify, not guess ----
    ambiguous = [
        (
            "What was Microsoft's profit margin in fiscal year 2025?",
            "'Profit margin' is undefined: gross, operating, or net? Correct "
            "behavior: ask which margin (or present all three).",
        ),
        (
            "What was Amazon's earnings in fiscal year 2025?",
            "'Earnings' is ambiguous: net income, operating income, or EPS? "
            "Correct behavior: ask which measure.",
        ),
        (
            "How much cash does Apple have?",
            "No fiscal year, and 'cash' is ambiguous (cash & equivalents vs "
            "including short-term investments). Correct behavior: clarify.",
        ),
        (
            "What was NVIDIA's growth rate in fiscal year 2026?",
            "Growth of which metric (revenue, net income, EPS) and vs which "
            "prior year? Correct behavior: clarify.",
        ),
        (
            "Which company is more profitable: Microsoft or Apple?",
            "'More profitable' is undefined: absolute net income, net margin, "
            "or return on equity? Correct behavior: clarify the measure.",
        ),
        (
            "What was Meta Platforms' free cash flow margin relative to its peers?",
            "Which peers, and which fiscal year? Correct behavior: clarify the "
            "comparison set and year.",
        ),
        (
            "Is Tesla's research and development spending increasing?",
            "Over what period, and nominal dollars or as a % of revenue? "
            "Correct behavior: clarify the window and basis.",
        ),
    ]
    for q, note in ambiguous:
        add(
            {
                "id": "",
                "input": q,
                "expected": {"answer": None, "citations": [], "type": "judge"},
                "variation_rules": [],
                "difficulty": "medium",
                "failure_category": "ambiguous",
                "domain": "financial",
                "notes": f"enterprise builder; {note}",
            }
        )

    # write
    by_cat = {}
    for c in cases:
        by_cat[c["failure_category"]] = by_cat.get(c["failure_category"], 0) + 1
    with OUT.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"Wrote {len(cases)} enterprise cases -> {OUT}")
    for cat, k in sorted(by_cat.items()):
        print(f"  {cat:12s} {k}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    build(args.dry_run)
