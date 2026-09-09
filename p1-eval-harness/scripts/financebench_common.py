"""Shared FinanceBench helpers: dataset loading (downloads on first use) and
the doc inventory the 150 questions reference."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

P1 = Path(__file__).resolve().parent.parent
FB_DIR = P1 / "data" / "financebench"
FB = FB_DIR / "financebench_merged.jsonl"
FB_URL = (
    "https://huggingface.co/datasets/PatronusAI/financebench/resolve/main/financebench_merged.jsonl"
)

_DOC_NAME_RE = re.compile(
    r"^(?P<co>.+?)_(?P<period>\d{4}(?:Q\d)?)_(?P<form>10K|10Q|8K|EARNINGS)"
    r"(?:_dated[-_](?P<date>\d{4}-\d{2}-\d{2}))?$"
)

FORM_LABEL = {"10K": "10-K", "10Q": "10-Q", "8K": "8-K", "EARNINGS": "Earnings"}


def load_financebench() -> list[dict]:
    if not FB.exists():
        FB.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading FinanceBench -> {FB}")
        try:
            urllib.request.urlretrieve(FB_URL, FB)
        except Exception as e:
            raise SystemExit(
                f"could not download FinanceBench ({e}); save "
                f"financebench_merged.jsonl to {FB} manually "
                "(HuggingFace: PatronusAI/financebench, CC-BY-NC-4.0)"
            )
    return [json.loads(line) for line in FB.open() if line.strip()]


def parse_doc_name(doc_name: str) -> dict[str, str | None]:
    """'FOOTLOCKER_2022_8K_dated_2022-08-19' ->
    {period: '2022', form: '8-K', year: 2022, quarter: None, date: ...}."""
    m = _DOC_NAME_RE.match(doc_name)
    if not m:
        raise ValueError(f"unparsable doc_name: {doc_name}")
    period, form = m["period"], FORM_LABEL[m["form"]]
    year = int(period[:4])
    quarter = int(period[-1]) if "Q" in period else None
    return {"form": form, "year": year, "quarter": quarter, "date": m["date"]}


def unique_docs(recs: list[dict]) -> dict[str, dict]:
    """First record per doc_name (carries doc_link/company/doc_type)."""
    docs: dict[str, dict] = {}
    for r in recs:
        docs.setdefault(r["doc_name"], r)
    return docs


def questions_per_doc(recs: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in recs:
        counts[r["doc_name"]] = counts.get(r["doc_name"], 0) + 1
    return counts
