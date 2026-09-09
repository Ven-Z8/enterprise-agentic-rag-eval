"""Deterministic fact-graph augmentation for clean-scope lookups.

For a question whose scope is a clean (ticker, metric, fiscal year) triple,
this layer resolves the exact figure(s) against the fact graph — extracting
scope from the question text alone, no LLM involved — so the pipeline can put
the facts and their provenance chunks into the synthesis context up front.
That removes retrieval as a single point of failure: a missed chunk can cause
neither a refusal nor a wrong-metric answer (free models do not reliably
self-refuse, so waiting for a refusal before injecting the fact is unreliable).

Conservative by design, because injecting a wrong fact turns a correct
refusal into a hallucination:

- rescue fires only on complete (ticker, metric, year) triples;
- metric scope comes from unambiguous multi-word statement phrases only
  (never bare "revenue", which would match "WhatsApp revenue");
- the question must be fully explained by ticker + metric + year: any
  residual qualifier ("first quarter", "data center", "Waymo") aborts;
- sub-period questions (quarterly, half-year) abort;
- facts flagged as mis-extracted (corpus/graph/excluded_facts.json) are
  never surfaced.

The rescue can therefore only ever inject a real, provenance-backed fact;
whether it answers the question is still the synthesis model's call, and
every figure it cites is re-verified against the source chunk downstream.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ... import config as cfg_mod
from .builder import KNOWN_METRICS
from .query import GraphQueryEngine

_YEAR_RE = re.compile(r"\b(19[6-9]\d|20[0-4]\d)\b")
# FY-prefixed years ("FY2025", "FY 2025", "FY-2025", "FY25", "FY'25"): the
# bare _YEAR_RE cannot see these — between "Y" and the first digit there is
# no word boundary, so "FY2025" never matches \b20\d\d\b. Users write years
# this way constantly; every query-side year check must use _find_years().
_FY_YEAR_RE = re.compile(r"\bfy[\s\-']*(\d{4}|\d{2})\b", re.IGNORECASE)


def _find_years(text: str) -> list[int]:
    """All fiscal years mentioned in query text, longhand or FY-shorthand.

    Returns bare 4-digit years plus FY-prefixed 4- or 2-digit years
    ("FY25" → 2025; 00–69 → 2000s, 70–99 → 1900s). Order of appearance,
    duplicates kept (callers dedupe as needed).
    """
    years = [int(y) for y in _YEAR_RE.findall(text)]
    for m in _FY_YEAR_RE.finditer(text):
        tok = m.group(1)
        if len(tok) == 4:
            years.append(int(tok))
        else:
            yy = int(tok)
            years.append(2000 + yy if yy < 70 else 1900 + yy)
    return years


def _strip_years(text: str) -> str:
    """Remove all year mentions (longhand + FY-shorthand) from query text."""
    return _FY_YEAR_RE.sub(" ", _YEAR_RE.sub(" ", text))


_PERIOD_RE = re.compile(
    r"\bquarter(?:ly)?\b|\bq[1-4]\b|\b(?:first|second|third|fourth) quarter\b"
    r"|\b(?:three|six|nine) months\b|\bhalf[- ]?year\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]*")

# Interrogative scaffolding that carries no topical scope. Anything left
# over after removing companies, metric phrases, years, and these words is a
# qualifier the graph cannot vouch for, so rescue aborts.
_FILLERS = {
    "what",
    "was",
    "were",
    "is",
    "are",
    "the",
    "a",
    "an",
    "of",
    "for",
    "in",
    "on",
    "as",
    "by",
    "or",
    "and",
    "to",
    "from",
    "its",
    "did",
    "do",
    "does",
    "how",
    "much",
    "many",
    "which",
    "company",
    "companies",
    "report",
    "reported",
    "higher",
    "lower",
    "change",
    "changed",
    "increase",
    "decrease",
    "fiscal",
    "year",
    "years",
    "fy",
    "s",
    "10-k",
    "between",
    "over",
    "vs",
    "compared",
    "with",
    "expense",
    "amount",
    # multi-hop scaffolding (ratios, CAGR, trends)
    "compound",
    "annual",
    "growth",
    "rate",
    "cagr",
    "trend",
    "had",
    "have",
    "margin",
    "intensity",
    "percentage",
    "relative",
    "peers",
    "spending",
    "increasing",
    "decreasing",
}

# Ratio metrics: phrase -> numerator metric. The denominator is consolidated
# revenue (Total Revenue, falling back to Net Sales). The ratio itself is a
# derived figure grounded for verification.
_RATIO_NUMERATORS = {
    "net profit margin": "Net Income",
    "net margin": "Net Income",
    "operating margin": "Operating Income",
    "gross margin": "Gross Profit",
    "free cash flow margin": "Free Cash Flow",
    "r&d intensity": "R&D Expense",
    "research and development intensity": "R&D Expense",
}
_REVENUE_DENOMINATORS = ("Total Revenue", "Net Sales")

_CAGR_RE = re.compile(r"\bcagr\b|\bcompound annual growth rate\b", re.IGNORECASE)

# Vague surface terms that map to several distinct statement metrics. A
# question whose only metric reference is one of these is under-specified no
# matter how many years it names, so the right behavior is to clarify.
# Order matters: longest/most specific term first ("earnings per share"
# before "earnings"). Each entry: (term, family wording, candidate canonical
# metrics used only to list the years the corpus actually holds).
_VAGUE_METRIC_TERMS = (
    ("earnings per share", "basic or diluted earnings per share", ("Diluted EPS",)),
    ("eps", "basic or diluted earnings per share", ("Diluted EPS",)),
    (
        "profit margin",
        "gross margin, operating margin, or net profit margin",
        ("Gross Profit", "Operating Income", "Net Income"),
    ),
    (
        "growth rate",
        "the growth of a specific line item (total revenue, net income, earnings per share, ...)",
        ("Total Revenue", "Net Sales", "Net Income"),
    ),
    (
        "earnings",
        "net income, operating income, or earnings per share",
        ("Net Income", "Operating Income", "Diluted EPS"),
    ),
    (
        "cash",
        "cash & cash equivalents, a broader cash-and-investments total, "
        "operating cash flow, or free cash flow",
        ("Cash & Cash Equivalents", "Operating Cash Flow", "Free Cash Flow"),
    ),
)

# Phrases that anchor a question to one specific metric; when any of these is
# present the vague-term clarification abstains ("revenue growth rate" is a
# modifier on a real metric, not a vague reference).
_ANCHOR_PHRASES = sorted(set(KNOWN_METRICS) | set(_RATIO_NUMERATORS), key=len, reverse=True)

# First words of company names that are also common English words; these
# match only via the full company name, never via the first-word fallback.
_GENERIC_FIRST_WORDS = {"home", "bank"}

# Multi-word statement phrases are unambiguous metric references; single-word
# keys ("revenue", "r&d") are too broad for rescue scope.
_RESCUE_PHRASES = sorted(
    (p for p in KNOWN_METRICS if " " in p and KNOWN_METRICS[p] != "Gross Margin"),
    key=len,
    reverse=True,
)

_UNIT_SUFFIX = {"USD_M": " million", "USD_B": " billion", "USD_TH": " thousand"}


@dataclass(frozen=True)
class RescueQuery:
    ticker: str
    metric: str
    fiscal_year: int

    @property
    def fact_id(self) -> str:
        return f"val:{self.ticker}:{self.metric.lower().replace(' ', '_')}:{self.fiscal_year}"


@dataclass
class RescueOutcome:
    queries: list[RescueQuery]
    facts: list[dict[str, Any]]
    chunk_ids: list[str]
    chunks: list[dict[str, Any]]
    facts_block: str
    derived_values: list[float] = field(default_factory=list)


def load_excluded_facts(path: str | Path | None = None) -> frozenset[str]:
    """Fact ids verified wrong by human review; never surfaced by rescue."""
    p = Path(path) if path else cfg_mod.ROOT / "corpus" / "graph" / "excluded_facts.json"
    if not p.exists():
        return frozenset()
    data = json.loads(p.read_text(encoding="utf-8"))
    return frozenset(data.get("excluded", {}))


def load_company_aliases(manifest_path: str | Path | None = None) -> dict[str, list[str]]:
    """Ticker -> matchable *name* aliases from the corpus manifest.

    Ticker symbols are deliberately NOT included here: they are matched
    case-sensitively elsewhere, because a lowercased symbol can collide with an
    ordinary word (the symbol "cost" would otherwise eat "cost of revenue").
    """
    p = Path(manifest_path) if manifest_path else cfg_mod.ROOT / "corpus" / "manifest.csv"
    aliases: dict[str, list[str]] = {}
    with p.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ticker = row["ticker"].strip().upper()
            names = {_normalize(row["company"])}
            first = _normalize(row["company"]).split()[0]
            if len(first) >= 4 and first not in _GENERIC_FIRST_WORDS:
                names.add(first)
            aliases[ticker] = sorted(names, key=len, reverse=True)
    return aliases


def load_company_names(manifest_path: str | Path | None = None) -> dict[str, str]:
    """Ticker -> display company name from the corpus manifest."""
    p = Path(manifest_path) if manifest_path else cfg_mod.ROOT / "corpus" / "manifest.csv"
    names: dict[str, str] = {}
    with p.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            names[row["ticker"].strip().upper()] = row["company"].strip()
    return names


def _normalize(text: str) -> str:
    low = text.lower().replace("&", " and ").replace("'", " ")
    return re.sub(r"[^a-z0-9\s-]", " ", low)


def _format_fact(fact: dict[str, Any]) -> str:
    num = f"{fact['value']:,.2f}".rstrip("0").rstrip(".")
    if fact.get("unit") == "PCT":
        return f"{num}%"
    if str(fact.get("metric", "")).endswith("EPS"):
        return f"${num}"
    return f"${num}{_UNIT_SUFFIX.get(fact.get('unit', ''), '')}"


def _derived_values(facts: list[dict[str, Any]]) -> list[float]:
    """Grounded deltas / percent changes over the rescued facts.

    Change questions (same ticker + metric, two years) yield the absolute
    delta and absolute percent change; comparison questions (same metric +
    year, two tickers) yield the absolute difference. Magnitudes only —
    answers phrase these as positive figures with an up/down qualifier.
    """
    out: list[float] = []
    by_metric: dict[str, list[dict[str, Any]]] = {}
    for f in facts:
        by_metric.setdefault(str(f.get("metric", "")), []).append(f)
    for group in by_metric.values():
        if len(group) < 2:
            continue
        by_ticker: dict[str, list[dict[str, Any]]] = {}
        for f in group:
            by_ticker.setdefault(str(f.get("ticker", "")), []).append(f)
        for tf in by_ticker.values():
            if len(tf) >= 2:
                ordered = sorted(tf, key=lambda x: int(x.get("fiscal_year", 0)))
                for a, b in zip(ordered, ordered[1:]):
                    va, vb = float(a["value"]), float(b["value"])
                    out.append(abs(vb - va))
                    if va:
                        out.append(abs((vb - va) / va * 100.0))
        by_year: dict[str, list[float]] = {}
        for f in group:
            by_year.setdefault(str(f.get("fiscal_year", "")), []).append(float(f["value"]))
        for values in by_year.values():
            if len(values) >= 2:
                for i in range(len(values)):
                    for j in range(i + 1, len(values)):
                        out.append(abs(values[i] - values[j]))
    return out


class GraphRescue:
    """Deterministic rescue lookups against the fact graph."""

    def __init__(
        self,
        engine: GraphQueryEngine,
        chunks_by_id: dict[str, dict[str, Any]],
        company_aliases: dict[str, list[str]] | None = None,
        excluded: frozenset[str] | None = None,
        company_names: dict[str, str] | None = None,
    ) -> None:
        self.engine = engine
        self.chunks_by_id = chunks_by_id
        self.company_aliases = company_aliases or {}
        self.company_names = company_names or {}
        self.excluded = excluded if excluded is not None else load_excluded_facts()
        self._alias_re = sorted(
            ((alias, ticker) for ticker, names in self.company_aliases.items() for alias in names),
            key=lambda pair: len(pair[0]),
            reverse=True,
        )
        # Ticker symbols are matched case-sensitively (uppercase) so they cannot
        # collide with ordinary lowercase words ("cost" in "cost of revenue").
        self._ticker_re = sorted(self.company_aliases.keys(), key=len, reverse=True)

    # ------------------------------------------------------------- extraction

    def _find_tickers(self, query: str) -> tuple[list[str], str]:
        """Return (tickers, text) where text is the normalized remainder after
        stripping every matched company reference."""
        tickers: list[str] = []
        raw = query
        # Ticker symbols first, case-sensitively, and strip them before
        # lowercasing so a matched symbol cannot linger as a residual word.
        for ticker in self._ticker_re:
            if re.search(rf"\b{re.escape(ticker)}\b", raw):
                if ticker not in tickers:
                    tickers.append(ticker)
                raw = re.sub(rf"\b{re.escape(ticker)}\b", " ", raw)
        text = _normalize(raw)
        for alias, ticker in self._alias_re:
            if re.search(rf"\b{re.escape(alias)}\b", text):
                if ticker not in tickers:
                    tickers.append(ticker)
                text = re.sub(rf"\b{re.escape(alias)}\b", " ", text)
        return tickers, text

    def extract_queries(self, query: str) -> list[RescueQuery] | None:
        """Deterministic (ticker, metric, year) scope, or None if the
        question carries any qualifier the graph cannot vouch for."""
        if _PERIOD_RE.search(query):
            return None

        tickers, text = self._find_tickers(query)
        if not tickers:
            return None

        metrics: list[str] = []
        for phrase in _RESCUE_PHRASES:
            if re.search(rf"\b{re.escape(_normalize(phrase))}\b", text):
                canon = KNOWN_METRICS[phrase]
                if canon not in metrics:
                    metrics.append(canon)
                text = re.sub(rf"\b{re.escape(_normalize(phrase))}\b", " ", text)
        if not metrics:
            return None

        years = _find_years(text)
        if not years:
            return None
        years = [int(y) for y in years]
        # trend questions span the full inclusive range between endpoints
        if "trend" in query.lower() and len(years) >= 2:
            years = list(range(min(years), max(years) + 1))
        text = _strip_years(text)

        residual = [t for t in _TOKEN_RE.findall(text) if t not in _FILLERS]
        if residual:
            return None

        return [
            RescueQuery(t, m, y) for t in tickers for m in metrics for y in dict.fromkeys(years)
        ]

    # --------------------------------------------------------------- multi-hop

    def _fact_id(self, row: dict[str, Any]) -> str:
        return f"val:{row['ticker']}:{row['metric'].lower().replace(' ', '_')}:{row['fiscal_year']}"

    def _excluded_fact(self, row: dict[str, Any]) -> bool:
        return self._fact_id(row) in self.excluded

    def _outcome(
        self,
        facts: list[dict[str, Any]],
        queries: list,
        derived: list[float],
        derived_lines: list[str] | None = None,
    ) -> RescueOutcome | None:
        chunks = [
            self.chunks_by_id[f["chunk_id"]]
            for f in facts
            if f.get("chunk_id") in self.chunks_by_id
        ]
        if not chunks:
            return None
        chunk_ids = [c["id"] for c in chunks]
        lines = [
            f"- {f['ticker']} {f['metric']} FY{f['fiscal_year']}: "
            f"{_format_fact(f)} (source chunk: {f['chunk_id']})"
            for f in facts
        ]
        # Derived lines (ratios, CAGR) are computed deterministically from the
        # listed input facts; naming them gives the model the exact figure to
        # state instead of re-deriving (and rounding) it.
        lines.extend(derived_lines or [])
        block = (
            "[GRAPH_FACTS — deterministic extractions from 10-K tables]\n"
            "Each line carries the source chunk ID of the table it was parsed "
            "from. If you use one of these figures, cite that source chunk ID, "
            "not this block.\n" + "\n".join(lines)
        )
        return RescueOutcome(
            queries=queries,
            facts=facts,
            chunk_ids=chunk_ids,
            chunks=chunks,
            facts_block=block,
            derived_values=derived,
        )

    def _rescue_ratios(self, query: str) -> RescueOutcome | None:
        """Margin/intensity ratios (numerator over consolidated revenue),
        including cross-company comparisons and year-over-year changes."""
        query = re.sub(r"\([^)]*\)", " ", query)  # drop definitional asides
        if _PERIOD_RE.search(query):
            return None
        norm = _normalize(query)
        ratio_phrase = None
        for phrase in sorted(_RATIO_NUMERATORS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(_normalize(phrase))}\b", norm):
                ratio_phrase = phrase
                break
        if ratio_phrase is None:
            return None
        num_metric = _RATIO_NUMERATORS[ratio_phrase]

        tickers, text = self._find_tickers(query)
        if not tickers:
            return None
        text = re.sub(rf"\b{re.escape(_normalize(ratio_phrase))}\b", " ", text)
        years = list(dict.fromkeys(_find_years(text)))
        if not years:
            return None
        text = _strip_years(text)
        if [t for t in _TOKEN_RE.findall(text) if t not in _FILLERS]:
            return None

        facts: list[dict[str, Any]] = []
        ratio_vals: list[float] = []
        ratio_lines: list[str] = []
        seen: set[tuple] = set()
        for t in tickers:
            for y in years:
                num = self.engine.get_metric_value(t, num_metric, y)
                den = None
                for dm in _REVENUE_DENOMINATORS:
                    den = self.engine.get_metric_value(t, dm, y)
                    if den is not None:
                        break
                if num is None or den is None or not den.get("value"):
                    return None
                if self._excluded_fact(num) or self._excluded_fact(den):
                    return None
                for f in (num, den):
                    key = (f["ticker"], f["metric"], str(f["fiscal_year"]))
                    if key not in seen:
                        seen.add(key)
                        facts.append(f)
                ratio = num["value"] / den["value"] * 100
                ratio_vals.append(ratio)
                ratio_lines.append(
                    f"- {t} {ratio_phrase} FY{y}: {ratio:.1f}% (derived: "
                    f"{num['metric']} ÷ {den['metric']}; source chunks: "
                    f"{num['chunk_id']}, {den['chunk_id']})"
                )
        if not facts:
            return None

        # ground the ratio(s) and any change/comparison gap between them
        derived = list(ratio_vals)
        for i in range(len(ratio_vals)):
            for j in range(i + 1, len(ratio_vals)):
                gap = abs(ratio_vals[i] - ratio_vals[j])
                derived.append(gap)
                derived.append(round(gap, 1))  # match 1-decimal phrasing
        queries = [RescueQuery(f["ticker"], f["metric"], int(f["fiscal_year"])) for f in facts]
        return self._outcome(facts, queries, derived, derived_lines=ratio_lines)

    def _rescue_cagr(self, query: str) -> RescueOutcome | None:
        """Compound annual growth rate of one metric over a year span."""
        if not _CAGR_RE.search(query) or _PERIOD_RE.search(query):
            return None
        tickers, text = self._find_tickers(query)
        if len(tickers) != 1:
            return None
        ticker = tickers[0]
        text = _CAGR_RE.sub(" ", text)
        metrics: list[str] = []
        for phrase in _RESCUE_PHRASES:
            if re.search(rf"\b{re.escape(_normalize(phrase))}\b", text):
                canon = KNOWN_METRICS[phrase]
                if canon not in metrics:
                    metrics.append(canon)
                text = re.sub(rf"\b{re.escape(_normalize(phrase))}\b", " ", text)
        if len(metrics) != 1:
            return None
        metric = metrics[0]
        years = sorted(set(_find_years(text)))
        if len(years) < 2:
            return None
        text = _strip_years(text)
        if [t for t in _TOKEN_RE.findall(text) if t not in _FILLERS]:
            return None
        y0, y1 = years[0], years[-1]
        v0 = self.engine.get_metric_value(ticker, metric, y0)
        v1 = self.engine.get_metric_value(ticker, metric, y1)
        if v0 is None or v1 is None or not v0.get("value") or v0["value"] <= 0:
            return None
        if self._excluded_fact(v0) or self._excluded_fact(v1):
            return None
        cagr = ((v1["value"] / v0["value"]) ** (1 / (y1 - y0)) - 1) * 100
        facts = [v0, v1]
        queries = [RescueQuery(ticker, metric, y0), RescueQuery(ticker, metric, y1)]
        cagr_line = (
            f"- {ticker} {metric} CAGR FY{y0}→FY{y1}: {cagr:.1f}% per year "
            f"(derived: compound growth between the two endpoint figures; "
            f"source chunks: {v0['chunk_id']}, {v1['chunk_id']})"
        )
        return self._outcome(facts, queries, [cagr, round(cagr, 1)], derived_lines=[cagr_line])

    # ---------------------------------------------------------------- lookup

    def rescue(self, query: str) -> RescueOutcome | None:
        """Facts answering the question's scope, or None when rescue abstains."""
        for handler in (self._rescue_ratios, self._rescue_cagr):
            out = handler(query)
            if out is not None:
                return out

        queries = self.extract_queries(query)
        if not queries:
            return None

        facts: list[dict[str, Any]] = []
        seen: set[str] = set()
        for q in queries:
            if q.fact_id in seen or q.fact_id in self.excluded:
                continue
            row = self.engine.get_metric_value(q.ticker, q.metric, q.fiscal_year)
            if row is None:
                continue
            seen.add(q.fact_id)
            facts.append(row)
        if not facts:
            return None

        return self._outcome(facts, queries, _derived_values(facts))

    # -------------------------------------------------------- clarification

    _CHANGE_INTENT_RE = re.compile(
        r"\b(change|changed|trend|grow|grew|growth|increasing|decreasing|"
        r"increase|decrease|rise|fall|rose|fell|cagr)\b",
        re.IGNORECASE,
    )

    # "relative to its peers" leaves the comparison set undefined — the
    # clarification must ask for it as well as the missing fiscal year.
    _PEERS_RE = re.compile(
        r"\b(?:relative|compared|vs\.?|versus)\s+(?:to\s+)?(?:its\s+|their\s+|the\s+)?"
        r"peers?\b|\bpeer\s+(?:group|companies|comparison)\b",
        re.IGNORECASE,
    )

    def missing_year_clarification(self, query: str) -> str | None:
        """A deterministic clarification when a single company + a recognized
        metric are given but no fiscal year is pinned and the corpus holds
        several years — the right enterprise behavior is to ask, not guess.

        Returns the clarification text, or None when it does not apply.
        """
        if _PERIOD_RE.search(query):
            return None
        tickers, text = self._find_tickers(query)
        if len(tickers) != 1:
            return None
        ticker = tickers[0]
        if _find_years(text):
            return None  # a year is already pinned (longhand or FY-shorthand)
        metric = None
        for phrase in _RESCUE_PHRASES:
            if re.search(rf"\b{re.escape(_normalize(phrase))}\b", text):
                metric = KNOWN_METRICS[phrase]
                break
        if metric is None:
            for phrase in (
                "total revenue",
                "net revenue",
                "revenue",
                "operating profit",
                "operating income",
                "net sales",
                "net income",
                "r&d",
            ):
                if phrase in KNOWN_METRICS and re.search(rf"\b{re.escape(phrase)}\b", text):
                    metric = KNOWN_METRICS[phrase]
                    break
        if metric is None:
            return None
        hist = self.engine.get_metric_history(ticker, metric)
        years = sorted(
            {int(h["fiscal_year"]) for h in hist if str(h.get("fiscal_year", "")).isdigit()}
        )
        if len(years) < 2 and metric in ("Total Revenue", "Net Sales"):
            alt = "Net Sales" if metric == "Total Revenue" else "Total Revenue"
            hist_alt = self.engine.get_metric_history(ticker, alt)
            years_alt = sorted(
                {int(h["fiscal_year"]) for h in hist_alt if str(h.get("fiscal_year", "")).isdigit()}
            )
            if len(years_alt) >= 2:
                metric = alt
                years = years_alt
        if len(years) < 2:
            return None
        name = self.company_names.get(ticker, ticker)
        span = ", ".join(f"FY{y}" for y in years)
        metric_l = metric.lower()
        if self._CHANGE_INTENT_RE.search(text):
            msg = (
                f"{name} reports {metric_l} for {len(years)} fiscal years in "
                f"the corpus ({span}), and the question does not specify a "
                f"period. Between which fiscal years would you like the change "
                f"in {metric_l}?"
            )
        else:
            msg = (
                f"{name} reports {metric_l} for {len(years)} fiscal years in the "
                f"corpus ({span}), and the question does not specify one. Which "
                f"fiscal year's {metric_l} would you like?"
            )
        if self._PEERS_RE.search(query):
            msg += (
                " Also, 'relative to its peers' is unspecified: which peer "
                "companies would you like it compared against?"
            )
        return msg

    def vague_metric_clarification(self, query: str) -> str | None:
        """A deterministic clarification when the question's only metric
        reference is a vague term ("earnings", "cash", "growth rate", ...)
        that maps to several distinct statement metrics — under-specified
        even when a fiscal year is pinned.

        Returns the clarification text, or None when it does not apply.
        """
        if _PERIOD_RE.search(query) or _CAGR_RE.search(query):
            return None
        norm = _normalize(query)
        for phrase in _ANCHOR_PHRASES:
            if re.search(rf"\b{re.escape(_normalize(phrase))}\b", norm):
                return None  # the question anchors a specific metric
        tickers, text = self._find_tickers(query)
        years = sorted(set(_find_years(text)))
        for term, family, candidates in _VAGUE_METRIC_TERMS:
            if not re.search(rf"\b{re.escape(term)}\b", text):
                continue
            subject = (
                self.company_names.get(tickers[0], tickers[0])
                if len(tickers) == 1
                else "the company"
            )
            if years:
                year_txt = (
                    f"fiscal year {years[0]}"
                    if len(years) == 1
                    else f"fiscal years {', '.join(map(str, years))}"
                )
                return (
                    f"'{term.capitalize()}' is ambiguous: it could mean "
                    f"{family}. Which measure of {subject}'s {term} for "
                    f"{year_txt} would you like?"
                )
            span_years: set[int] = set()
            if len(tickers) == 1:
                for m in candidates:
                    span_years |= {
                        int(h["fiscal_year"])
                        for h in self.engine.get_metric_history(tickers[0], m)
                        if str(h.get("fiscal_year", "")).isdigit()
                    }
            if len(span_years) >= 2:
                span = ", ".join(f"FY{y}" for y in sorted(span_years))
                return (
                    f"{subject} reports figures that could match '{term}' "
                    f"({family}) for {len(span_years)} fiscal years in the "
                    f"corpus ({span}), and the question specifies neither the "
                    f"exact measure nor the fiscal year. Which measure — and "
                    f"which fiscal year — would you like?"
                )
            return (
                f"'{term.capitalize()}' is ambiguous: it could mean {family}, "
                f"and the question specifies neither the exact measure nor a "
                f"fiscal year. Which measure — and which fiscal year — would "
                f"you like?"
            )
        return None

    def no_company_clarification(self, query: str) -> str | None:
        """A deterministic clarification when the question names a recognized
        metric but no company and no fiscal year — a corpus-wide guess (or a
        cross-company ranking over misaligned fiscal years) is never the right
        enterprise answer.

        Returns the clarification text, or None when it does not apply.
        """
        if _PERIOD_RE.search(query):
            return None
        tickers, text = self._find_tickers(query)
        if tickers:
            return None
        if _find_years(text):
            return None
        metric = None
        for phrase in _RESCUE_PHRASES:
            if re.search(rf"\b{re.escape(_normalize(phrase))}\b", text):
                metric = KNOWN_METRICS[phrase]
                break
        if metric is None:
            for phrase in (
                "total revenue",
                "net revenue",
                "revenue",
                "operating profit",
                "operating income",
                "net sales",
                "net income",
                "gross profit",
                "r&d",
            ):
                if phrase in KNOWN_METRICS and re.search(rf"\b{re.escape(phrase)}\b", text):
                    metric = KNOWN_METRICS[phrase]
                    break
        if metric is None:
            return None
        n = len(self.company_names)
        return (
            f"The corpus holds filings for {n} companies, each reporting "
            f"several fiscal years, and the question names neither a company "
            f"nor a fiscal year. Which company's {metric.lower()} would you "
            f"like — and for which fiscal year?"
        )

    def clarification(self, query: str) -> str | None:
        """Any deterministic clarifying question for an under-specified
        query, or None when the question is in scope for synthesis."""
        for handler in (
            self.missing_year_clarification,
            self.vague_metric_clarification,
            self.no_company_clarification,
        ):
            out = handler(query)
            if out is not None:
                return out
        return None
