"""Ingestion smoke + regression checks. The section-tree logic is the fragile part."""

from pathlib import Path

import pytest

from ragfilings.ingestion import parse_file, parse_html, render_tree

# Minimal 10-K-shaped doc: a TOC that names every item, then the real sections.
# The TOC copies have no body; the real ones do. Parser must keep the real ones.
_HTML = """
<html><body>
<p>Item 1. Business ......... 4</p>
<p>Item 1A. Risk Factors ......... 12</p>
<p>Item 7. Management's Discussion ......... 30</p>

<p>Item 1. Business</p>
<p>{biz}</p>
<p>Item 1A. Risk Factors</p>
<p>{risk}</p>
<p>Item 7. Management's Discussion and Analysis</p>
<p>{mda}</p>
</body></html>
""".format(
    biz="Apple designs phones. " * 30, risk="Markets are risky. " * 60, mda="Revenue rose. " * 40
)


def test_toc_deduped_and_ordered():
    secs = parse_html(_HTML, min_section_chars=100)
    items = [s.item for s in secs]
    assert items == ["1", "1A", "7"], items  # no TOC ghosts, doc order
    assert all(s.n_chars > 100 for s in secs)  # real bodies, not TOC stubs
    assert secs[1].item == "1A" and "risk" in secs[1].text.lower()


def test_part_grouping():
    secs = parse_html(_HTML, min_section_chars=100)
    assert secs[0].part == "I" and secs[2].part == "II"
    assert "PART I" in render_tree(secs)


# Regression: a back-reference to "Item 1A" *inside* Item 7's MD&A must not hijack
# Item 1A nor truncate Item 7. This is the bug that scrambled the BAC and XOM trees:
# the nested cite had the longest body, so the greedy per-item pick chose it.
_BACKREF_HTML = """
<html><body>
<p>Item 1. Business ... 4</p>
<p>Item 1A. Risk Factors ... 12</p>
<p>Item 7. MD&A ... 30</p>
<p>Item 8. Financial Statements ... 60</p>

<p>Item 1. Business</p>
<p>{biz}</p>
<p>Item 1A. Risk Factors</p>
<p>{risk}</p>
<p>Item 7. Management's Discussion and Analysis</p>
<p>{mda1}</p>
<p>Item 1A. Risk Factors of this Annual Report on Form 10-K</p>
<p>{mda2}</p>
<p>Item 8. Financial Statements and Supplementary Data</p>
<p>{fin}</p>
</body></html>
""".format(
    biz="We sell things. " * 20,
    risk="RISKTEXT is dangerous. " * 40,
    mda1="Revenue grew. " * 20,
    mda2="MARGINS improved sharply. " * 90,
    fin="Total assets. " * 30,
)


def test_backreference_does_not_hijack_or_truncate():
    secs = {s.item: s for s in parse_html(_BACKREF_HTML, min_section_chars=100)}
    assert list(secs) == ["1", "1A", "7", "8"]  # monotonic, single 1A
    # Item 1A is the real early section (risk text), not the MD&A back-reference.
    assert "RISKTEXT" in secs["1A"].text and "MARGINS" not in secs["1A"].text
    # Item 7 keeps the MD&A that follows the back-reference line (not truncated).
    assert "MARGINS" in secs["7"].text


# Real-corpus guards for the exact filings the back-ref bug scrambled. Skipped when
# the (gitignored) corpus is not present.
_CORPUS = Path(__file__).resolve().parent.parent / "corpus"


def _find(ticker: str):
    hits = sorted(_CORPUS.glob(f"{ticker}_*_10K.htm"))
    return hits[0] if hits else None


@pytest.mark.skipif(_find("BAC") is None, reason="corpus not downloaded")
def test_bac_mda_recovered():
    secs = {s.item: s for s in parse_file(_find("BAC"))}
    assert secs["7"].n_chars > 100_000  # MD&A recovered (was truncated to ~2.7K)
    assert secs["1A"].n_chars > 50_000  # real Risk Factors present, not the cite


@pytest.mark.skipif(_find("XOM") is None, reason="corpus not downloaded")
def test_xom_properties_not_scrambled():
    secs = {s.item: s for s in parse_file(_find("XOM"))}
    assert secs["2"].n_chars < 50_000  # Properties not bloated to ~197K by a cross-ref


