"""Ingestion: turn a messy 10-K HTML filing into a section tree.

Day 1-2 scope is the section tree only. Days 3-5 add table extraction,
footnote linking, and section-aware chunking on top of the Section list here.

Real filings fight three ways, each handled below:
  1. Every "Item N" heading appears in the Table of Contents AND as the real
     section. We pick, per item, the occurrence with the longest body — the TOC
     copy is immediately followed by the next TOC line, so its body is tiny.
  2. Cover pages / forward-looking summaries repeat item numbers before the
     document even starts. We anchor on the real Item 1 (Business) and drop
     everything before it.
  3. Prose cites earlier items ("Item 1A. Risk Factors" inside the MD&A). Such a
     back-reference can have the longest body and hijack a section, so we enforce
     the 10-K's monotonic item order (1, 1A, 1B, 2, ... 16) and re-pick out-of-order
     headers from their correct position.
  4. Item 7/8 are often one-line POINTERS ("incorporated by reference", "appears
     on pages 46-160") with the real MD&A / financial statements placed after
     Part IV (F-pages) — or, for some filers, swallowed inside another item's
     span. A section under `pointer_chars` triggers content-anchor resolution:
     find the real block (validated audit-report / statement-title / MD&A
     heading), carve it out of whichever section physically holds it, and attach
     it to the stub with `resolved_from` naming the host. Every line still
     belongs to exactly one section.
  5. Some filers (MSFT) stamp bare "Item 7" page-corner labels through a section.
     The last label before the next item can out-gap the real titled header, so a
     bare-label winner is re-picked from titled occurrences with real bodies.
"""

from __future__ import annotations

import bisect
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# Some filings are XHTML; the lxml HTML parser handles them fine for our text pass.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Line-anchored "Item 1", "Item 1A.", "ITEM 7 — ..."; captures number, optional
# letter suffix, and the rest of the line as a title candidate.
_ITEM_RE = re.compile(r"^item\s+(\d{1,2})\s*([A-C])?\b[.:)\s—-]*(.*)$", re.IGNORECASE)
# Trailing dot-leaders + page number from TOC-style lines: "Business .... 4"
_LEADER_RE = re.compile(r"[.\s…]{2,}\d+\s*$")

# --- Content anchors for pointer-stub resolution ---------------------------
# The real F-pages / MD&A block is found by heading lines, VALIDATED so the
# filing's internal TOC copies (followed by a bare page number) and running
# page headers don't match.
_AUDIT_RE = re.compile(r"reports? of independent registered public accounting firm", re.I)
_AUDIT_PROOF_RE = re.compile(r"^(to the |opinion on|we have audited)", re.I)
_STMT_RE = re.compile(
    r"consolidated (balance sheets?|statements? of (income|operations|earnings|"
    r"comprehensive income|cash flows|financial position|(stock|share)holders[’']? equity|"
    r"equity))\s*(\((continued|unaudited)\))?",
    re.I,
)
# Units / registrant subtitle that follows a REAL statement title.
_STMT_PROOF_RE = re.compile(
    r"^\(?(in|millions of|thousands of) (millions|thousands|billions|dollars)"
    r"|and subsidiaries",
    re.I,
)
_MDA_RE = re.compile(r"management[’']s discussion and analysis", re.I)
# Block end markers: signatures / exhibit index that FOLLOW the F-pages return
# to the host section, so Item 15 keeps its exhibit list.
_SIG_RE = re.compile(r"signatures?", re.I)
_PURSUANT_RE = re.compile(r"^pursuant to the requirements", re.I)
_EXH_IDX_RE = re.compile(r"exhibit index", re.I)


def _is_fin_anchor(lines: list[str], i: int) -> bool:
    """Start of the real financial statements at line i?"""
    if _AUDIT_RE.fullmatch(lines[i]):  # audit report headline + addressee/opinion nearby
        return any(_AUDIT_PROOF_RE.match(ln) for ln in lines[i + 1 : i + 6])
    if _STMT_RE.fullmatch(lines[i]):
        # A real statement title carries a units/registrant subtitle within two
        # SHORT lines. MD&A analysis headings reuse the title but run straight
        # into prose (CVX); TOC copies run into page numbers. Both fail this.
        for ln in lines[i + 1 : i + 3]:
            if _STMT_PROOF_RE.search(ln):
                return True
            if len(ln) > 60:
                return False
        return False
    return False


def _is_mda_anchor(lines: list[str], i: int) -> bool:
    # Colon-terminated copies are index entries ("Management's discussion and analysis:").
    return bool(_MDA_RE.match(lines[i])) and not lines[i].endswith(":")


