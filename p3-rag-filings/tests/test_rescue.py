"""Tests for the deterministic graph-rescue layer and its engine wiring."""

import json

from ragfilings.graph import FinancialGraphBuilder, GraphQueryEngine
from ragfilings.graph.rescue import (
    GraphRescue,
    RescueQuery,
    _derived_values,
    _find_years,
    _format_fact,
    _strip_years,
    load_excluded_facts,
)
from ragfilings.tools.verification import verify
from ragfilings.llm.base import BaseLLMClient
from ragfilings.llm.types import LLMResponse, TokenUsage
from ragfilings.pipeline.engine import answer, split_graph_strategy

# A consolidated-statement chunk; the graph extracts one fact per
# (ticker, metric, year) with provenance back to this chunk id.
STATEMENT_CHUNK = {
    "id": "AAPL_2025_10K:Item8:c007",
    "ticker": "AAPL",
    "fiscal_year": 2025,
    "section_id": "Item8",
    "item": "8",
    "text": (
        "CONSOLIDATED STATEMENTS OF OPERATIONS (In millions)\n"
        "Three fiscal years ended | 2025 | 2024 | 2023\n"
        "Total net sales | $416,161 | $391,035 | $383,285\n"
        "Net income | $112,010 | $93,736 | $96,995\n"
    ),
}
DECOY_CHUNK = {
    "id": "AAPL_2025_10K:Item1:c000",
    "ticker": "AAPL",
    "fiscal_year": 2025,
    "text": "The company designs and sells consumer electronics.",
}

ALIASES = {
    "AAPL": ["apple", "aapl"],
    "MSFT": ["microsoft", "msft"],
    "META": ["meta platforms", "meta"],
}

CFG = {
    "generation": {"model": "test/model", "max_tokens": 512, "verify_retries": 1},
    "verification": {"min_confidence": 0.35},
}


def _engine():
    builder = FinancialGraphBuilder()
    builder.ingest_chunk(STATEMENT_CHUNK)
    return GraphQueryEngine(builder=builder)


def _rescuer(excluded=frozenset()):
    return GraphRescue(
        engine=_engine(),
        chunks_by_id={STATEMENT_CHUNK["id"]: STATEMENT_CHUNK},
        company_aliases=ALIASES,
        excluded=excluded,
        company_names={"AAPL": "Apple", "MSFT": "Microsoft",
                       "META": "Meta Platforms"},
    )


# ------------------------------------------------------------- extraction

def test_extract_simple_lookup():
    q = _rescuer().extract_queries("What was Apple's total net sales for fiscal year 2025?")
    assert q == [RescueQuery("AAPL", "Net Sales", 2025)]


def test_extract_comparison_yields_one_query_per_company():
    q = _rescuer().extract_queries(
        "Which company reported higher net income in fiscal year 2025: Apple or Microsoft?"
    )
    assert q is not None
    assert sorted(x.ticker for x in q) == ["AAPL", "MSFT"]
    assert all(x.metric == "Net Income" and x.fiscal_year == 2025 for x in q)


def test_extract_year_over_year_change_yields_one_query_per_year():
    q = _rescuer().extract_queries(
        "How did Apple's net income change from fiscal year 2024 to fiscal year 2025?"
    )
    assert q is not None
    assert sorted(x.fiscal_year for x in q) == [2024, 2025]
    assert all(x.ticker == "AAPL" and x.metric == "Net Income" for x in q)


def test_extract_aborts_on_subperiod_qualifier():
    assert _rescuer().extract_queries(
        "What was Apple's net income for the first quarter of 2025?") is None


def test_extract_aborts_on_residual_qualifier():
    assert _rescuer().extract_queries(
        "What was Apple's iPhone net income for fiscal year 2025?") is None


def test_extract_aborts_on_single_word_metric():
    # Bare "revenue" is too broad for rescue scope (would match sub-segments).
    assert _rescuer().extract_queries(
        "How much revenue did Apple generate in fiscal year 2025?") is None


