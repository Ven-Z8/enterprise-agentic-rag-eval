"""Build the FinanceBench full-retrieval corpus.

Downloads the filings that FinanceBench's 150 questions reference, parses and
chunks them with the ragfilings pipeline, and builds a dedicated embedding
index — so the benchmark can be run in retrieval mode (find the evidence
yourself, then reason) instead of reasoning-over-evidence.

Resolution order per document:
  10-K / 10-Q / 8-K -> SEC EDGAR primary document, matched by form + fiscal
                       period parsed from doc_name (works even when the
                       dataset's corporate-IR link is dead)
  Earnings releases -> the dataset's own doc_link (not on EDGAR)

Usage: uv run python scripts/build_financebench_corpus.py
Writes data/financebench/{docs,chunks,index}/ + corpus_manifest.json
(all gitignored).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parent / "src"))
sys.path.insert(0, str(SCRIPTS.parent.parent / "p3-rag-filings" / "src"))

from bs4 import BeautifulSoup  # noqa: E402
from financebench_common import (  # noqa: E402
    FB_DIR,
    load_financebench,
    parse_doc_name,
    questions_per_doc,
    unique_docs,
)
from ragfilings import ingestion, retrieval  # noqa: E402

USER_AGENT = "Venkis Portfolio Research venkatesh.gtd1@gmail.com"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)

DOCS_DIR = FB_DIR / "docs"
CHUNKS_DIR = FB_DIR / "chunks"
INDEX_DIR = FB_DIR / "index"
MANIFEST = FB_DIR / "corpus_manifest.json"

# dataset `company` field -> ticker (all 32 FinanceBench companies)
TICKERS = {
    "3M": "MMM",
    "AES Corporation": "AES",
    "AMD": "AMD",
    "Activision Blizzard": "ATVI",
    "Adobe": "ADBE",
    "Amazon": "AMZN",
    "Amcor": "AMCR",
    "American Express": "AXP",
    "American Water Works": "AWK",
    "Best Buy": "BBY",
    "Block": "SQ",
    "Boeing": "BA",
    "CVS Health": "CVS",
    "Coca-Cola": "KO",
    "Corning": "GLW",
    "Costco": "COST",
    "Foot Locker": "FL",
    "General Mills": "GIS",
    "JPMorgan": "JPM",
    "Johnson & Johnson": "JNJ",
    "Kraft Heinz": "KHC",
    "Lockheed Martin": "LMT",
    "MGM Resorts": "MGM",
    "Microsoft": "MSFT",
    "Netflix": "NFLX",
    "Nike": "NKE",
    "Paypal": "PYPL",
    "PepsiCo": "PEP",
    "Pfizer": "PFE",
    "Ulta Beauty": "ULTA",
    "Verizon": "VZ",
    "Walmart": "WMT",
}

# tickers no longer in SEC's live company_tickers.json (acquired / renamed)
CIK_FALLBACK = {
    "ATVI": 718877,  # Activision Blizzard (acquired by Microsoft, 2023)
    "SQ": 1512673,  # Block Inc (renamed to XYZ in 2025)
    "FL": 850209,  # Foot Locker (acquired by Dick's Sporting Goods, 2025)
}

_cik_cache: dict[str, int] | None = None
_submissions_cache: dict[int, list[dict]] = {}
_fye_cache: dict[int, tuple[int, int]] = {}


def fetch(url: str, ua: str = USER_AGENT, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def cik_map() -> dict[str, int]:
    """ticker -> CIK from SEC's company_tickers.json (fetched once)."""
    global _cik_cache
    if _cik_cache is None:
        data = json.loads(fetch("https://www.sec.gov/files/company_tickers.json"))
        _cik_cache = {v["ticker"]: int(v["cik_str"]) for v in data.values()}
        time.sleep(0.5)
    return _cik_cache


