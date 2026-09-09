"""Domain-pack tests for the harness.

Pre-rebuild this file tested Gemini facade adapters that returned the golden
answer on error; those were removed in the integrity audit. The harness now
runs real domains through the p3 engine via RAGFilingsAdapter(domain=...).
These tests verify the shipped golden datasets and the domain wiring without
touching the (index-requiring) adapters.
"""

from pathlib import Path

from harness.cli import DOMAIN_DATA
from harness.datasets.schema import load_jsonl

P1_ROOT = Path(__file__).resolve().parents[1]


def test_shipped_domains_have_data_dirs():
    for domain, dirname in DOMAIN_DATA.items():
        assert (P1_ROOT / "data" / dirname).is_dir(), f"{domain} data dir missing"


def test_financial_golden_sets_load():
    cases = load_jsonl(str(P1_ROOT / "data/domain_a_financial/golden_set_v1.jsonl"))
    assert len(cases) == 50
    assert all(c.domain == "financial" for c in cases)


def test_legal_golden_set_loads():
    path = P1_ROOT / "data/domain_b_legal/golden_set_legal_v1.jsonl"
    assert path.exists(), "run scripts/build_golden_legal_v1.py first"
    cases = load_jsonl(str(path))
    assert len(cases) >= 50
    assert all(c.domain == "legal" for c in cases)
    assert all(c.id.startswith("leg-") for c in cases)
    # unanswerable/ambiguous must assert refusal (schema enforces null answer)
    cats = {c.failure_category for c in cases}
    assert {"lookup", "synthesis", "unanswerable", "ambiguous"} <= cats


def test_unknown_domain_rejected():
    import pytest

    from harness.cli import _adapter_for

    with pytest.raises(SystemExit):
        _adapter_for("klingon", None)