def test_extract_aborts_without_company_or_year():
    r = _rescuer()
    assert r.extract_queries("What was total net sales for fiscal year 2025?") is None
    assert r.extract_queries("What was Apple's total net sales?") is None


# ----------------------------------------------------------------- lookup

def test_rescue_returns_fact_and_provenance_chunk():
    out = _rescuer().rescue("What was Apple's net income for fiscal year 2025?")
    assert out is not None
    assert out.facts[0]["value"] == 112010.0
    assert out.facts[0]["metric"] == "Net Income"
    assert out.chunks == [STATEMENT_CHUNK]
    assert out.chunk_ids == [STATEMENT_CHUNK["id"]]
    assert "AAPL Net Income FY2025" in out.facts_block
    assert STATEMENT_CHUNK["id"] in out.facts_block


def test_rescue_skips_excluded_facts():
    r = _rescuer(excluded=frozenset({"val:AAPL:net_income:2025"}))
    assert r.rescue("What was Apple's net income for fiscal year 2025?") is None
    # A non-excluded metric for the same company still resolves.
    assert r.rescue("What was Apple's total net sales for fiscal year 2025?") is not None


def test_rescue_returns_none_when_year_not_in_graph():
    assert _rescuer().rescue("What was Apple's net income for fiscal year 2019?") is None


def test_format_fact_units():
    assert _format_fact({"value": 153463.0, "unit": "USD_M", "metric": "Gross Profit"}) \
        == "$153,463 million"
    assert _format_fact({"value": 7.17, "unit": "USD_M", "metric": "Diluted EPS"}) == "$7.17"
    assert _format_fact({"value": 46.9, "unit": "PCT", "metric": "Gross Margin"}) == "46.9%"
    assert _format_fact({"value": 5.2, "unit": "USD_B", "metric": "Net Income"}) \
        == "$5.2 billion"


def test_load_excluded_facts_reads_committed_file():
    excluded = load_excluded_facts()
    assert isinstance(excluded, frozenset)
    assert "val:AMZN:operating_expenses:2025" in excluded


def test_split_graph_strategy():
    assert split_graph_strategy("hybrid_rerank_graph") == ("hybrid_rerank", True)
    assert split_graph_strategy("hybrid_rerank") == ("hybrid_rerank", False)
    assert split_graph_strategy("dense_graph") == ("dense", True)


# -------------------------------------------------------- derived values

def _fact(ticker, metric, year, value, unit="USD_M"):
    return {"ticker": ticker, "metric": metric, "fiscal_year": str(year),
            "value": value, "unit": unit}


def test_derived_values_year_over_year_change():
    facts = [_fact("META", "Free Cash Flow", 2024, 52103.0),
             _fact("META", "Free Cash Flow", 2025, 43585.0)]
    dv = _derived_values(facts)
    exp_delta = abs(43585.0 - 52103.0)
    exp_pct = exp_delta / 52103.0 * 100.0
    assert any(abs(x - exp_delta) < 1e-6 for x in dv)        # absolute delta
    assert any(abs(x - exp_pct) < 1e-6 for x in dv)          # absolute % change


def test_derived_values_cross_company_difference():
    facts = [_fact("MSFT", "Operating Income", 2024, 109433.0),
             _fact("TSLA", "Operating Income", 2024, 7076.0)]
    dv = _derived_values(facts)
    assert any(abs(x - 102357.0) < 1e-6 for x in dv)


def test_derived_values_empty_for_single_fact():
    assert _derived_values([_fact("AAPL", "Net Income", 2025, 112010.0)]) == []


def test_verify_accepts_derived_percent_and_difference():
    chunk = {"id": "c0", "text": "Free cash flow | $52,103 | $43,585"}
    res = verify("It fell to $43,585 million from $52,103 million, a 16.3% decrease.",
                 [chunk], derived_values=[8518.0, 16.3136])
    assert res["verified"]
    res2 = verify("The difference is $102,357 million.", [chunk],
                  derived_values=[102357.0])
    assert res2["verified"]