def submissions(cik: int) -> list[dict]:
    """All filings for a CIK: (form, filing_date, report_date, accession,
    primary_document) — walks the recent table plus older-file pages."""
    if cik in _submissions_cache:
        return _submissions_cache[cik]

    def rows(payload: dict) -> list[dict]:
        # main JSON wraps the table in filings.recent; older-file pages are
        # flat column arrays at the top level.
        table = payload["filings"]["recent"] if "filings" in payload else payload
        return [
            {"form": f, "filing_date": fd, "report_date": rd, "accession": acc, "primary_doc": doc}
            for f, fd, rd, acc, doc in zip(
                table["form"],
                table["filingDate"],
                table["reportDate"],
                table["accessionNumber"],
                table["primaryDocument"],
            )
        ]

    data = json.loads(fetch(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    fye = data.get("fiscalYearEnd") or "1231"
    _fye_cache[cik] = (int(fye[:2]), int(fye[2:]))
    out = rows(data)
    for page in data["filings"].get("files", []):
        time.sleep(0.5)
        page_data = json.loads(fetch(f"https://data.sec.gov/submissions/{page['name']}"))
        out.extend(rows(page_data))
    _submissions_cache[cik] = out
    time.sleep(0.5)
    return out


def _sub_months(d: dt.date, n: int) -> dt.date:
    """Subtract n calendar months, clamping the day to the target month end."""
    month_index = d.month - 1 - n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        last_day = dt.date(year, 12, 31).day
    else:
        last_day = (dt.date(year, month + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(year, month, min(d.day, last_day))


def _expected_period_end(fye_mmdd: tuple[int, int], year: int, quarter: int | None) -> dt.date:
    """FinanceBench's FY label = the fiscal year ENDING in that calendar year.
    The fiscal quarter q ends 3*(4-q) months before the fiscal year end."""
    end = dt.date(year, fye_mmdd[0], fye_mmdd[1])
    if quarter is None:  # 10-K covers the whole fiscal year
        return end
    return _sub_months(end, 3 * (4 - quarter))


def find_filing(
    entries: list[dict],
    form: str,
    year: int,
    quarter: int | None,
    date_str: str | None,
    fye_mmdd: tuple[int, int],
) -> dict | None:
    """Match a filing by form + fiscal period. 10-K/10-Q match on the report
    date closest to the fiscal period end (any fiscal calendar); 8-Ks match
    on the exact filing date from doc_name."""
    cands = [e for e in entries if e["form"] == form or e["form"].startswith(form + "/")]
    if form == "8-K" and date_str:
        exact = [e for e in cands if e["filing_date"] == date_str]
        if exact:
            return exact[0]
        target = dt.date.fromisoformat(date_str)
        nearby = [
            e
            for e in cands
            if e["filing_date"]
            and abs((dt.date.fromisoformat(e["filing_date"]) - target).days) <= 6
        ]
        if not nearby:
            return None
        nearby.sort(key=lambda e: abs((dt.date.fromisoformat(e["filing_date"]) - target).days))
        return nearby[0]

    target = _expected_period_end(fye_mmdd, year, quarter)
    best: list[tuple[int, dict]] = []
    for e in cands:
        rd = e["report_date"]
        if not rd:
            continue
        gap = abs((dt.date.fromisoformat(rd) - target).days)
        if gap <= 20:  # fiscal quarter ends drift a few days at most
            best.append((gap, e))
    if not best:
        return None
    gap = min(g for g, _ in best)
    ties = [e for g, e in best if g == gap]
    # prefer the original over amendments; earliest filing first
    ties.sort(key=lambda e: (e["form"] != form, e["filing_date"]))
    return ties[0]


def download_doc(rec: dict) -> tuple[Path | None, str]:
    """Fetch one FinanceBench document. Returns (path_or_None, how)."""
    doc_name = rec["doc_name"]
    parsed = parse_doc_name(doc_name)
    for ext in (".htm", ".pdf"):
        existing = DOCS_DIR / f"{doc_name}{ext}"
        if existing.exists():
            return existing, "cached"

    if parsed["form"] == "Earnings":
        url = rec.get("doc_link") or ""
        if not url:
            return None, "no link"
        try:
            blob = fetch(url, ua=BROWSER_UA, timeout=90)
        except Exception as e:
            print(f"    earnings link failed: {type(e).__name__}")
            return None, "link dead"
        if not blob.startswith(b"%PDF"):
            return None, "not a pdf"
        path = DOCS_DIR / f"{doc_name}.pdf"
        path.write_bytes(blob)
        return path, "dataset link"

    ticker = TICKERS[rec["company"]]
    cik = cik_map().get(ticker) or CIK_FALLBACK.get(ticker)
    if cik is None:
        return None, f"no CIK for {ticker}"
    entries = submissions(cik)
    fye = _fye_cache.get(cik, (12, 31))
    hit = find_filing(
        entries, parsed["form"], parsed["year"], parsed["quarter"], parsed["date"], fye
    )
    if hit is None:
        return None, f"EDGAR: no {parsed['form']} for period"
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{hit['accession'].replace('-', '')}/{hit['primary_doc']}"
    )
    try:
        blob = fetch(url, timeout=120)
    except Exception as e:
        print(f"    EDGAR download failed: {type(e).__name__}: {e}")
        return None, "EDGAR download failed"
    ext = ".pdf" if blob.startswith(b"%PDF") else ".htm"
    path = DOCS_DIR / f"{doc_name}{ext}"
    path.write_bytes(blob)
    return path, "EDGAR"


def parse_to_sections(path: Path, form: str) -> list:
    if path.suffix == ".pdf":
        return ingestion.sections_from_text(ingestion.parse_pdf(path))
    html = path.read_text(encoding="utf-8", errors="replace")
    if form == "10-K":
        secs = ingestion.parse_html(html, 200, 5000)
        if secs:
            return secs
    text = BeautifulSoup(html, "lxml").get_text("\n")
    return ingestion.sections_from_text(text)


def build_chunks(doc_name: str, sections: list, rec: dict, filing_date: str) -> list[dict]:
    from ragfilings.chunking import _chunk_one

    parsed = parse_doc_name(doc_name)
    meta = {
        "ticker": TICKERS[rec["company"]],
        "company": rec["company"],
        "filing_date": filing_date,
        "source_url": "",
    }
    chunks: list[dict] = []
    for sec in sections:
        for c in _chunk_one(sec, doc_name, meta, 1800):
            c["form"] = parsed["form"]
            c["fiscal_year"] = parsed["year"]
            chunks.append(c)
    return chunks


def main() -> None:
    for d in (DOCS_DIR, CHUNKS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    recs = load_financebench()
    docs = unique_docs(recs)
    per_doc = questions_per_doc(recs)
    print(f"{len(recs)} questions across {len(docs)} unique documents\n")

    manifest: dict[str, dict] = {}
    all_chunks: list[dict] = []
    for i, (doc_name, rec) in enumerate(sorted(docs.items()), 1):
        parsed = parse_doc_name(doc_name)
        print(f"[{i:>2}/{len(docs)}] {doc_name} ({parsed['form']}, {per_doc[doc_name]} questions)")
        path, how = download_doc(rec)
        entry = {
            "doc_name": doc_name,
            "company": rec["company"],
            "form": parsed["form"],
            "fiscal_year": parsed["year"],
            "source": how,
            "questions": per_doc[doc_name],
            "local_file": path.name if path else None,
            "n_chunks": 0,
            "n_sections": 0,
        }
        if path is None:
            print(f"    UNAVAILABLE ({how})")
            manifest[doc_name] = entry
            continue
        time.sleep(0.5)
        try:
            sections = parse_to_sections(path, parsed["form"])
        except Exception as e:
            print(f"    PARSE FAILED ({type(e).__name__}: {e})")
            entry["source"] = f"parse failed: {type(e).__name__}"
            entry["local_file"] = None
            manifest[doc_name] = entry
            continue
        filing_date = parsed.get("date") or f"{parsed['year']}-07-01"
        chunks = build_chunks(doc_name, sections, rec, filing_date)
        with (CHUNKS_DIR / f"{doc_name}.jsonl").open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        all_chunks.extend(chunks)
        entry["n_sections"] = len(sections)
        entry["n_chunks"] = len(chunks)
        manifest[doc_name] = entry
        print(f"    {entry['source']}: {len(sections)} sections, {len(chunks)} chunks")

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    ok = [e for e in manifest.values() if e["n_chunks"]]
    covered_q = sum(e["questions"] for e in ok)
    print(
        f"\ndocuments: {len(ok)}/{len(docs)} built | questions with their "
        f"document indexed: {covered_q}/{len(recs)}"
    )
    if not all_chunks:
        raise SystemExit("no chunks built — nothing to index")

    print(f"embedding {len(all_chunks)} chunks with BAAI/bge-small-en-v1.5 ...")
    retrieval.build_index(all_chunks, INDEX_DIR, "BAAI/bge-small-en-v1.5")
    print(f"index written to {INDEX_DIR}")


if __name__ == "__main__":
    main()
