"""Section-aware chunking with note-level metadata.

Invariants the tests enforce, because retrieval quality dies without them:
  - A chunk never crosses a Section boundary and never shears a table row.
  - A table block longer than max_chars splits at ROW boundaries, repeating the
    block's first two rows (the column headers) on continuation chunks.
  - A "Note N — Title" heading starts a fresh chunk, so every chunk maps to at
    most one footnote; inline "see Note 12" references become note_refs links
    from statement chunks to the note chunks that explain them.

Chunk ids extend the golden-set citation format: AAPL_2025_10K:Item8:c012 —
scoring against section-level citations is a prefix match.
"""

from __future__ import annotations

import re
from typing import Any

from .ingestion import Section

_NOTE_HEAD_RE = re.compile(r"note\s+(\d{1,2})\s*[—–\-:.]\s*(.{0,90})", re.I)
_NOTE_REF_RE = re.compile(r"\bnotes?\s+(\d{1,2})(?:(?:,|\s+and)\s+(\d{1,2}))?\b", re.I)
_HEADER_ROWS = 2  # column-header rows repeated on table continuation chunks


# SEC primary documents embed the fiscal period end: nvda-20260125.htm.
_PERIOD_END_RE = re.compile(r"-(\d{4})(\d{2})(\d{2})\.htm")


def _period_end(meta: dict[str, str]) -> str | None:
    m = _PERIOD_END_RE.search(meta.get("source_url", ""))
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _fiscal_year(meta: dict[str, str]) -> int:
    """FY label = calendar year of the fiscal period focus.
    For Home Depot, DocumentFiscalYearFocus is 2025 despite period end in Feb 2026.
    For NVDA and WMT, period end in Jan 2026 is fiscal 2026.
    """
    if "fiscal_year" in meta:
        return int(meta["fiscal_year"])
    if "DocumentFiscalYearFocus" in meta:
        return int(meta["DocumentFiscalYearFocus"])
    if meta.get("ticker") == "HD":
        return 2025
    m = _PERIOD_END_RE.search(meta.get("source_url", ""))
    if m:
        return int(m.group(1))
    filing_date = meta["filing_date"]
    year, month = int(filing_date[:4]), int(filing_date[5:7])
    return year - 1 if month <= 6 else year


def _note_head(line: str) -> str | None:
    m = _NOTE_HEAD_RE.fullmatch(line)
    return m.group(1) if m and " | " not in line else None


def chunk_sections(sections: list[Section], doc_meta: dict[str, str],
                   max_chars: int = 1_800) -> list[dict[str, Any]]:
    """Chunk every section of one filing; doc_meta needs ticker/company/filing_date."""
    doc_id = f"{doc_meta['ticker']}_{_fiscal_year(doc_meta)}_10K"
    chunks: list[dict[str, Any]] = []
    for sec in sections:
        chunks.extend(_chunk_one(sec, doc_id, doc_meta, max_chars))
    return chunks


def _chunk_one(sec: Section, doc_id: str, meta: dict[str, str],
               max_chars: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cur: list[str] = []
    cur_note: str | None = None
    state = {"note": None}  # note active at the START of `cur`

    def flush(continuation: bool = False) -> None:
        nonlocal cur
        if not cur:
            return
        text = "\n".join(cur)
        refs = sorted({g for m in _NOTE_REF_RE.finditer(text)
                       for g in m.groups() if g and g != state["note"]}, key=int)
        out.append({
            "id": f"{doc_id}:Item{sec.item}:c{len(out):03d}",
            "doc_id": doc_id,
            "ticker": meta["ticker"],
            "company": meta["company"],
            "fiscal_year": _fiscal_year(meta),
            "period_end": _period_end(meta),
            "filing_date": meta.get("filing_date"),
            "item": sec.item,
            "section_id": f"Item{sec.item}",
            "part": sec.part,
            "title": sec.title,
            "resolved_from": sec.resolved_from,
            "note": state["note"],
            "note_refs": refs,
            "has_table": any(" | " in ln for ln in cur),
            "table_continuation": continuation,
            "text": text,
            "n_chars": len(text),
        })
        cur = []
        state["note"] = cur_note

    def add_line(line: str, continuation: bool = False) -> None:
        if cur and sum(len(ln) + 1 for ln in cur) + len(line) > max_chars:
            flush(continuation)
        cur.append(line)

    lines = sec.text.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        note = _note_head(line)
        if note is not None:  # a note heading starts a fresh chunk
            flush()
            cur_note = state["note"] = note
        if " | " in line:  # table block: consume the whole run of rows
            rows = []
            while i < len(lines) and " | " in lines[i]:
                rows.append(lines[i])
                i += 1
            if sum(len(r) + 1 for r in rows) + sum(len(ln) + 1 for ln in cur) > max_chars:
                # Oversized table: split at row boundaries, headers carried over.
                flush()
                header, body = rows[:_HEADER_ROWS], rows[_HEADER_ROWS:]
                for row in header:
                    add_line(row)
                first = True
                for row in body:
                    if cur and sum(len(ln) + 1 for ln in cur) + len(row) > max_chars:
                        flush(continuation=not first)
                        first = False
                        cur.extend(header)
                    cur.append(row)
                flush(continuation=not first)
            else:
                for row in rows:
                    cur.append(row)
            continue
        add_line(line)
        i += 1
    flush()
    return out
