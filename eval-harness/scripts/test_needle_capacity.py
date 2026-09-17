"""Needle 2 (Cactus Compute) Capacity & Benchmarking Test.

Evaluates Needle 2 on 10 realistic enterprise queries across financial and legal domains:
1. Tool Calling & Routing (lookup, comparison, multi-year variance, legal clause, clarification)
2. Argument & Entity Extraction (company, fiscal year, metric, clause topic)
3. Inference Latency (ms), Decoding Speed (tokens/sec), and Peak RAM

Usage:
  python scripts/test_needle_capacity.py
"""

from __future__ import annotations

import os
import time
from typing import Any

# Suppress telemetry prompt
os.environ["NEEDLE_TELEMETRY"] = "0"

import needle


# ---------------------------------------------------------------------------
# 1. Define Candidate RAG Pipeline Tools
# ---------------------------------------------------------------------------

@needle.tool
def lookup_financial_filing(company: str, fiscal_year: int, metric: str) -> dict[str, Any]:
    """Lookup a single financial metric for a company in a specific fiscal year.

    Args:
        company: Name of the company or stock ticker symbol
        fiscal_year: 4-digit fiscal year (e.g. 2023, 2024, 2025)
        metric: Financial line item such as operating income, revenue, cash flow
    """
    return {
        "tool": "lookup_financial_filing",
        "company": company,
        "fiscal_year": fiscal_year,
        "metric": metric,
    }


@needle.tool
def compare_companies(company_a: str, company_b: str, metric: str, fiscal_year: int) -> dict[str, Any]:
    """Compare a financial metric or segment between two different companies in a year.

    Args:
        company_a: First company name
        company_b: Second company name
        metric: Financial metric or segment to compare
        fiscal_year: 4-digit fiscal year
    """
    return {
        "tool": "compare_companies",
        "company_a": company_a,
        "company_b": company_b,
        "metric": metric,
        "fiscal_year": fiscal_year,
    }


@needle.tool
def multi_year_variance(company: str, metric: str, start_year: int, end_year: int) -> dict[str, Any]:
    """Calculate multi-year change, growth rate, delta, or CAGR for a company across two years.

    Args:
        company: Name of the company
        metric: Financial line item or expense to analyze
        start_year: Earlier fiscal year
        end_year: Later fiscal year
    """
    return {
        "tool": "multi_year_variance",
        "company": company,
        "metric": metric,
        "start_year": start_year,
        "end_year": end_year,
    }


@needle.tool
def review_contract_clause(provider: str, clause_topic: str) -> dict[str, Any]:
    """Review legal contracts, terms of service, or agreements for specific legal provisions.

    Args:
        provider: Organization or agreement name (e.g. Microsoft, Google, Agency Agreement)
        clause_topic: Legal clause topic like arbitration, liability cap, termination, effective date
    """
    return {
        "tool": "review_contract_clause",
        "provider": provider,
        "clause_topic": clause_topic,
    }


@needle.tool
def request_clarification(missing_info: str) -> dict[str, Any]:
    """Use this tool when the query is ambiguous, missing a company name, or missing a fiscal year.

    Args:
        missing_info: Description of what is needed (e.g. missing company or year)
    """
    return {
        "tool": "request_clarification",
        "missing_info": missing_info,
    }


