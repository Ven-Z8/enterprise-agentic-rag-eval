"""Tests for the fact graph: deterministic multi-year table extraction,
provenance, community detection, and the query engine."""

from ragfilings.domains.financial.builder import FinancialGraphBuilder
from ragfilings.domains.financial.query import GraphQueryEngine

STATEMENT_CHUNK = {
    "id": "AAPL_2025_10K:Item8:c007",
    "ticker": "AAPL",
    "fiscal_year": 2025,
    "section_id": "Item8",
    "text": (
        "CONSOLIDATED STATEMENTS OF OPERATIONS (In millions)\n"
        "Three fiscal years ended | 2025 | 2024 | 2023\n"
        "Total net sales | $416,161 | $391,035 | $383,285\n"
        "Net income | $112,010 | $93,736 | $96,995\n"
        "Gross margin percentage | 46.9% | 46.2% | 45.2%\n"
    ),
}


def _build(chunk=STATEMENT_CHUNK):
    builder = FinancialGraphBuilder()
    builder.ingest_chunk(chunk)
    return builder


# ------------------------------------------------------------- extraction


def test_multi_year_columns_are_attributed_to_their_years():
    engine = GraphQueryEngine(builder=_build())
    series = engine.get_metric_history("AAPL", "Net Sales")
    by_year = {row["fiscal_year"]: row["value"] for row in series}
    assert by_year == {"2025": 416161.0, "2024": 391035.0, "2023": 383285.0}
    assert all(r["chunk_id"] == "AAPL_2025_10K:Item8:c007" for r in series)


def test_percentage_rows_get_pct_unit():
    engine = GraphQueryEngine(builder=_build())
    row = engine.get_metric_value("AAPL", "Gross Margin", 2025)
    assert row is not None and row["value"] == 46.9 and row["unit"] == "PCT"


def test_thousands_unit_detected():
    chunk = {
        "id": "X_2025_10K:Item8:c000",
        "ticker": "X",
        "fiscal_year": 2025,
        "text": "(In thousands)\nNet income | 2025 | 2024\nNet income | $1,000 | $900",
    }
    engine = GraphQueryEngine(builder=_build(chunk))
    row = engine.get_metric_value("X", "Net Income", 2025)
    assert row["unit"] == "USD_TH" and row["value"] == 1000.0


def test_mixed_units_in_one_chunk_use_nearest_annotation():
    chunk = {
        "id": "X_2025_10K:Item8:c010",
        "ticker": "X",
        "fiscal_year": 2025,
        "text": (
            "(In thousands, except per share data)\n"
            "Shares used for EPS | 2025 | 2024\n"
            "Diluted earnings per share | $2.69 | $2.18\n"
            "See notes.\n"
            "(In millions)\n"
            "Total net sales | 2025 | 2024\n"
            "Total net sales | $416,161 | $391,035\n"
        ),
    }
    engine = GraphQueryEngine(builder=_build(chunk))
    assert engine.get_metric_value("X", "Net Sales", 2025)["unit"] == "USD_M"
    assert engine.get_metric_value("X", "Diluted EPS", 2025)["unit"] == "USD_TH"


def test_apple_style_compound_unit_line_means_millions():
    # "(In millions, except shares reflected in thousands...)" — the FIRST
    # phrase is the primary unit of the statement.
    chunk = {
        "id": "AAPL_2025_10K:Item8:c000",
        "ticker": "AAPL",
        "fiscal_year": 2025,
        "item": "8",
        "text": (
            "(In millions, except number of shares, which are reflected in "
            "thousands, and per-share amounts)\n"
            "September 27, 2025 | September 28, 2024\n"
            "Total net sales | 416,161 | 391,035\n"
        ),
    }
    engine = GraphQueryEngine(builder=_build(chunk))
    assert engine.get_metric_value("AAPL", "Net Sales", 2025)["unit"] == "USD_M"


def test_parenthesized_values_are_negative():
    chunk = {
        "id": "X_2025_10K:Item8:c001",
        "ticker": "X",
        "fiscal_year": 2025,
        "text": "2025 | 2024\nNet income | $(1,234) | $500",
    }
    engine = GraphQueryEngine(builder=_build(chunk))
    assert engine.get_metric_value("X", "Net Income", 2025)["value"] == -1234.0
    assert engine.get_metric_value("X", "Net Income", 2024)["value"] == 500.0


def test_multi_value_row_without_year_header_is_skipped():
    # Honesty rule: never guess which column belongs to which year.
    chunk = {
        "id": "X_2025_10K:Item8:c002",
        "ticker": "X",
        "fiscal_year": 2025,
        "text": "Total net sales | $100 | $90 | $80",
    }
    builder = FinancialGraphBuilder()
    assert builder.ingest_chunk(chunk) == 0


def test_single_value_without_header_falls_back_to_filing_year():
    chunk = {
        "id": "X_2025_10K:Item7:c000",
        "ticker": "X",
        "fiscal_year": 2025,
        "text": "Free cash flow was reported as:\nFree cash flow | $12,345",
    }
    engine = GraphQueryEngine(builder=_build(chunk))
    row = engine.get_metric_value("X", "Free Cash Flow", 2025)
    assert row is not None and row["value"] == 12345.0


def test_provenance_edges_point_to_source_chunk():
    builder = _build()
    value_nodes = [n for n, d in builder.graph.nodes(data=True) if d.get("label") == "MetricValue"]
    assert value_nodes
    for vn in value_nodes:
        assert builder.graph.has_edge(vn, "chunk:AAPL_2025_10K:Item8:c007")