# --- Pointer-stub resolution ("incorporated by reference") -----------------
# Many filers make Item 7/8 one-line pointers and put the real MD&A/financial
# statements after Part IV (F-pages). The parser must detect the stub, find the
# real block by content anchor, and carve it out of the host section — no line
# of the document may end up in two sections.

_FILL = dict(
    biz="We design chips. " * 40,
    risk="Competition is fierce. " * 60,
    mda="Revenue grew because DATACENTERBOOM continued. " * 40,
    exhibits="3.1 Certificate of Incorporation. 10.5 Equity plan. " * 10,
    audit="We have audited the accompanying consolidated balance sheets. AUDITOPINION. " * 20,
    fin="Total assets FINBLOCK were higher. " * 60,
    notes="Note 1 Basis of presentation. " * 40,
    exhtail="10.1 Form of Award Agreement EXHTAIL. " * 15,
)

# NVDA-shaped: Item 8 is a short pointer; F-pages live inside Item 15 between
# the exhibit preamble and the Exhibit Index.
_POINTER_HTML = """
<html><body>
<p>Item 1. Business ... 4</p>
<p>Item 8. Financial Statements ... 60</p>

<p>Item 1. Business</p>
<p>{biz}</p>
<p>Item 1A. Risk Factors</p>
<p>{risk}</p>
<p>Item 7. Management's Discussion and Analysis</p>
<p>{mda}</p>
<p>Item 8. Financial Statements and Supplementary Data</p>
<p>The information required by this Item is set forth in our Consolidated Financial
Statements and Notes thereto included in this Annual Report on Form 10-K and is
incorporated by reference. See Item 15.</p>
<p>Item 15. Exhibits and Financial Statement Schedules</p>
<p>{exhibits}</p>
<p>Report of Independent Registered Public Accounting Firm</p>
<p>To the Board of Directors and Shareholders</p>
<p>{audit}</p>
<p>Consolidated Balance Sheets</p>
<p>(In millions)</p>
<p>{fin}</p>
<p>Notes to the Consolidated Financial Statements</p>
<p>{notes}</p>
<p>Exhibit Index</p>
<p>{exhtail}</p>
</body></html>
""".format(**_FILL)


def test_pointer_stub_resolved_from_host():
    secs = parse_html(_POINTER_HTML, min_section_chars=100, pointer_chars=1_000)
    by = {s.item: s for s in secs}
    assert [s.item for s in secs] == ["1", "1A", "7", "8", "15"]  # order kept
    # Item 8 got the real block, flagged with its physical home.
    assert by["8"].resolved_from == "15"
    assert "FINBLOCK" in by["8"].text and "AUDITOPINION" in by["8"].text
    assert "incorporated by reference" in by["8"].text  # pointer text kept as preamble
    assert by["8"].n_chars > 2_000
    # Host keeps its own content on both sides of the carve; no duplication.
    assert "3.1 Certificate" in by["15"].text and "EXHTAIL" in by["15"].text
    assert "FINBLOCK" not in by["15"].text
    assert "EXHTAIL" not in by["8"].text
    # Untouched sections carry no flag.
    assert by["7"].resolved_from is None


# PEP-shaped: no Item 8 header exists at all; the statements sit INSIDE Item 7's
# body after the MD&A. Item 8 must be created by splitting Item 7.
_SWALLOWED_HTML = """
<html><body>
<p>Item 1. Business ... 4</p>

<p>Item 1. Business</p>
<p>{biz}</p>
<p>Item 7. Management's Discussion and Analysis</p>
<p>{mda}</p>
<p>Consolidated Statements of Income</p>
<p>(In millions, except per share data)</p>
<p>{fin}</p>
<p>Notes to the Consolidated Financial Statements</p>
<p>{notes}</p>
<p>Item 9A. Controls and Procedures</p>
<p>Our management evaluated our disclosure controls and procedures. They are effective.
Based on that evaluation there were no changes in internal control over financial
reporting that materially affected it.</p>
</body></html>
""".format(**_FILL)


def test_missing_item8_carved_out_of_item7():
    secs = parse_html(_SWALLOWED_HTML, min_section_chars=100, pointer_chars=1_000)
    by = {s.item: s for s in secs}
    assert [s.item for s in secs] == ["1", "7", "8", "9A"]  # created 8 in item order
    assert by["8"].resolved_from == "7"
    assert "FINBLOCK" in by["8"].text
    assert by["8"].title  # synthesized title, not empty
    # The MD&A no longer carries the statements; the split point is the real title.
    assert "FINBLOCK" not in by["7"].text and "DATACENTERBOOM" in by["7"].text
    assert by["7"].resolved_from is None


