"""Runnable check: `python tests/test_schema.py` (or pytest).

The headline assertion is the cross-project consistency check from the brief:
P1's schema must load P3's actual hand-authored golden skeleton unchanged.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from harness import TestCase, Trace, load_jsonl, validate  # noqa: E402
from harness.datasets.schema import Expected  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
P3_SKELETON = REPO.parent / "p3-rag-filings" / "golden" / "golden_set_skeleton.jsonl"


def test_loads_p3_skeleton():
    """The whole point of Phase 0: P3's file drops into P1 unchanged."""
    assert P3_SKELETON.exists(), f"P3 skeleton missing at {P3_SKELETON}"
    cases = load_jsonl(P3_SKELETON)
    assert len(cases) == 5
    ids = [c.id for c in cases]
    assert ids == ["fin-0001", "fin-0002", "fin-0003", "fin-0004", "fin-0005"]
    # fin-0004/0005 are the refusal cases → answer must be null.
    by_id = {c.id: c for c in cases}
    assert by_id["fin-0004"].expected.answer is None
    assert by_id["fin-0005"].failure_category == "ambiguous"


def _case(**over):
    base = dict(
        id="x-1",
        input="q",
        expected=Expected(answer="a", citations=[], type="exact"),
        variation_rules=[],
        difficulty="easy",
        failure_category="lookup",
        domain="test",
    )
    base.update(over)
    return TestCase(**base)


def test_validate_catches_bad_enum():
    assert validate(_case(difficulty="trivial"))  # non-empty == problems found
    assert validate(_case(failure_category="nope"))
    assert validate(_case(expected=Expected(answer="a", citations=[], type="fuzzy")))


def test_validate_enforces_refusal_invariant():
    # unanswerable with a non-null answer is illegal
    bad = _case(
        failure_category="unanswerable", expected=Expected(answer="42", citations=[], type="exact")
    )
    assert validate(bad)
    # unanswerable with null answer is fine
    ok = _case(
        failure_category="unanswerable", expected=Expected(answer=None, citations=[], type="exact")
    )
    assert not validate(ok)


def test_trace_roundtrips():
    t = Trace(case_id="fin-0001", input="q", final_output="a", citations=["AAPL_2025_10K:Item8"])
    t.usage.output_tokens = 12
    restored = Trace.from_dict(__import__("json").loads(t.to_json()))
    assert restored == t


def test_goldencase_pydantic_validation():
    import pytest
    from pydantic import ValidationError

    from harness.schema import ExpectedOutcome, GoldenCase

    # Bad enum difficulty
    with pytest.raises(ValidationError):
        GoldenCase(
            id="c1",
            input="q",
            expected=ExpectedOutcome(type="exact", answer="1"),
            difficulty="ultra",
            failure_category="lookup",
            domain="financial",
        )

    # Bad failure category
    with pytest.raises(ValidationError):
        GoldenCase(
            id="c1",
            input="q",
            expected=ExpectedOutcome(type="exact", answer="1"),
            difficulty="easy",
            failure_category="invalid_cat",
            domain="financial",
        )

    # Unanswerable with non-null answer
    with pytest.raises(ValidationError):
        GoldenCase(
            id="c1",
            input="q",
            expected=ExpectedOutcome(type="exact", answer="42"),
            difficulty="easy",
            failure_category="unanswerable",
            domain="financial",
        )

    # Ambiguous with non-null answer
    with pytest.raises(ValidationError):
        GoldenCase(
            id="c1",
            input="q",
            expected=ExpectedOutcome(type="judge", answer="42"),
            difficulty="easy",
            failure_category="ambiguous",
            domain="financial",
        )

    # Exact with null answer for lookup
    with pytest.raises(ValidationError):
        GoldenCase(
            id="c1",
            input="q",
            expected=ExpectedOutcome(type="exact", answer=None),
            difficulty="easy",
            failure_category="lookup",
            domain="financial",
        )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\nAll checks passed.")