def test_verify_still_rejects_ungrounded_derived_claim():
    chunk = {"id": "c0", "text": "Free cash flow | $52,103 | $43,585"}
    res = verify("It fell by 42.0%.", [chunk], derived_values=[16.3136])
    assert not res["verified"]


# ----------------------------------------------------------- multi-hop

def test_rescue_ratio_margin():
    out = _rescuer().rescue("What was Apple's net profit margin in fiscal year 2025?")
    assert out is not None
    assert len(out.facts) == 2  # net income + net sales
    ratio = out.derived_values[0]
    assert abs(ratio - 112010 / 416161 * 100) < 1e-6


def test_rescue_ratio_with_definitional_parenthetical():
    out = _rescuer().rescue(
        "What was Apple's net profit margin (net income as a percentage of "
        "revenue) in fiscal year 2025?")
    assert out is not None
    assert len(out.facts) == 2


def test_rescue_cagr():
    out = _rescuer().rescue(
        "What was the compound annual growth rate (CAGR) of Apple's net sales "
        "from fiscal year 2023 to 2025?")
    assert out is not None
    assert len(out.facts) == 2
    expected = ((416161 / 383285) ** 0.5 - 1) * 100
    assert any(abs(v - expected) < 1e-6 for v in out.derived_values)


def test_rescue_trend_expands_year_range():
    out = _rescuer().rescue(
        "What was the trend in Apple's net income from fiscal year 2023 to 2025?")
    assert out is not None
    # endpoints expanded to the full inclusive range 2023, 2024, 2025
    assert len(out.facts) == 3


def test_rescue_ratio_change_two_years():
    out = _rescuer().rescue(
        "How did Apple's net profit margin change from fiscal year 2024 to 2025?")
    assert out is not None
    assert len(out.facts) == 4  # net income + net sales for both years


def test_rescue_ratio_abstains_on_qualifier():
    out = _rescuer().rescue(
        "What was Apple's segment net profit margin in fiscal year 2025?")
    assert out is None


def test_rescue_cagr_abstains_on_subperiod():
    out = _rescuer().rescue(
        "What was the CAGR of Apple's net sales for the first quarter of 2025?")
    assert out is None


def test_rescue_ratio_outcome_grounds_derived_ratio_line():
    out = _rescuer().rescue("What was Apple's net profit margin in fiscal year 2025?")
    assert out is not None
    lines = [ln for ln in out.facts_block.splitlines() if "(derived:" in ln]
    assert len(lines) == 1
    assert "net profit margin FY2025" in lines[0]
    assert "26.9%" in lines[0]  # 112,010 / 416,161
    assert STATEMENT_CHUNK["id"] in lines[0]


def test_rescue_cagr_outcome_grounds_derived_line():
    out = _rescuer().rescue(
        "What was the CAGR of Apple's net sales from fiscal year 2023 to 2025?")
    assert out is not None
    lines = [ln for ln in out.facts_block.splitlines() if "(derived:" in ln]
    assert len(lines) == 1
    assert "CAGR FY2023→FY2025" in lines[0]
    assert "4.2%" in lines[0]


def test_rescue_ratio_aborts_when_denominator_excluded():
    # A poisoned revenue fact (see corpus/graph/excluded_facts.json) must
    # abort the ratio rescue, never feed a garbage denominator.
    r = _rescuer(excluded=frozenset({"val:AAPL:net_sales:2025"}))
    assert r.rescue("What was Apple's net profit margin in fiscal year 2025?") is None


# ------------------------------------------------------- clarification

def test_clarification_fires_on_missing_year():
    clar = _rescuer().missing_year_clarification("What was Apple's net sales?")
    assert clar is not None
    assert "Apple" in clar
    assert "net sales" in clar
    assert "which fiscal year" in clar.lower()