# PEP-shaped: the Item 8 header appears AFTER the statements, as part of a formal
# pointer sequence ("See Item 15"). The scan must also look INSIDE the preceding
# real section, not just after it.
_LATE_POINTER_HTML = """
<html><body>
<p>Item 1. Business ... 4</p>

<p>Item 1. Business</p>
<p>{biz}</p>
<p>Item 7. Management's Discussion and Analysis</p>
<p>{mda}</p>
<p>Consolidated Statements of Income</p>
<p>(In millions, except per share data)</p>
<p>{fin}</p>
<p>Item 7A. Quantitative and Qualitative Disclosures About Market Risk</p>
<p>Included in the MD&A above.</p>
<p>Item 8. Financial Statements and Supplementary Data</p>
<p>See Item 15. Included above.</p>
<p>Item 9A. Controls and Procedures</p>
<p>Our management evaluated our disclosure controls and procedures. They are effective.
Based on that evaluation there were no changes in internal control over financial
reporting that materially affected it.</p>
</body></html>
""".format(**_FILL)


def test_late_pointer_item8_still_resolved():
    secs = parse_html(_LATE_POINTER_HTML, min_section_chars=20, pointer_chars=1_000)
    by = {s.item: s for s in secs}
    assert by["8"].resolved_from == "7"
    assert "FINBLOCK" in by["8"].text and "See Item 15" in by["8"].text
    assert "FINBLOCK" not in by["7"].text and "DATACENTERBOOM" in by["7"].text


# MSFT-shaped: bare "Item 7" page-corner labels repeat through the MD&A. The real
# titled header must win even though a late corner label has a longer gap to the
# next candidate — otherwise the MD&A head lands in Item 6 "[Reserved]".
_RUNNING_HEADER_HTML = """
<html><body>
<p>Item 1. Business ... 4</p>

<p>Item 1. Business</p>
<p>{biz}</p>
<p>Item 6. [Reserved]</p>
<p>Item 7. Management's Discussion and Analysis</p>
<p>MDASTART. {mda}</p>
<p>Item 7</p>
<p>{mda}</p>
<p>Item 7</p>
<p>{mda}</p>
<p>Item 7</p>
<p>{mda}{mda}</p>
<p>Item 8. Financial Statements and Supplementary Data</p>
<p>Report of Independent Registered Public Accounting Firm</p>
<p>To the Board of Directors</p>
<p>{audit}</p>
<p>{fin}</p>
</body></html>
""".format(**_FILL)


def test_running_page_labels_do_not_steal_section_start():
    secs = parse_html(_RUNNING_HEADER_HTML, min_section_chars=100, pointer_chars=1_000)
    by = {s.item: s for s in secs}
    assert "MDASTART" in by["7"].text  # starts at the titled header
    assert by["7"].text.count("DATACENTERBOOM") >= 160  # whole MD&A, all pages
    assert "6" not in by or "MDASTART" not in by["6"].text


# --- Table extraction: data tables keep row structure ----------------------
# Financial tables must not flatten to one-cell-per-line word soup; layout
# tables (prose wrappers) must NOT be serialized or they would merge paragraphs
# and break line-anchored header detection.

_TABLE_HTML = """
<html><body>
<p>Item 1. Business</p>
<p>{biz}</p>
<table><tr><td>
<p>This paragraph lives inside a LAYOUTWRAP table cell and must stay prose.</p>
</td></tr><tr><td>
<p>Second wrapped paragraph, still prose, no pipes.</p>
</td></tr></table>
<p>Item 8. Financial Statements and Supplementary Data</p>
<p>Consolidated Statements of Income</p>
<p>(In millions, except per share data)</p>
<table>
 <tr><td></td><td>2025</td><td>2024</td></tr>
 <tr><td>Revenue</td><td>$</td><td>130,497</td><td>$</td><td>60,922</td></tr>
 <tr><td>Net income</td><td>72,880</td><td>29,760</td></tr>
 <tr><td>Nested<table><tr><td>inner</td><td>cell</td></tr></table></td><td>77</td></tr>
 <tr><td>Margin note</td></tr>
</table>
<p>{notes}</p>
</body></html>
""".format(**_FILL)


