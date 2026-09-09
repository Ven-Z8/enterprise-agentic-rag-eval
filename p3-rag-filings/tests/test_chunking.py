"""Chunking: section-scoped, table-safe, note-aware. These invariants feed
retrieval quality directly — a chunk that crosses a section or shears a table
row poisons citations downstream."""

from ragfilings.chunking import _fiscal_year, chunk_sections
from ragfilings.ingestion import Section

# NVDA-shaped: filed Feb 2026 for the fiscal year ENDING Jan 2026 — the filer
# (and the golden set) call that FY2026. The period end is authoritative.
META = {
    "ticker": "TEST",
    "company": "Test Co",
    "filing_date": "2026-02-25",
    "source_url": "https://www.sec.gov/Archives/edgar/data/1/000/test-20260125.htm",
}


def test_fiscal_year_is_period_end_year():
    assert _fiscal_year(META) == 2026  # NVDA/WMT shape (Jan FY end)
    assert _fiscal_year({**META, "source_url": ".../aapl-20250927.htm"}) == 2025
    # No parsable period end: fall back to the filing-date heuristic.
    assert _fiscal_year({"filing_date": "2026-02-25"}) == 2025
    assert _fiscal_year({"filing_date": "2025-10-31", "source_url": "garbage"}) == 2025


def test_fiscal_year_reconciled_home_depot():
    # Home Depot filed in calendar 2026 with period ending Feb 1, 2026, but fiscal year focus 2025
    hd_meta = {
        "ticker": "HD",
        "company": "Home Depot",
        "filing_date": "2026-03-18",
        "source_url": "https://www.sec.gov/Archives/edgar/data/354950/000162828026019436/hd-20260201.htm",
        "DocumentFiscalYearFocus": "2025",
    }
    assert _fiscal_year(hd_meta) == 2025


def _sec(item, text, part="II", title="T", resolved_from=None):
    return Section(item, part, title, text, resolved_from)


def test_ids_boundaries_and_lossless_reassembly():
    secs = [
        _sec("1", "Business prose line.\n" * 120, part="I"),
        _sec("7", "MD&A prose line here.\n" * 200),
    ]
    chunks = chunk_sections(secs, META, max_chars=1_000)
    # IDs extend the golden-set citation format; fiscal year from filing date.
    assert all(c["id"].startswith(f"TEST_2026_10K:Item{c['item']}:c") for c in chunks)
    assert all(c["ticker"] == "TEST" and c["fiscal_year"] == 2026 for c in chunks)
    # No chunk crosses a section; rejoining chunks reproduces each section exactly.
    for sec in secs:
        mine = [c["text"] for c in chunks if c["item"] == sec.item]
        assert "\n".join(mine) == sec.text.strip()
    assert all(c["n_chars"] <= 1_000 for c in chunks)


def test_table_rows_never_split_and_headers_carry():
    rows = [f"Segment {i} | ${i},000 | ${i + 1},000" for i in range(40)]
    table = "\n".join(["Revenue | 2025 | 2024", "(In millions) | x | y", *rows])
    secs = [_sec("8", "Intro line.\n" + table + "\nOutro line.")]
    chunks = chunk_sections(secs, META, max_chars=600)
    tabular = [c for c in chunks if c["has_table"]]
    assert len(tabular) > 1  # long table forced a split
    all_lines = [ln for c in tabular for ln in c["text"].split("\n")]
    for row in rows:
        assert row in all_lines  # every row intact, never sheared
    # Continuation chunks repeat the two header rows for readability.
    conts = [c for c in tabular if c["table_continuation"]]
    assert conts and all(c["text"].startswith("Revenue | 2025 | 2024") for c in conts)


def test_note_metadata_and_note_ref_links():
    text = (
        "Consolidated Statements of Income\n"
        + "Revenue | $130,497 | $60,922\n"
        + "Deferred amounts are described in Note 5 to these statements.\n"
        + "Filler prose sentence.\n" * 30
        + "Notes to the Consolidated Financial Statements\n"
        + "Note 1 — Basis of Presentation\n"
        + "We prepare statements on an accrual basis.\n" * 30
        + "Note 5 — Income Taxes\n"
        + "The provision for TAXDETAIL income taxes was material.\n" * 30
    )
    secs = [_sec("8", text)]
    chunks = chunk_sections(secs, META, max_chars=800)
    head = chunks[0]
    assert head["note"] is None and "5" in head["note_refs"]  # statement -> note link
    note5 = [c for c in chunks if c["note"] == "5"]
    assert note5 and all("TAXDETAIL" in c["text"] or "Note 5" in c["text"] for c in note5)
    # A note heading starts its own chunk — chunks never straddle two notes.
    assert note5[0]["text"].startswith("Note 5 — Income Taxes")
    assert all(c["note"] == "1" for c in chunks if "accrual basis" in c["text"])


def test_section_metadata_carried():
    secs = [
        _sec("8", "Filler content line.\n" * 60, title="Financial Statements", resolved_from="15")
    ]
    c = chunk_sections(secs, META, max_chars=500)[0]
    assert c["section_id"] == "Item8" and c["part"] == "II"
    assert c["title"] == "Financial Statements" and c["resolved_from"] == "15"
    assert c["company"] == "Test Co" and c["doc_id"] == "TEST_2026_10K"
