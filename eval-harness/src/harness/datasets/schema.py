"""Golden dataset schema (v0). Frozen contract — shared with P3 (p3-rag-filings).

One JSONL file, one TestCase per line. This module is the source of truth for the
format; the human-readable spec lives next to it in SCHEMA.md. If the format must
change, change it HERE first, then propagate to P3's golden/schema.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Enums kept as plain tuples so validate() can check membership without extra deps.
EXPECTED_TYPES = ("exact", "contains", "judge")
DIFFICULTIES = ("easy", "medium", "hard")
FAILURE_CATEGORIES = ("lookup", "synthesis", "table", "unanswerable", "ambiguous")


@dataclass
class Expected:
    answer: str | None  # None => unanswerable/ambiguous: the agent MUST refuse or clarify
    citations: list[str]  # e.g. ["AAPL_2025_10K:Item7"] — filing + section
    type: str  # one of EXPECTED_TYPES


@dataclass
class TestCase:
    __test__ = False
    id: str  # e.g. "fin-0001" — stable forever once assigned
    input: str
    expected: Expected
    variation_rules: list[str]  # e.g. ["numeric_tolerance:0.5%", "unit_equivalence"]
    difficulty: str  # one of DIFFICULTIES
    failure_category: str  # one of FAILURE_CATEGORIES
    domain: str  # "financial" | "legal" | "support" | ...
    notes: str = ""  # why this case exists / what it's designed to catch

    @classmethod
    def from_dict(cls, d: dict) -> TestCase:
        return cls(
            id=d["id"],
            input=d["input"],
            expected=Expected(
                answer=d["expected"]["answer"],
                citations=d["expected"].get("citations", []),
                type=d["expected"]["type"],
            ),
            variation_rules=d.get("variation_rules", []),
            difficulty=d["difficulty"],
            failure_category=d["failure_category"],
            domain=d["domain"],
            notes=d.get("notes", ""),
        )


def load_jsonl(path: str | Path) -> list[TestCase]:
    """Load and validate a golden set. Raises ValueError on the first bad case."""
    cases: list[TestCase] = []
    seen: set[str] = set()
    for lineno, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            case = TestCase.from_dict(json.loads(line))
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"{path}:{lineno}: cannot parse test case: {e}") from e
        for problem in validate(case):
            raise ValueError(f"{path}:{lineno} ({case.id}): {problem}")
        if case.id in seen:
            raise ValueError(f"{path}:{lineno}: duplicate id {case.id}")
        seen.add(case.id)
        cases.append(case)
    return cases


def validate(case: TestCase) -> list[str]:
    """Return a list of human-readable problems (empty == valid)."""
    problems: list[str] = []
    if case.expected.type not in EXPECTED_TYPES:
        problems.append(f"expected.type {case.expected.type!r} not in {EXPECTED_TYPES}")
    if case.difficulty not in DIFFICULTIES:
        problems.append(f"difficulty {case.difficulty!r} not in {DIFFICULTIES}")
    if case.failure_category not in FAILURE_CATEGORIES:
        problems.append(f"failure_category {case.failure_category!r} not in {FAILURE_CATEGORIES}")
    # Unanswerable/ambiguous cases assert a refusal: answer must be null.
    if case.failure_category in ("unanswerable", "ambiguous") and case.expected.answer is not None:
        problems.append(f"{case.failure_category} case must have expected.answer = null")
    # exact/contains scoring needs a ground-truth string (unless it's a refusal case).
    if case.expected.type in ("exact", "contains") and case.expected.answer is None:
        if case.failure_category not in ("unanswerable", "ambiguous"):
            problems.append(f"type {case.expected.type!r} requires a non-null expected.answer")
    return problems
