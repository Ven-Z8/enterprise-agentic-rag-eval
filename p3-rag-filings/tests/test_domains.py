"""Domain pack contract tests.

The engine is domain-agnostic: it may only depend on the DomainPack
interface, never on financial internals. These tests pin that contract and
prove the financial pack satisfies it with unchanged behavior.
"""

import pytest

from ragfilings.domains import DomainPack, available_packs, get_pack
from ragfilings.graph.rescue import GraphRescue
from ragfilings.tools.verification import verify


def test_financial_pack_satisfies_contract():
    pack = get_pack("financial")
    assert isinstance(pack, DomainPack)
    assert pack.name == "financial"
    assert pack.display_name == "SEC 10-K Filings"


def test_unknown_pack_rejected():
    with pytest.raises(ValueError, match="unknown domain pack"):
        get_pack("klingon")


def test_available_packs_lists_financial():
    assert "financial" in available_packs()


def test_pack_prompts_match_registry():
    from ragfilings.prompts import PromptRegistry

    pack = get_pack("financial")
    assert pack.prompt("synthesis") == PromptRegistry.get_system_synthesis()
    assert pack.format_prompt(
        "verification_retry", failed_claims=["$1M"]
    ) == PromptRegistry.get_verification_retry(["$1M"])


def test_pack_decomposition_delegates():
    pack = get_pack("financial")
    assert pack.needs_decomposition("What was the CAGR of Apple's net sales?")
    assert not pack.needs_decomposition("What was Apple's net income in 2025?")


def test_pack_verify_matches_claim_checker():
    chunk = {"id": "c0", "text": "Net sales | $416,161 | $391,035"}
    pack = get_pack("financial")
    assert pack.verify("Net sales were $416,161 million.", [chunk])["verified"]
    # identical result to calling the claim checker directly
    assert pack.verify("Net sales were $416,161 million.", [chunk]) == verify(
        "Net sales were $416,161 million.", [chunk]
    )


def test_pack_math_compute_delegates(monkeypatch):
    from ragfilings.tools import compute_financial_math

    pack = get_pack("financial")
    chunks = [{"id": "c0", "text": "Revenue | $100 | $80"}]
    cfg = {"generation": {"model": "test/model", "max_tokens": 256}}

    def fake_complete(messages, cfg_, model=None, client=None, role="generation"):
        assert role == "runtime"
        return (
            '{"explanation": "growth", "expression": "(100-80)/80*100", '
            '"result_value": 25.0, "formatted": "25.0%"}'
        ), {"calls": 1}

    import ragfilings.domains.financial.math_tool as mt

    monkeypatch.setattr(mt, "complete_with_resilience", fake_complete)
    out_pack = pack.compute("What was the revenue growth rate?", chunks, cfg)
    out_direct = compute_financial_math("What was the revenue growth rate?", chunks, cfg)
    assert out_pack == out_direct
    assert out_pack["result_value"] == 25.0


def test_pack_load_rescue_returns_scope_agent():
    """The pack's scope agent exposes clarification() and rescue()."""
    pack = get_pack("financial")
    # no corpus artifacts in the unit environment -> graceful None is fine,
    # but the call itself must not raise.
    rescuer = pack.load_rescue({}, None)
    if rescuer is not None:
        assert isinstance(rescuer, GraphRescue)
        assert callable(rescuer.clarification)
        assert callable(rescuer.rescue)