def test_clarification_abstains_when_year_present():
    clar = _rescuer().missing_year_clarification(
        "What was Apple's net sales for fiscal year 2025?")
    assert clar is None


def test_clarification_abstains_on_unrecognized_metric():
    # "cash" is not a recognized statement phrase, so no clarification
    assert _rescuer().missing_year_clarification(
        "How much cash does Apple have?") is None


def test_clarification_abstains_on_multiple_companies():
    assert _rescuer().missing_year_clarification(
        "Which company had higher net income, Apple or Microsoft?") is None


def test_clarification_change_intent_asks_for_period():
    clar = _rescuer().missing_year_clarification(
        "How did Apple's net sales change?")
    assert clar is not None
    assert "between which fiscal years" in clar.lower()


def test_clarification_asks_about_peers_when_peers_unspecified():
    clar = _rescuer().missing_year_clarification(
        "What was Apple's net income relative to its peers?")
    assert clar is not None
    assert "fiscal year" in clar
    assert "peer" in clar


def test_clarification_no_peers_clause_without_peer_qualifier():
    clar = _rescuer().missing_year_clarification("What was Apple's net sales?")
    assert clar is not None
    assert "peer" not in clar


def test_vague_metric_clarification_fires_with_year():
    clar = _rescuer().vague_metric_clarification(
        "What was Microsoft's earnings in fiscal year 2025?")
    assert clar is not None
    assert "ambiguous" in clar
    assert "Microsoft" in clar
    assert "fiscal year 2025" in clar


def test_vague_metric_clarification_cash_without_year():
    clar = _rescuer().vague_metric_clarification("How much cash does Apple have?")
    assert clar is not None
    assert "ambiguous" in clar
    assert "fiscal year" in clar
    assert "cash & cash equivalents" in clar


def test_vague_metric_clarification_abstains_on_anchor_phrase():
    r = _rescuer()
    assert r.vague_metric_clarification(
        "What was Apple's free cash flow in fiscal year 2025?") is None
    assert r.vague_metric_clarification(
        "What did Apple report as diluted earnings per share for fiscal year 2025?") is None
    # a vague term modifying a recognized metric is not a vague reference
    assert r.vague_metric_clarification(
        "What was Apple's revenue growth rate in fiscal year 2025?") is None


def test_vague_metric_clarification_abstains_on_cagr():
    assert _rescuer().vague_metric_clarification(
        "What was the compound annual growth rate of Apple's total net sales "
        "from fiscal year 2023 to fiscal year 2025?") is None


def test_no_company_clarification_fires_without_company_or_year():
    r = _rescuer()
    clar = r.no_company_clarification("Which company had the highest net income?")
    assert clar is not None
    assert "net income" in clar
    assert r.no_company_clarification("What was the net income?") is not None


def test_no_company_clarification_abstains_with_year_company_or_no_metric():
    r = _rescuer()
    assert r.no_company_clarification(
        "What was the net income in fiscal year 2025?") is None
    assert r.no_company_clarification("What was Apple's net income?") is None
    assert r.no_company_clarification("What is the capital of France?") is None


def test_clarification_entry_point_routes_and_abstains():
    r = _rescuer()
    # missing-year shape wins...
    assert r.clarification("What was Apple's net sales?") == \
        r.missing_year_clarification("What was Apple's net sales?")
    # ...vague-metric shape is next...
    assert r.clarification(
        "What was Microsoft's earnings in fiscal year 2025?") is not None
    # ...and a fully-scoped question reaches synthesis untouched.
    assert r.clarification(
        "What was Apple's total net sales for fiscal year 2025?") is None


# --------------------------------------------------------- engine wiring

