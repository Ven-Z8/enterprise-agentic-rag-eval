#!/usr/bin/env python3
"""Download the P3 corpus: latest 10-K filings for ~25 companies from SEC EDGAR.

Run from the p3-rag-filings directory (no dependencies beyond stdlib):

    python scripts/download_corpus.py

SEC fair-access rules: identify yourself via User-Agent and stay under
10 requests/second. This script is deliberately slow (0.5s sleep).
Docs: https://www.sec.gov/os/accessing-edgar-data
"""

from __future__ import annotations

import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

USER_AGENT = "Venkis Portfolio Research venkatesh.gtd1@gmail.com"
OUT_DIR = Path(__file__).resolve().parent.parent / "corpus"

# (ticker, CIK, company) — spread across sectors so tables/footnotes vary widely.
COMPANIES: list[tuple[str, int, str]] = [
    ("AAPL", 320193, "Apple"),
    ("MSFT", 789019, "Microsoft"),
    ("AMZN", 1018724, "Amazon"),
    ("GOOGL", 1652044, "Alphabet"),
    ("META", 1326801, "Meta Platforms"),
    ("NVDA", 1045810, "NVIDIA"),
    ("TSLA", 1318605, "Tesla"),
    ("JPM", 19617, "JPMorgan Chase"),
    ("BAC", 70858, "Bank of America"),
    ("GS", 886982, "Goldman Sachs"),
    ("WMT", 104169, "Walmart"),
    ("COST", 909832, "Costco"),
    ("JNJ", 200406, "Johnson & Johnson"),
    ("PFE", 78003, "Pfizer"),
    ("UNH", 731766, "UnitedHealth"),
    ("XOM", 34088, "Exxon Mobil"),
    ("CVX", 93410, "Chevron"),
    ("KO", 21344, "Coca-Cola"),
    ("PEP", 77476, "PepsiCo"),
    ("PG", 80424, "Procter & Gamble"),
    ("DIS", 1744489, "Disney"),
    ("NFLX", 1065280, "Netflix"),
    ("BA", 12927, "Boeing"),
    ("CAT", 18230, "Caterpillar"),
    ("HD", 354950, "Home Depot"),
]


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def latest_10k(cik: int) -> tuple[str, str, str] | None:
    """Return (accession_no_nodash, primary_doc, filing_date) for latest 10-K."""
    data = fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    recent = data["filings"]["recent"]
    for form, acc, doc, date in zip(
        recent["form"],
        recent["accessionNumber"],
        recent["primaryDocument"],
        recent["filingDate"],
    ):
        if form == "10-K":
            return acc.replace("-", ""), doc, date
    return None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_DIR / "manifest.csv"
    rows = []
    for ticker, cik, name in COMPANIES:
        try:
            hit = latest_10k(cik)
            if hit is None:
                print(f"!! {ticker}: no 10-K found", file=sys.stderr)
                continue
            acc, doc, date = hit
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
            dest = OUT_DIR / f"{ticker}_{date}_10K.htm"
            if dest.exists():
                print(f"-- {ticker}: already downloaded")
            else:
                dest.write_bytes(fetch_bytes(url))
                print(f"ok {ticker}: {date} ({dest.stat().st_size // 1024} KB)")
            rows.append([ticker, name, cik, date, url, dest.name])
            time.sleep(0.5)
        except Exception as e:  # noqa: BLE001 — log and continue
            print(f"!! {ticker}: {e}", file=sys.stderr)

    with manifest_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "company", "cik", "filing_date", "source_url", "local_file"])
        w.writerows(rows)
    print(f"\n{len(rows)}/{len(COMPANIES)} filings. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
