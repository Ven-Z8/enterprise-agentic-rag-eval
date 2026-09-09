"""Python Financial Math Tool.

Executes exact Python mathematical calculations (growth rates, deltas, percentages, CAGRs)
using safe AST evaluation to eliminate LLM arithmetic errors on 10-K financial tables.
"""

from __future__ import annotations

import ast
import json
import operator
from typing import Any

from ...llm import complete_with_resilience
from ...llm.base import BaseLLMClient
from ...prompts import PromptRegistry

_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expr: str) -> float:
    """Safely evaluate a mathematical Python expression using AST parsing."""

    def _eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        elif isinstance(node, ast.BinOp):
            op = _SAFE_OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported operator: {type(node.op)}")
            return float(op(_eval_node(node.left), _eval_node(node.right)))
        elif isinstance(node, ast.UnaryOp):
            op = _SAFE_OPERATORS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op)}")
            return float(op(_eval_node(node.operand)))
        else:
            raise ValueError(f"Unsupported AST node: {type(node)}")

    parsed = ast.parse(expr, mode="eval")
    return _eval_node(parsed.body)


def compute_financial_math(
    query: str,
    chunks: list[dict[str, Any]],
    cfg: dict[str, Any],
    client: BaseLLMClient | None = None,
) -> dict[str, Any] | None:
    """Extract arithmetic expression and evaluate using safe AST interpreter."""
    context = "\n".join(c.get("text", "") for c in chunks[:8])
    messages = [
        {"role": "system", "content": PromptRegistry.get_math_tool()},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
    ]

    try:
        text, usage = complete_with_resilience(messages, cfg, client=client, role="runtime")
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            data = json.loads(text[start : end + 1])
            expr = data.get("expression", "")
            if expr:
                val = safe_eval(expr)
                is_pct = any(
                    k in query.lower()
                    for k in (
                        "growth",
                        "percent",
                        "margin",
                        "cagr",
                        "rate",
                        "share",
                        "portion",
                        "ratio",
                    )
                )
                if is_pct and 0 < abs(val) <= 1.0 and "* 100" not in expr and "*100" not in expr:
                    val_pct = val * 100
                else:
                    val_pct = val

                formatted_str = f"{val_pct:.2f}%" if is_pct else f"{val:,.2f}"
                return {
                    "expression": expr,
                    "result_value": round(val_pct, 4),
                    "raw_value": round(val, 4),
                    "formatted": formatted_str,
                    "explanation": data.get("explanation", ""),
                    "usage": usage,
                }
    except Exception:
        pass

    return None