def _is_block_end(lines: list[str], i: int) -> bool:
    if _SIG_RE.fullmatch(lines[i]):
        return i + 1 < len(lines) and bool(_PURSUANT_RE.match(lines[i + 1]))
    return bool(_EXH_IDX_RE.fullmatch(lines[i]))


# Cell holding a figure / year / money placeholder: "1,234", "(56)", "2025", "—".
_NUMCELL_RE = re.compile(r"[$()\d.,%\-—–]+")


def _serialize_tables(soup: BeautifulSoup) -> None:
    """Replace DATA tables with pipe-joined rows so figures keep their labels.

    Gate: >=2 multi-cell rows and >=25% numeric-ish cells. Layout tables that
    merely wrap prose fail the gate and keep flattening line-per-cell as before —
    serializing those would merge whole paragraphs onto one line and break the
    line-anchored "Item N" header detection.
    """
    for table in soup.find_all("table"):
        if table.find_parent("table"):
            continue  # the outermost table flattens nested ones into its cells
        rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            if tr.find_parent("table") is not table:
                continue  # nested row — already flattened into its host cell's text
            cells: list[str] = []
            for td in tr.find_all(["td", "th"], recursive=False):
                txt = re.sub(r"\s+", " ", td.get_text(" ").replace("\xa0", " ")).strip()
                if not txt:
                    continue  # alignment/spacer cell
                if cells and cells[-1] == "$":  # "$" gets its own cell; merge into figure
                    cells[-1] = "$" + txt
                else:
                    cells.append(txt)
            if cells:
                rows.append(cells)
        flat = [c for r in rows for c in r]
        n_multi = sum(len(r) >= 2 for r in rows)
        if (
            n_multi >= 2
            and flat
            and (sum(bool(_NUMCELL_RE.fullmatch(c)) for c in flat) / len(flat) >= 0.25)
        ):
            # 1-cell rows (statement titles, units lines) stay plain lines.
            table.replace_with("\n" + "\n".join(" | ".join(r) for r in rows) + "\n")


# Fallback titles when the detected header line is mangled/empty.
_STD_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "[Reserved] / Selected Financial Data",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Foreign Jurisdiction Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees",
    "15": "Exhibits, Financial Statement Schedules",
    "16": "Form 10-K Summary",
}


@dataclass
class Section:
    item: str  # "1", "1A", "7A", ...
    part: str  # "I" | "II" | "III" | "IV"
    title: str
    text: str
    resolved_from: str | None = None  # item that physically held this body ("15")

    @property
    def n_chars(self) -> int:
        return len(self.text)

    @property
    def label(self) -> str:
        return f"Item {self.item}"


def _part_for(num: int) -> str:
    return "I" if num <= 4 else "II" if num <= 9 else "III" if num <= 14 else "IV"


def _item_key(item: str) -> tuple[int, str]:
    """Sortable key so 1 < 1A < 1B < 2 < ... < 7 < 7A < 8 < 9 < 9A ... ('' < 'A')."""
    m = re.match(r"(\d+)([A-C]?)", item)
    return int(m.group(1)), m.group(2)


def _clean_title(item: str, raw: str) -> str:
    title = _LEADER_RE.sub("", raw).strip(" .:-—")
    # A header line sometimes carries the whole section; keep only a title-length head.
    if len(title) > 90 or not title:
        return _STD_TITLES.get(item, title[:90] or "(untitled)")
    return title


