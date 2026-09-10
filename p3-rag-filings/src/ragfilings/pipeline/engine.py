"""Core Grounded RAG Pipeline Engine.

Single responsibility: orchestrates confidence gating, context assembly,
prompt dispatch via LLM clients, JSON response extraction, and deterministic
verification with corrective retries.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from ..domains import DomainPack, get_pack
from ..llm import BaseLLMClient, complete_with_resilience, get_llm_client
from ..retrieval import Index, confidence, embed_text, load_index

logger = logging.getLogger(__name__)


class GenerationError(RuntimeError):
    """The model never produced parseable JSON, even after a reformat retry."""


def _parse_json(text: str) -> dict[str, Any] | None:
    """Tolerantly extract and parse a JSON object from model prose."""
    clean_text = text
    if "```json" in clean_text:
        clean_text = clean_text.split("```json")[1].split("```")[0]
    elif "```" in clean_text:
        clean_text = clean_text.split("```")[1].split("```")[0]

    start, end = clean_text.find("{"), clean_text.rfind("}")
    if start == -1 or end <= start:
        return None
    snippet = clean_text[start : end + 1]
    data = None
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError:
        cleaned_snippet = re.sub(r',\s*([\]\}])', r'\1', snippet)
        cleaned_snippet = re.sub(r'//[^\n]*', '', cleaned_snippet)
        try:
            data = json.loads(cleaned_snippet)
        except json.JSONDecodeError:
            try:
                import ast

                data = ast.literal_eval(cleaned_snippet)
            except Exception:
                m = re.search(
                    r'"(?:answer|result|value|output|percentage_change|change)"\s*:\s*(?:"([^"]*)"?|([^,\n}]+))',
                    snippet,
                )
                if m:
                    ans_val = (m.group(1) or m.group(2) or "").strip()
                    if ans_val and ans_val != "null":
                        return {"answer": ans_val, "citations": [], "reason": None}
                return None

    if not isinstance(data, dict):
        return None
    if "answer" in data:
        return data
    for k in ("result", "final_answer", "response", "output", "value", "percentage_change", "change"):
        if k in data:
            data["answer"] = data[k]
            data.setdefault("citations", [])
            data.setdefault("reason", None)
            return data
    return None


def _complete(
    messages: list[dict[str, str]],
    cfg: dict[str, Any],
    model: str | None = None,
    client: BaseLLMClient | None = None,
) -> tuple[str, dict[str, Any]]:
    """Chat completion entry point (OpenRouter). Tests monkeypatch this."""
    return complete_with_resilience(messages, cfg, model=model, client=client)


# The generation model is supposed to refuse via answer=null, but free models
# often emit the refusal as prose in the answer field instead. Treat the
# common shapes as refusals so graph rescue still gets a chance.
_REFUSAL_MARKERS = (
    "do not contain",
    "does not contain",
    "do not include",
    "does not include",
    "not provided in",
    "not present in",
    "not directly stated",
    "no context chunks",
    "none of the provided",
    "cannot find",
    "could not find",
    "cannot answer",
    "unable to answer",
    "cannot determine",
    "unable to determine",
    "not stated in",
    "not mentioned in",
    "not disclosed in",
    "does not provide",
    "do not provide",
    "is not available",
    "not available in",
)


def _is_refusal_text(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in _REFUSAL_MARKERS)


def _query_to_dict(q: Any) -> dict[str, Any]:
    """Domain-agnostic serialization of a rescue query (dataclass or dict)."""
    if isinstance(q, dict):
        return q
    return {k: getattr(q, k) for k in getattr(q, "__dataclass_fields__", {})}


def _is_real_answer(data: dict[str, Any]) -> bool:
    ans = data.get("answer")
    return ans is not None and not _is_refusal_text(str(ans))


def answer(
    query: str,
    hits: list[dict[str, Any]],
    cfg: dict[str, Any],
    client: BaseLLMClient | None = None,
    graph_rescue: Any = None,
    pack: DomainPack | None = None,
) -> dict[str, Any]:
    """Execute grounded answer synthesis with verification and confidence gating.

    Domain-specific behavior (prompts, derivation tool, claim semantics) comes
    from ``pack`` (defaults to the financial pack). When ``graph_rescue`` is
    provided, a deterministic fact lookup runs up front; for a clean-scope
    question the exact figure(s) and their provenance chunks are added to the
    context before synthesis, so a retrieval miss can cause neither a refusal
    nor a wrong-metric answer. If the model still does not give a grounded
    answer, synthesis is retried once.
    """
    pack = pack or get_pack("financial")
    conf = confidence(hits)
    min_confidence = cfg.get("verification", {}).get("min_confidence", 0.35)

    usage: dict[str, float | int] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "calls": 0,
    }

    # An under-specified question (missing fiscal year, a vague metric term,
    # or no company at all) is met with a deterministic clarifying question
    # rather than a guess — guessing is how ambiguous questions get scored
    # wrong.
    if graph_rescue is not None:
        clarification = graph_rescue.clarification(query)
        if clarification is not None:
            return {
                "refused": False,
                "refusal_reason": None,
                "answer": clarification,
                "citations": [],
                "invalid_citations": [],
                "verification": {"verified": True, "claims": []},
                "confidence": conf,
                "usage": usage,
                "math_result": None,
                "graph_rescue": {"clarification": True},
                "hits": hits,
            }

    if conf < min_confidence:
        return {
            "refused": True,
            "refusal_reason": f"low retrieval confidence: {conf:.3f} < {min_confidence}",
            "answer": None,
            "citations": [],
            "invalid_citations": [],
            "verification": {"verified": True, "claims": []},
            "confidence": conf,
            "usage": usage,
            "hits": hits,
        }

    math_res = None
    if pack.needs_decomposition(query):
        math_res = pack.compute(query, [h["chunk"] for h in hits], cfg, client=client)
        if math_res:
            for k in ("input_tokens", "output_tokens", "cost_usd"):
                usage[k] += math_res["usage"].get(k, 0)
            usage["calls"] += math_res["usage"].get("calls", 1)

    llm_client = client or get_llm_client(cfg=cfg)
    verify_retries = cfg.get("generation", {}).get("verify_retries", 1)

    def _synthesize(
        active_hits: list[dict[str, Any]],
        graph_block: str | None,
        math_result: dict[str, Any] | None,
        derived_values: list[float] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """One grounded synthesis pass (with verification retries).

        Returns (parsed_data, verification) — verification is None when the
        model refused.
        """
        context = "\n\n".join(
            f"[{h['chunk']['id']}]\n{embed_text(h['chunk'])}" for h in active_hits
        )
        if math_result:
            context += (
                f"\n\n[PYTHON_MATH_TOOL_VERIFIED_RESULT]\n"
                f"Calculated {math_result['explanation']}: {math_result['formatted']} "
                f"(Formula: {math_result['expression']})"
            )
        if graph_block:
            context += f"\n\n{graph_block}"

        msgs = [
            {"role": "system", "content": pack.prompt("synthesis")},
            {"role": "user", "content": f"Context chunks:\n\n{context}\n\nQuestion: {query}"},
        ]

        def _call_model() -> dict[str, Any]:
            nonlocal msgs
            for attempt in range(2):
                text, u = _complete(msgs, cfg, client=llm_client)
                for k in ("input_tokens", "output_tokens", "cost_usd"):
                    usage[k] += u.get(k, 0)
                usage["calls"] += 1

                data = _parse_json(text)
                if data is not None:
                    msgs = msgs + [{"role": "assistant", "content": text}]
                    return data

                if attempt == 0:
                    msgs = msgs + [
                        {"role": "assistant", "content": text},
                        {
                            "role": "user",
                            "content": (
                                'Reply with ONLY a valid JSON object matching:\n'
                                '{"answer": "<exact_number_or_null>", "citations": ["<chunk_id>"], "reason": null}'
                            ),
                        },
                    ]
                else:
                    clean = text.strip()
                    if clean:
                        m = re.search(
                            r'"(?:answer|result|value|output|percentage_change|change)"\s*:\s*(?:"([^"]*)"?|([^,\n}]+))',
                            clean,
                        )
                        if m:
                            ans_val = (m.group(1) or m.group(2) or "").strip()
                            if ans_val.lower() in ("null", "none", ""):
                                return {
                                    "answer": None,
                                    "citations": [],
                                    "reason": "model refused in raw json",
                                }
                            return {
                                "answer": ans_val,
                                "citations": [h["chunk"]["id"] for h in active_hits[:1]],
                                "reason": None,
                            }
                        # Soft fallback for concluding financial prose with numeric answer
                        if not any(
                            marker in clean.lower()
                            for marker in ("no json", "invalid", "error", '"answer": null', '"answer":null')
                        ):
                            num_match = re.search(r'([-+]?\$?\d[\d,]*(?:\.\d+)?%?)', clean)
                            if num_match and any(
                                word in clean.lower()
                                for word in ("is", "was", "increase", "decrease", "change", "total", "percent")
                            ):
                                return {
                                    "answer": clean,
                                    "citations": [h["chunk"]["id"] for h in active_hits[:1]],
                                    "reason": None,
                                }

            raise GenerationError("model did not return parseable JSON after retry")

        by_id = {h["chunk"]["id"]: h["chunk"] for h in active_hits}
        data = _call_model()
        retries = verify_retries

        while True:
            if data.get("answer") is None:
                return data, {"verified": True, "claims": []}

            raw_citations = [c for c in data.get("citations") or [] if isinstance(c, str)]
            valid = [c for c in raw_citations if c in by_id]
            invalid = [c for c in raw_citations if c not in by_id]
            cited = [by_id[c] for c in valid] or [h["chunk"] for h in active_hits]

            checked = pack.verify(
                str(data["answer"]),
                cited,
                math_result=math_result,
                derived_values=derived_values,
                query=query,
            )
            checked["citations"] = valid
            checked["invalid_citations"] = invalid
            if checked["verified"] or retries <= 0:
                return data, checked

            retries -= 1
            failed_claims = [c["raw"] for c in checked["claims"] if not c["found"]]
            msgs = msgs + [
                {
                    "role": "user",
                    "content": pack.format_prompt(
                        "verification_retry", failed_claims=failed_claims
                    ),
                }
            ]
            data = _call_model()

    # --- deterministic graph augmentation ---------------------------------
    # For a clean-scope question (complete ticker+metric+year, no qualifier)
    # the fact graph is authoritative, so surface its figures and provenance
    # chunks BEFORE synthesis. Rescue-on-refusal alone is unreliable here:
    # free models do not consistently self-refuse — sometimes they answer with
    # a wrong-but-related metric instead. Injecting the grounded fact up front
    # means a retrieval miss can cause neither a refusal nor a wrong answer.
    rescue_meta: dict[str, Any] | None = None
    aug_hits, aug_block, aug_derived = hits, None, None
    outcome = graph_rescue.rescue(query) if graph_rescue is not None else None
    if outcome is not None:
        seen = {h["chunk"]["id"] for h in hits}
        extra = [
            {"chunk": c, "score": conf, "dense_sim": conf}
            for c in outcome.chunks
            if c["id"] not in seen
        ]
        aug_hits = hits + extra
        aug_block = outcome.facts_block
        aug_derived = outcome.derived_values
        rescue_meta = {
            "queries": [_query_to_dict(q) for q in outcome.queries],
            "facts": outcome.facts,
            "chunks_added": [c["chunk"]["id"] for c in extra],
            "rescued": False,
        }

    data, checked = _synthesize(aug_hits, aug_block, math_res, derived_values=aug_derived)

    if outcome is not None:
        hits = aug_hits
        if _is_real_answer(data):
            rescue_meta["rescued"] = True
        else:
            # Grounded facts are already in context; one retry leverages
            # free-model non-determinism before giving up.
            retry_data, retry_checked = _synthesize(
                aug_hits, aug_block, math_res, derived_values=aug_derived
            )
            if _is_real_answer(retry_data):
                data, checked = retry_data, retry_checked
                rescue_meta["rescued"] = True
            else:
                data = retry_data  # keep the last refusal reason

    if not _is_real_answer(data):
        prose = str(data.get("answer")) if data.get("answer") is not None else None
        reason = data.get("reason") or prose or "not answerable"
        return {
            "refused": True,
            "refusal_reason": f"model: {reason}",
            "answer": None,
            "citations": [],
            "invalid_citations": [],
            "verified": False,
            "verification": {"verified": True, "claims": []},
            "confidence": conf,
            "usage": usage,
            "math_result": math_res,
            "graph_rescue": rescue_meta,
            "hits": hits,
        }

    return {
        "refused": False,
        "refusal_reason": None,
        "answer": str(data["answer"]),
        "citations": checked["citations"],
        "invalid_citations": checked["invalid_citations"],
        "verified": bool(checked.get("verified", False) and not checked.get("invalid_citations")),
        "verification": checked,
        "confidence": conf,
        "usage": usage,
        "math_result": math_res,
        "graph_rescue": rescue_meta,
        "hits": hits,
    }


def split_graph_strategy(strategy: str) -> tuple[str, bool]:
    """`hybrid_rerank_graph` -> ("hybrid_rerank", True): base retrieval plus
    deterministic fact-graph augmentation of the synthesis context."""
    if strategy.endswith("_graph"):
        return strategy[: -len("_graph")], True
    return strategy, False


def log_refusal(path: str | Path, query: str, result: dict[str, Any], strategy: str) -> None:
    """Persist refusal event for analysis."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "query": query,
                    "strategy": strategy,
                    "reason": result.get("refusal_reason"),
                    "confidence": result.get("confidence"),
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def ask(
    query: str,
    cfg: dict[str, Any],
    index: Index | None = None,
    strategy: str | None = None,
    refusal_log: str | Path = "reports/refusals.jsonl",
    filters: dict[str, Any] | None = None,
    domain: str = "financial",
    top_k: int | None = None,
    memory: Any = None,
) -> dict[str, Any]:
    """End-to-end RAG pipeline execution for one domain pack."""
    pack = get_pack(domain)
    if index is None:
        index = load_index(cfg["embedding"]["index_dir"], cfg["embedding"]["model"])

    strat = strategy or cfg.get("retrieval", {}).get("strategy", "dense")
    base_strat, use_graph = split_graph_strategy(strat)

    if base_strat == "agent_react":
        from .orchestrator import MultiAgentOrchestrator

        orch = MultiAgentOrchestrator(cfg, memory=memory)
        res = orch.run(query, index, strategy="hybrid_rerank")
        res["strategy"] = "agent_react"
        res["model"] = cfg.get("generation", {}).get("model", "")
        if res.get("refused"):
            log_refusal(refusal_log, query, res, strat)
        return res

    rescuer = None
    if use_graph:
        rescuer = pack.load_rescue(cfg, index)

    t0 = time.perf_counter()
    effective_top_k = top_k if top_k is not None else cfg.get("retrieval", {}).get("top_k", 8)
    rerank_candidates = cfg.get("retrieval", {}).get("rerank_candidates", 25)

    if pack.needs_decomposition(query):
        sub_queries = pack.decompose_query(query, cfg)
        hits: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for sq in sub_queries:
            sq_hits = index.search(
                sq,
                base_strat,
                effective_top_k,
                filters=filters,
                rerank_candidates=rerank_candidates,
                reranker_name=cfg.get("retrieval", {}).get("reranker"),
            )
            for h in sq_hits:
                cid = h["chunk"]["id"]
                if cid not in seen_ids:
                    hits.append(h)
                    seen_ids.add(cid)
        hits = sorted(hits, key=lambda x: x["score"], reverse=True)[:effective_top_k]
    else:
        hits = index.search(
            query,
            base_strat,
            effective_top_k,
            filters=filters,
            rerank_candidates=rerank_candidates,
            reranker_name=cfg.get("retrieval", {}).get("reranker"),
        )

    result = answer(query, hits, cfg, graph_rescue=rescuer, pack=pack)
    result["latency_ms"] = (time.perf_counter() - t0) * 1000.0
    result["strategy"] = strat
    result["hits"] = result.pop("hits", hits)
    result["model"] = cfg.get("generation", {}).get("model", "")

    if result.get("refused"):
        log_refusal(refusal_log, query, result, strat)

    return result