def test_data_table_rows_preserved_layout_tables_untouched():
    secs = parse_html(_TABLE_HTML, min_section_chars=100, pointer_chars=100_000_000)
    by = {s.item: s for s in secs}
    t = by["8"].text
    assert "2025 | 2024" in t  # header row joined
    assert "Revenue | $130,497 | $60,922" in t  # $ merged into its figure
    assert "Net income | 72,880 | 29,760" in t
    assert "Margin note" in t and "Margin note |" not in t  # 1-cell row stays plain
    assert "Nested inner cell | 77" in t  # nested table flattens into its cell once
    assert t.count("inner") == 1  # ...without duplication
    # Layout table: prose not pipe-joined, paragraphs on separate lines.
    assert "LAYOUTWRAP table cell and must stay prose." in by["1"].text
    assert "prose. | " not in by["1"].text


@pytest.mark.skipif(_find("NVDA") is None, reason="corpus not downloaded")
def test_nvda_statement_tables_have_rows():
    by = {s.item: s for s in parse_file(_find("NVDA"))}
    # The income statement must contain multi-column rows, not cell-per-line soup.
    assert any(" | " in ln and "$" in ln for ln in by["8"].text.split("\n")[:400])


# --- Real-corpus guards for stub resolution (NVDA + JPM fixtures) ----------


@pytest.mark.skipif(_find("NVDA") is None, reason="corpus not downloaded")
def test_nvda_item8_resolved_from_item15():
    by = {s.item: s for s in parse_file(_find("NVDA"))}
    assert by["8"].resolved_from == "15"
    assert by["8"].n_chars > 50_000  # was a 206-char pointer stub
    assert "Report of Independent Registered" in by["8"].text[:3_000]
    assert by["15"].n_chars < 20_000  # exhibit index kept, F-pages carved out
    assert "Exhibit Index" in by["15"].text  # tail reattached to host


@pytest.mark.skipif(_find("JPM") is None, reason="corpus not downloaded")
def test_jpm_mda_and_financials_resolved_from_item15():
    by = {s.item: s for s in parse_file(_find("JPM"))}
    # Bank 10-K: MD&A and financial statements both live after Item 15.
    assert by["7"].resolved_from == "15" and by["7"].n_chars > 100_000
    assert by["8"].resolved_from == "15" and by["8"].n_chars > 100_000
    assert by["15"].n_chars < 40_000  # host keeps exhibits + signatures only


@pytest.mark.skipif(_find("MSFT") is None, reason="corpus not downloaded")
def test_msft_mda_not_stolen_by_running_labels():
    by = {s.item: s for s in parse_file(_find("MSFT"))}
    assert by["7"].n_chars > 30_000  # was 9.9K; head sat in Item 6 "[Reserved]"
    assert by["8"].n_chars > 50_000


@pytest.mark.skipif(_find("PEP") is None, reason="corpus not downloaded")
def test_pep_statements_carved_out_of_mda():
    by = {s.item: s for s in parse_file(_find("PEP"))}
    # PEP: statements sit inside Item 7's span; the Item 8 header is a late pointer.
    assert by["8"].resolved_from == "7" and by["8"].n_chars > 100_000
    assert 50_000 < by["7"].n_chars < 150_000  # MD&A alone (was 241K with statements)


def test_sections_from_text_generic_split():
    # For documents with no Item structure (10-Q/8-K HTML, earnings PDFs) the
    # generic sectioner groups lines into size-capped sections labelled S1..Sn.
    from ragfilings.ingestion import sections_from_text

    text = "\n".join([f"line {i} of prose" for i in range(200)])
    secs = sections_from_text(text, max_section_chars=500)
    assert len(secs) > 1
    assert [s.item for s in secs] == [f"S{i}" for i in range(1, len(secs) + 1)]
    assert all(s.n_chars <= 500 + 40 for s in secs)  # cap holds (± one line)
    # every line survives exactly once
    rejoined = "\n".join(s.text for s in secs)
    assert rejoined == text


if __name__ == "__main__":
    test_toc_deduped_and_ordered()
    test_part_grouping()
    test_backreference_does_not_hijack_or_truncate()
    test_pointer_stub_resolved_from_host()
    test_missing_item8_carved_out_of_item7()
    test_running_page_labels_do_not_steal_section_start()
    print("ok")