def parse_html(
    html: str, min_section_chars: int = 200, pointer_chars: int = 5_000
) -> list[Section]:
    """Parse 10-K HTML into ordered top-level Item sections.

    Item 7/8 bodies under `pointer_chars` are treated as pointer stubs and
    resolved to the real block elsewhere in the document (see module docstring).
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    _serialize_tables(soup)

    # Normalized non-empty lines; nbsp -> space, whitespace collapsed.
    lines: list[str] = []
    for raw in soup.get_text("\n").split("\n"):
        line = re.sub(r"\s+", " ", raw.replace("\xa0", " ")).strip()
        if line:
            lines.append(line)

    # Candidate headers: (line_index, item_id, raw_title).
    candidates: list[tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        m = _ITEM_RE.match(line)
        if not m:
            continue
        num, suffix, rest = m.group(1), (m.group(2) or "").upper(), m.group(3)
        candidates.append((i, f"{num}{suffix}", rest))

    if not candidates:
        return []

    # Prefix sum of joined-line lengths so body(a, b) = cum[b] - cum[a] is O(1).
    cum = [0]
    for line in lines:
        cum.append(cum[-1] + len(line) + 1)
    cand_starts = [c[0] for c in candidates]

    def body_len(start: int) -> int:
        """Chars from a header line to the next header candidate (any item)."""
        i = bisect.bisect_right(cand_starts, start)
        stop = cand_starts[i] if i < len(cand_starts) else len(lines)
        return cum[stop] - cum[start]

    # Anchor on the real Item 1 (Business) — its longest-body occurrence. Everything
    # before it (cover page, table of contents, forward-looking summaries) is front
    # matter that repeats item numbers; drop it so those stray/ghost headers never
    # reach the section spine. Business is never relocated, so this anchor is safe.
    ones = [ln for ln, item, _ in candidates if item == "1"]
    if ones:
        anchor = max(ones, key=body_len)
        candidates = [c for c in candidates if c[0] >= anchor]
        cand_starts = [c[0] for c in candidates]

    # Per item, the real header is the occurrence with the longest body — this beats
    # the Table of Contents, whose copies have near-empty bodies. When the winner is
    # a BARE label ("Item 7", no title), it is usually a running page header whose
    # gap to the next item out-grew the real header (MSFT stamps one per page);
    # re-pick from titled occurrences that own a real body.
    occ: dict[str, list[tuple[int, str]]] = {}
    for line_idx, item, rest in candidates:
        occ.setdefault(item, []).append((line_idx, rest))

    def _pick(occs: list[tuple[int, str]]) -> tuple[int, str]:
        winner = max(occs, key=lambda lr: body_len(lr[0]))
        if not winner[1].strip():
            titled = [lr for lr in occs if lr[1].strip() and body_len(lr[0]) >= min_section_chars]
            if titled:
                return max(titled, key=lambda lr: body_len(lr[0]))
        return winner

    best = {item: _pick(v) for item, v in occ.items()}

    # Monotonic repair. A 10-K's items run in order (1, 1A, 1B, 2, ... 16), so a
    # chosen header sitting out of order is usually a back-reference that won its slot
    # by body length ("Item 1A. Risk Factors" cited deep inside Item 7, stealing the
    # MD&A). Over the SUBSTANTIAL headers only (tiny TOC-ghost items like an absent
    # Item 1B must not anchor the windows), keep the longest increasing-by-item
    # subsequence; for each out-of-order item, re-pick its longest-body occurrence
    # that fits between its in-order neighbors. If no real header fits the window,
    # LEAVE it as chosen — that is a genuinely messy layout (Days 3-5), not a
    # back-reference, and dropping it would lose content. Already-monotonic filings
    # (the common case) are left exactly as chosen above.
    chosen = sorted(
        (
            (item, ln, rest)
            for item, (ln, rest) in best.items()
            if body_len(ln) >= min_section_chars
        ),
        key=lambda c: c[1],
    )
    keys = [_item_key(c[0]) for c in chosen]
    m = len(chosen)
    length = [1] * m
    par = [-1] * m
    for i in range(m):
        for j in range(i):
            if keys[j] < keys[i] and length[j] + 1 > length[i]:
                length[i], par[i] = length[j] + 1, j
    keep: set[int] = set()
    i = max(range(m), key=lambda k: length[k], default=-1)
    while i != -1:
        keep.add(i)
        i = par[i]

    kept = sorted((chosen[i] for i in keep), key=lambda c: c[1])
    first_kept = kept[0][1] if kept else 0
    for idx in range(m):
        if idx in keep:
            continue
        item, k, ln0 = chosen[idx][0], keys[idx], chosen[idx][1]
        lo = max((c[1] for c in kept if _item_key(c[0]) < k), default=-1)
        hi = min((c[1] for c in kept if _item_key(c[0]) > k), default=len(lines))
        fits = [(ln, rest) for ln, rest in occ[item] if lo < ln < hi]
        if fits:  # a real, correctly-placed header exists — the chosen one was a back-ref
            best[item] = max(fits, key=lambda lr: body_len(lr[0]))
        elif ln0 < first_kept:  # stray header in front matter, ahead of the real spine
            del best[item]
        # else: keep as chosen — messy real content in an odd spot (Days 3-5), not a stray

    # Bodies run from each chosen header to the next chosen header. Entries hold
    # line RANGES (possibly several after resolution carves a block out).
    spine = sorted(((item, ln, rest) for item, (ln, rest) in best.items()), key=lambda c: c[1])
    bounds = [c[1] for c in spine] + [len(lines)]
    entries: list[list] = [  # [item, title_rest, ranges, resolved_from]
        [item, rest, [(ln, bounds[pos + 1])], None] for pos, (item, ln, rest) in enumerate(spine)
    ]

    _resolve_pointer_stubs(entries, lines, cum, pointer_chars)

    sections: list[Section] = []
    for item, rest, ranges, resolved_from in entries:
        text = "\n".join("\n".join(lines[a:b]) for a, b in ranges)
        if len(text) < min_section_chars:  # drop pointer/ghost stubs with no real body
            continue
        sections.append(
            Section(
                item, _part_for(_item_key(item)[0]), _clean_title(item, rest), text, resolved_from
            )
        )
    return sections


def _resolve_pointer_stubs(
    entries: list[list], lines: list[str], cum: list[int], pointer_chars: int
) -> None:
    """Attach the real MD&A / financial-statements block to Item 7/8 pointer stubs.

    Item 8 resolves first: when both items point into the same back-matter block
    (JPM, XOM, CVX), Item 7's carve then naturally ends where Item 8's began.
    A carved range moves — never copies — so no line lands in two sections; text
    after a block-end marker (signatures, exhibit index) stays with the host.
    """

    def span(a: int, b: int) -> int:
        return cum[b] - cum[a]

    def _size(e: list) -> int:
        return sum(span(a, b) for a, b in e[2])

    for target, is_anchor in (("8", _is_fin_anchor), ("7", _is_mda_anchor)):
        ent = next((e for e in entries if e[0] == target), None)
        if ent and _size(ent) >= pointer_chars:
            continue  # real body — nothing to resolve

        def _scan(start: int) -> tuple[int, list, int] | None:
            for i in range(start, len(lines)):
                if not is_anchor(lines, i):
                    continue
                # The anchor must own a real remaining span — quoted titles inside
                # pointer stubs (which are < pointer_chars) can never host one.
                for e in entries:
                    for r, (a, b) in enumerate(e[2]):
                        if a <= i < b and span(i, b) >= pointer_chars:
                            return i, e, r
            return None

        # The block never starts before the last REAL section preceding the target.
        # Scan after it (F-pages-after-Part-IV, the usual layout), then inside it
        # (PEP: the statements sit inside Item 7's span, before its Item 8 pointer).
        tkey = _item_key(target)
        prev = [e for e in entries if _item_key(e[0]) < tkey and _size(e) >= pointer_chars]
        if not prev:
            continue
        last = max(prev, key=lambda e: e[2][0][0])
        hit = _scan(last[2][-1][1]) or _scan(last[2][0][0] + 1)
        if hit is None:
            continue  # leave the stub as-is; coverage will report it honestly
        i, host, r = hit
        a, b = host[2][r]
        end = next((j for j in range(i + 1, b) if _is_block_end(lines, j)), b)
        host[2][r : r + 1] = [rng for rng in ((a, i), (end, b)) if rng[0] < rng[1]]
        if ent:
            ent[2].append((i, end))  # pointer text stays as the section's preamble
            ent[3] = host[0]
        else:
            tkey = _item_key(target)
            pos = max((k + 1 for k, e in enumerate(entries) if _item_key(e[0]) < tkey), default=0)
            entries.insert(pos, [target, "", [(i, end)], host[0]])


def parse_file(
    path: str | Path, min_section_chars: int = 200, pointer_chars: int = 5_000
) -> list[Section]:
    return parse_html(
        Path(path).read_text(encoding="utf-8", errors="replace"), min_section_chars, pointer_chars
    )


def parse_pdf(path: str | Path) -> str:
    """Extract plain text from a PDF filing, page by page (pymupdf)."""
    import pymupdf

    doc = pymupdf.open(str(path))
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def sections_from_text(text: str, max_section_chars: int = 6_000) -> list[Section]:
    """Generic sectioning for documents with no 10-K Item structure (10-Q/8-K
    HTML that yielded no items, earnings releases, PDF filings): blank/paragraph
    lines grouped into size-capped sections."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    sections: list[Section] = []
    cur: list[str] = []
    cur_len = 0

    def flush() -> None:
        nonlocal cur, cur_len
        if cur:
            sections.append(
                Section(
                    item=f"S{len(sections) + 1}",
                    part="I",
                    title=f"Part {len(sections) + 1}",
                    text="\n".join(cur),
                )
            )
            cur, cur_len = [], 0

    for ln in lines:
        if cur and cur_len + len(ln) > max_section_chars:
            flush()
        cur.append(ln)
        cur_len += len(ln) + 1
    flush()
    return sections


def render_tree(sections: list[Section]) -> str:
    """Pretty section tree grouped by Part."""
    out: list[str] = []
    last_part = None
    for s in sections:
        if s.part != last_part:
            out.append(f"PART {s.part}")
            last_part = s.part
        mark = f"  <- Item {s.resolved_from}" if s.resolved_from else ""
        out.append(f"  {s.label:<8} {s.title:<62.62} {s.n_chars:>9,} chars{mark}")
    return "\n".join(out)
