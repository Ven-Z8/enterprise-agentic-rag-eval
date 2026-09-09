"""Build a standard Trace (traces/trace.py format) from a raw adapter result.

The metric layer scores Traces, never raw agent output — so anything a metric
might need (tool calls, retries, citations, cost, latency) lives here.
"""

from __future__ import annotations

from typing import Any


def build_trace(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Emit a trace dictionary in the standard format (Trace.from_dict-compatible)."""
    hits = result.get("hits", [])
    ver = result.get("verification", {"verified": True, "claims": []})
    final = (
        result.get("answer")
        if not result.get("refused")
        else f"[REFUSED] {result.get('refusal_reason')}"
    )
    steps = [
        {
            "index": 0,
            "kind": "tool_call",
            "content": None,
            "retry_of": None,
            "tool_call": {
                "name": "retrieve",
                "arguments": {
                    "query": case["input"],
                    "strategy": result.get("strategy", ""),
                    "top_k": len(hits),
                },
                "result": [
                    {"id": h["chunk"]["id"], "score": h["score"], "dense_sim": h["dense_sim"]}
                    for h in hits
                ],
                "error": None,
                "latency_ms": None,
            },
        },
        {
            "index": 1,
            "kind": "tool_call",
            "content": None,
            "retry_of": None,
            "tool_call": {
                "name": "verify_claims",
                "arguments": {"n_claims": len(ver.get("claims", []))},
                "result": {
                    "verified": ver.get("verified", True),
                    "failed": [c["raw"] for c in ver.get("claims", []) if not c.get("found", True)],
                },
                "error": None,
                "latency_ms": None,
            },
        },
        {
            "index": 2,
            "kind": "response",
            "content": final,
            "tool_call": None,
            "retry_of": None,
        },
    ]
    rescue = result.get("graph_rescue")
    if rescue:
        steps.insert(
            1,
            {
                "index": 1,
                "kind": "tool_call",
                "content": None,
                "retry_of": None,
                "tool_call": {
                    "name": "graph_rescue",
                    "arguments": {"queries": rescue.get("queries", [])},
                    "result": {
                        "facts": rescue.get("facts", []),
                        "chunks_added": rescue.get("chunks_added", []),
                        "rescued": rescue.get("rescued", False),
                    },
                    "error": None,
                    "latency_ms": None,
                },
            },
        )
        for i, step in enumerate(steps):
            step["index"] = i
    u = result.get("usage", {})
    return {
        "case_id": case["id"],
        "input": case["input"],
        "final_output": final or "",
        "steps": steps,
        "citations": list(result.get("citations", [])),
        "usage": {
            "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0),
            "cost_usd": u.get("cost_usd", 0.0),
        },
        "latency_ms": result.get("latency_ms", 0.0),
        "model": result.get("model", ""),
        "metadata": {
            "adapter": "ragfilings-v1",
            "strategy": result.get("strategy", ""),
            "refused": result.get("refused", False),
            "refusal_reason": result.get("refusal_reason"),
            "confidence": result.get("confidence"),
            "invalid_citations": result.get("invalid_citations", []),
            "verification_verified": ver.get("verified", True),
            "golden_verification": (
                case.get("golden_verification")
                or case.get("provenance")
                or ("v1 proven" if str(case.get("id", "")).startswith("fin-") else "diagnostic")
            ),
            "graph_rescue": (
                {
                    "rescued": result["graph_rescue"].get("rescued", False),
                    "chunks_added": result["graph_rescue"].get("chunks_added", []),
                }
                if result.get("graph_rescue")
                else None
            ),
        },
    }