class MockLLMClient(BaseLLMClient):
    def __init__(self, replies):
        super().__init__()
        self.replies = list(replies)
        self.calls = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def complete(self, messages, model=None, max_tokens=1200, temperature=0.0, **kwargs):
        self.calls.append(messages)
        text = self.replies.pop(0)
        return LLMResponse(
            content=text,
            usage=TokenUsage(input_tokens=100, output_tokens=20, cost_usd=0.001),
            model="mock-model",
        )


def _reply(ans, citations=(), reason=None):
    return json.dumps({"answer": ans, "citations": list(citations), "reason": reason})


def _hits(chunk=DECOY_CHUNK, sim=0.8):
    return [{"chunk": chunk, "score": sim, "dense_sim": sim}]


def test_engine_rescues_refusal_and_answers():
    client = MockLLMClient([
        _reply(None, reason="figure not in context"),
        _reply("Total net sales were $416,161 million.",
               citations=("AAPL_2025_10K:Item8:c007",)),
    ])
    res = answer("What was Apple's total net sales for fiscal year 2025?",
                 _hits(), CFG, client=client, graph_rescue=_rescuer())
    assert not res["refused"]
    assert res["graph_rescue"]["rescued"] is True
    assert res["graph_rescue"]["chunks_added"] == ["AAPL_2025_10K:Item8:c007"]
    assert res["citations"] == ["AAPL_2025_10K:Item8:c007"]
    assert res["verification"]["verified"]
    assert "416,161" in res["answer"]
    assert len(client.calls) == 2


def test_engine_direct_answer_with_proactive_augmentation():
    # Retrieval already surfaced the provenance chunk; the graph fact is
    # injected up front but adds no NEW chunk, and the model answers directly.
    client = MockLLMClient([
        _reply("Total net sales were $416,161 million.",
               citations=("AAPL_2025_10K:Item8:c007",)),
    ])
    res = answer("What was Apple's total net sales for fiscal year 2025?",
                 _hits(chunk=STATEMENT_CHUNK), CFG, client=client, graph_rescue=_rescuer())
    assert not res["refused"]
    assert res["graph_rescue"]["rescued"] is True
    assert res["graph_rescue"]["chunks_added"] == []
    assert len(client.calls) == 1


def test_engine_rescue_aborts_on_qualifier_and_stays_refused():
    client = MockLLMClient([_reply(None, reason="not present")])
    res = answer("What was Apple's net income for the first quarter of 2025?",
                 _hits(), CFG, client=client, graph_rescue=_rescuer())
    assert res["refused"]
    assert res["graph_rescue"] is None
    assert len(client.calls) == 1


def test_engine_rescue_fires_but_model_still_refuses():
    client = MockLLMClient([
        _reply(None, reason="figure not in context"),
        _reply(None, reason="still cannot answer"),
    ])
    res = answer("What was Apple's total net sales for fiscal year 2025?",
                 _hits(), CFG, client=client, graph_rescue=_rescuer())
    assert res["refused"]
    assert res["graph_rescue"]["rescued"] is False
    assert len(client.calls) == 2


def test_engine_without_rescuer_keeps_refusal():
    client = MockLLMClient([_reply(None, reason="not present")])
    res = answer("What was Apple's total net sales for fiscal year 2025?",
                 _hits(), CFG, client=client, graph_rescue=None)
    assert res["refused"]
    assert res["graph_rescue"] is None
    assert len(client.calls) == 1


def test_engine_treats_refusal_prose_as_refusal_and_rescues():
    # Free models often put the refusal in the answer field instead of null.
    refusal_prose = ("The provided context chunks do not contain Apple's "
                     "total net sales for fiscal year 2025.")
    client = MockLLMClient([
        _reply(refusal_prose, citations=()),
        _reply("Total net sales were $416,161 million.",
               citations=("AAPL_2025_10K:Item8:c007",)),
    ])
    res = answer("What was Apple's total net sales for fiscal year 2025?",
                 _hits(), CFG, client=client, graph_rescue=_rescuer())
    assert not res["refused"]
    assert res["graph_rescue"]["rescued"] is True
    assert "416,161" in res["answer"]
    assert len(client.calls) == 2