def test_duplicate_extraction_keeps_first_value():
    builder = FinancialGraphBuilder()
    builder.ingest_chunk(STATEMENT_CHUNK)
    dup = {**STATEMENT_CHUNK, "id": "AAPL_2025_10K:Item7:c099"}
    builder.ingest_chunk(dup)
    engine = GraphQueryEngine(builder=builder)
    row = engine.get_metric_value("AAPL", "Net Sales", 2025)
    assert row["chunk_id"] == "AAPL_2025_10K:Item8:c007"


def test_statement_values_outrank_mda_values():
    builder = FinancialGraphBuilder()
    mda = {
        "id": "X_2025_10K:Item7:c001",
        "ticker": "X",
        "fiscal_year": 2025,
        "item": "7",
        "text": "2025 | 2024\nNet income | $11 | $9",
    }
    stmt = {
        "id": "X_2025_10K:Item8:c001",
        "ticker": "X",
        "fiscal_year": 2025,
        "item": "8",
        "text": "2025 | 2024\nNet income | $11,000 | $9,000",
    }
    builder.ingest_chunk(mda)  # MD&A first...
    builder.ingest_chunk(stmt)  # ...statements must win anyway
    engine = GraphQueryEngine(builder=builder)
    row = engine.get_metric_value("X", "Net Income", 2025)
    assert row["value"] == 11000.0
    assert row["chunk_id"] == "X_2025_10K:Item8:c001"


def test_anchored_matching_rejects_ratio_rows():
    chunk = {
        "id": "X_2025_10K:Item7:c002",
        "ticker": "X",
        "fiscal_year": 2025,
        "item": "7",
        "text": "2025 | 2024\nPercentage of total net sales | 8 | 7",
    }
    builder = FinancialGraphBuilder()
    assert builder.ingest_chunk(chunk) == 0


def test_group_label_splitting_a_table_keeps_year_context():
    # Real pattern: "Revenue:" group labels have no pipe and split the
    # statement into blocks; the year header above must still apply.
    chunk = {
        "id": "MSFT_2025_10K:Item8:c000",
        "ticker": "MSFT",
        "fiscal_year": 2025,
        "item": "8",
        "text": (
            "INCOME STATEMENTS (In millions)\n"
            "Year Ended June 30, | 2025 | 2024 | 2023\n"
            "Revenue:\n"
            "Product | $63,946 | $64,773 | $64,699\n"
            "Total revenue | 281,724 | 245,122 | 211,915\n"
        ),
    }
    engine = GraphQueryEngine(builder=_build(chunk))
    row = engine.get_metric_value("MSFT", "Total Revenue", 2025)
    assert row is not None and row["value"] == 281724.0


# ------------------------------------------------------------- communities


def test_louvain_communities_group_cooccurring_entities():
    chunks = [
        {
            "id": f"A_{i}",
            "ticker": "AAPL",
            "fiscal_year": 2025,
            "text": "Total net sales and net income grew.",
        }
        for i in range(3)
    ] + [
        {
            "id": f"M_{i}",
            "ticker": "MSFT",
            "fiscal_year": 2025,
            "text": "Research and development expense rose.",
        }
        for i in range(3)
    ]
    builder = FinancialGraphBuilder()
    comms = builder.build_communities(chunks)
    assert comms, "expected at least one community"
    all_members = {m for c in comms for m in c["members"]}
    assert "company:AAPL" in all_members and "company:MSFT" in all_members
    assert all(c["n_chunks"] >= 1 for c in comms)


def test_community_search_matches_keywords():
    builder = FinancialGraphBuilder()
    builder.communities = [
        {
            "id": "community:0",
            "members": ["company:AAPL", "metric:Net Sales"],
            "size": 2,
            "n_chunks": 5,
            "chunk_ids": ["c1"],
            "summary": None,
        },
    ]
    engine = GraphQueryEngine(builder=builder)
    hits = engine.community_search("apple net sales trajectory")
    assert hits and hits[0]["id"] == "community:0"


# ------------------------------------------------------------ persistence


def test_save_load_roundtrip_preserves_facts_and_communities(tmp_path):
    builder = _build()
    builder.build_communities([STATEMENT_CHUNK])
    path = tmp_path / "g.json"
    builder.save(path)

    loaded = FinancialGraphBuilder.load(path)
    engine = GraphQueryEngine(builder=loaded)
    assert engine.get_metric_value("AAPL", "Net Sales", 2025)["value"] == 416161.0
    assert loaded.communities == builder.communities


def test_load_missing_file_returns_empty_builder(tmp_path):
    builder = FinancialGraphBuilder.load(tmp_path / "nope.json")
    assert builder.graph.number_of_nodes() == 0


# ------------------------------------------------------------ query engine


def test_compare_metrics_across_companies():
    builder = FinancialGraphBuilder()
    builder.ingest_chunk(STATEMENT_CHUNK)
    builder.ingest_chunk(
        {
            "id": "MSFT_2025_10K:Item8:c001",
            "ticker": "MSFT",
            "fiscal_year": 2025,
            "text": "2025\nTotal net sales | $281,724",
        }
    )
    engine = GraphQueryEngine(builder=builder)
    rows = engine.compare_metrics(["AAPL", "MSFT"], "net sales", 2025)
    values = {r["ticker"]: r["value"] for r in rows}
    assert values["AAPL"] == 416161.0
    assert values["MSFT"] == 281724.0
