"""Agent package — planner, synthesis, auditor.

Each agent is a real LLM step: instructor-validated structured outputs
with API-reported usage accounting.
"""

from .auditor import audit_answer
from .planner import corpus_inventory, plan_query
from .synthesis import synthesize

__all__ = [
    "plan_query",
    "corpus_inventory",
    "synthesize",
    "audit_answer",
]