def test_engine_refusal_prose_stays_refused_without_rescuer():
    refusal_prose = "The provided context chunks do not contain the figure."
    client = MockLLMClient([_reply(refusal_prose, citations=())])
    res = answer("What was Apple's total net sales for fiscal year 2025?",
                 _hits(), CFG, client=client, graph_rescue=None)
    assert res["refused"]
    assert res["answer"] is None
    assert "do not contain" in res["refusal_reason"]


def test_engine_real_answer_not_misclassified_as_refusal():
    # A plain grounded answer carries no refusal markers, so it must be
    # accepted on the first pass without a redundant retry.
    client = MockLLMClient([
        _reply("Total net sales were $416,161 million.",
               citations=("AAPL_2025_10K:Item8:c007",)),
    ])
    res = answer("What was Apple's total net sales for fiscal year 2025?",
                 _hits(chunk=STATEMENT_CHUNK), CFG, client=client, graph_rescue=_rescuer())
    assert not res["refused"]
    assert res["graph_rescue"]["rescued"] is True
    assert len(client.calls) == 1


# ------------------------------------------- FY-shorthand year handling

def test_find_years_sees_fy_shorthand():
    assert _find_years("What was Apple's net sales for FY2025?") == [2025]
    assert _find_years("from FY2023 to FY2025") == [2023, 2025]
    # "FY 2024" matches both the bare-year and FY patterns (callers dedupe)
    assert sorted(set(_find_years("FY 2024 vs FY25"))) == [2024, 2025]
    assert _find_years("for fiscal year 2024") == [2024]
    # no false positive on ordinary words ending in "fy" + a bare number
    assert _find_years("specify the metric for 2024") == [2024]


def test_strip_years_removes_fy_shorthand():
    assert "fy2025" not in _strip_years("net sales fy2025").lower()
    assert "2025" not in _strip_years("net sales for fiscal year 2025")


def test_clarification_abstains_on_fy_shorthand_year():
    assert _rescuer().missing_year_clarification(
        "What was Apple's net sales for FY2025?") is None


def test_clarification_abstains_on_fy_range_cagr():
    assert _rescuer().missing_year_clarification(
        "What was the CAGR of Apple net sales from FY2023 to FY2025?") is None


def test_clarification_cagr_without_years_asks_for_period():
    clar = _rescuer().missing_year_clarification(
        "What was Apple's net sales CAGR?")
    assert clar is not None
    assert "between which fiscal years" in clar.lower()


def test_extract_lookup_with_fy_shorthand():
    queries = _rescuer().extract_queries(
        "What was Apple's net sales for FY2025?")
    assert queries is not None
    assert (queries[0].ticker, queries[0].fiscal_year) == ("AAPL", 2025)


def test_rescue_cagr_with_fy_shorthand():
    out = _rescuer().rescue(
        "What was the CAGR of Apple net sales from FY2023 to FY2025?")
    assert out is not None
    assert len(out.facts) == 2
    expected = ((416161 / 383285) ** 0.5 - 1) * 100
    assert any(abs(v - expected) < 1e-6 for v in out.derived_values)


def test_rescue_ratio_with_fy_shorthand():
    out = _rescuer().rescue(
        "What was Apple's net profit margin in FY2025?")
    assert out is not None
    assert any(abs(v - 112010 / 416161 * 100) < 0.1 for v in out.derived_values)


def test_missing_year_clarification_recognizes_revenue():
    clar = _rescuer().missing_year_clarification("How much did Apple revenue grow?")
    assert clar is not None
    assert "between which fiscal years" in clar.lower()


def test_no_company_clarification_recognizes_operating_profit():
    clar = _rescuer().no_company_clarification("What was operating profit?")
    assert clar is not None
    assert "which company" in clar.lower()