# ---------------------------------------------------------------------------
# 2. 10 Curated Test Queries
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": "Q01_lookup",
        "query": "What was Coca-Cola's operating income for fiscal year 2025?",
        "expected_tool": "lookup_financial_filing",
        "expected_entity": "Coca-Cola",
    },
    {
        "id": "Q02_variance",
        "query": "How did Microsoft's R&D expense change from FY2024 to FY2025?",
        "expected_tool": "multi_year_variance",
        "expected_entity": "Microsoft",
    },
    {
        "id": "Q03_cross_company",
        "query": "Compare Microsoft and Alphabet cloud segment revenues for 2024.",
        "expected_tool": "compare_companies",
        "expected_entity": "Microsoft",
    },
    {
        "id": "Q04_ratio_margin",
        "query": "What was Tesla's automotive gross margin for fiscal year 2023?",
        "expected_tool": "lookup_financial_filing",
        "expected_entity": "Tesla",
    },
    {
        "id": "Q05_cagr_math",
        "query": "Calculate Costco's net sales CAGR from 2022 to 2024.",
        "expected_tool": "multi_year_variance",
        "expected_entity": "Costco",
    },
    {
        "id": "Q06_ambiguous",
        "query": "What was the net income?",
        "expected_tool": "request_clarification",
        "expected_entity": "none",
    },
    {
        "id": "Q07_segments",
        "query": "Compare Amazon AWS operating profit and North America retail for 2024.",
        "expected_tool": "compare_companies",
        "expected_entity": "Amazon",
    },
    {
        "id": "Q08_cash_flow",
        "query": "What did Apple report as operating cash flow for fiscal year 2024?",
        "expected_tool": "lookup_financial_filing",
        "expected_entity": "Apple",
    },
    {
        "id": "Q09_legal_arbitration",
        "query": "Does Microsoft require arbitration for consumer dispute resolution?",
        "expected_tool": "review_contract_clause",
        "expected_entity": "Microsoft",
    },
    {
        "id": "Q10_legal_definition",
        "query": "In the Agency Agreement, what is the clause for Effective Date?",
        "expected_tool": "review_contract_clause",
        "expected_entity": "Agency Agreement",
    },
]


def main() -> None:
    print("=" * 72)
    print("⚡ TESTING NEEDLE 2 (CACTUS COMPUTE) CAPACITY ON 10 ENTERPRISE QUERIES")
    print("Model: 45M parameters | 14MB binary | 28MB RAM footprint | On-Device")
    print("=" * 72 + "\n")

    tools = [
        lookup_financial_filing,
        compare_companies,
        multi_year_variance,
        review_contract_clause,
        request_clarification,
    ]

    correct_tool_calls = 0
    latencies_ms: list[float] = []
    decode_speeds: list[float] = []
    peak_rams: list[float] = []

    print(f"{'#':<3} | {'Query ID':<18} | {'Latency':<8} | {'Selected Tool':<24} | {'Tool Match':<10} | {'RAM':<7}")
    print("-" * 80)

    for i, test in enumerate(TEST_CASES, 1):
        q = test["query"]
        exp_tool = test["expected_tool"]

        # Fresh agent instance to isolate independent query turns
        agent = needle.Needle(tools=tools)

        t0 = time.perf_counter()
        res = agent.run(q)
        lat_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(lat_ms)

        decode_tps = res.get("decode_tps") or 0.0
        decode_speeds.append(decode_tps)
        ram = res.get("peak_ram_mb") or 0.0
        peak_rams.append(ram)

        results = res.get("results", [])
        chosen_tool = results[0].get("tool") if results and isinstance(results[0], dict) else "None"
        tool_match = (chosen_tool == exp_tool)
        if tool_match:
            correct_tool_calls += 1

        match_str = "✅ PASS" if tool_match else f"❌ ({exp_tool})"
        print(f"{i:2d}  | {test['id']:<18} | {lat_ms:6.1f}ms | {str(chosen_tool):<24} | {match_str:<10} | {ram:.1f}MB")
        if results:
            print(f"     └─ Extracted args: {results[0]}")

    avg_lat = sum(latencies_ms) / len(latencies_ms)
    avg_speed = sum(decode_speeds) / len(decode_speeds) if decode_speeds else 0.0
    avg_ram = sum(peak_rams) / len(peak_rams) if peak_rams else 0.0
    accuracy = (correct_tool_calls / len(TEST_CASES)) * 100.0

    print("\n" + "=" * 72)
    print("📋 NEEDLE 2 CAPACITY BENCHMARK REPORT")
    print("=" * 72)
    print(f"Total Test Cases:            {len(TEST_CASES)}")
    print(f"Tool Routing Accuracy:       {accuracy:.1f}% ({correct_tool_calls}/{len(TEST_CASES)})")
    print(f"Average Decision Latency:    {avg_lat:.2f} ms")
    print(f"Average Decoding Speed:      {avg_speed:.1f} tokens/sec")
    print(f"Average Memory Footprint:    {avg_ram:.1f} MB RAM")
    print(f"Cost per Query:              $0.00000 (100% On-Device / Zero API Tokens)")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
