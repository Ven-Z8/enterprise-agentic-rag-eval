"""DeepEval metric layer with an OpenRouter judge.

Every DeepEval metric runs through OpenRouterJudge, which routes judge calls
through the harness's own OpenRouter client — never through deepeval's
built-in providers. Token usage and cost are the API-reported numbers,
accumulated in a per-run ledger, so eval overhead is visible in the same
accounting as generation.

Metrics used by the harness:
- correctness (G-Eval): judge-type cases, factual equivalence vs expected
- faithfulness: claims in the answer supported by retrieved chunks
- answer_relevancy: does the answer address the question
- contextual_precision: are the golden-citation chunks ranked first

Deterministic checks (exact/contains numeric matching, refusal correctness)
stay in metrics/engine.py; DeepEval scores complement them, they do not
replace ground truth.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval.metrics import (  # noqa: E402
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    FaithfulnessMetric,
    GEval,
)
from deepeval.models import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase, SingleTurnParams  # noqa: E402

from harness.llm import complete_with_resilience  # noqa: E402

CORRECTNESS_CRITERIA = (
    "Determine whether the ACTUAL OUTPUT is factually equivalent to the "
    "EXPECTED OUTPUT for the given INPUT question about SEC 10-K filings. "
    "Equivalent means: the same key figures (tolerate rounding and unit "
    "re-expression such as $1.0B vs $1,000 million), the same direction of "
    "change where one is asked, and the same attribution/explanation where "
    "the expected output gives one. Wording differences are acceptable; "
    "missing, contradicting, or materially misstating a key fact is not."
)

CORRECTNESS_STEPS = [
    "Extract every quantitative claim from the expected output.",
    "Check each claim appears in the actual output within rounding or unit re-expression.",
    "Check the actual output does not contradict the expected output on direction or attribution.",
    "Return an integer score from 0 to 10 for factual equivalence (10 = fully equivalent, 0 = completely contradicts or unsupported).",
]


class JudgeLedger:
    """Accumulates real token usage and cost across all judge calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0

    def add(self, usage: dict[str, Any]) -> None:
        self.calls += 1
        self.input_tokens += usage.get("input_tokens", 0)
        self.output_tokens += usage.get("output_tokens", 0)
        self.cost_usd += usage.get("cost_usd", 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "judge_calls": self.calls,
            "judge_input_tokens": self.input_tokens,
            "judge_output_tokens": self.output_tokens,
            "judge_cost_usd": round(self.cost_usd, 6),
        }


class OpenRouterJudge(DeepEvalBaseLLM):
    """DeepEval judge backed by the harness's OpenRouter client."""

    def __init__(self, cfg: dict[str, Any]):
        self._cfg = cfg
        self._model_name = cfg.get("judge", {}).get("model")
        self._max_tokens = cfg.get("judge", {}).get("max_tokens", 1500)
        self.ledger = JudgeLedger()
        super().__init__(model=self._model_name)

    def load_model(self) -> "OpenRouterJudge":
        return self

    def get_model_name(self) -> str:
        return self._model_name or "openrouter"

    @staticmethod
    def _extract_json(content: str) -> str:
        """Models often fence or pad JSON even when told not to; unwrap it so
        deepeval's verdict parsers accept the response."""
        text = content.strip()
        if fence := re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL):
            text = fence.group(1).strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass
        return content

    def generate(self, prompt: str, schema: Any = None, **kwargs: Any) -> str:
        messages: list[dict[str, str]] = []
        if schema is not None:
            try:
                js = json.dumps(schema.model_json_schema())
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Reply with ONLY a JSON object matching this JSON "
                            f"schema. No prose.\n{js}"
                        ),
                    }
                )
            except Exception:
                pass
        messages.append({"role": "user", "content": prompt})
        content, usage = complete_with_resilience(
            messages, model=self._model_name, max_tokens=self._max_tokens
        )
        self.ledger.add(usage)
        if schema is not None:
            content = self._extract_json(content)
        return content

    async def a_generate(self, prompt: str, schema: Any = None, **kwargs: Any) -> str:
        return await asyncio.to_thread(self.generate, prompt, schema=schema, **kwargs)


def build_metrics(judge: OpenRouterJudge) -> dict[str, Any]:
    """The metric set applied to every answered case (async off: sequential,
    deterministic temperature, costs attributed in call order)."""
    return {
        "correctness": GEval(
            name="Correctness",
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.EXPECTED_OUTPUT,
            ],
            criteria=CORRECTNESS_CRITERIA,
            evaluation_steps=CORRECTNESS_STEPS,
            model=judge,
            threshold=0.5,
            async_mode=False,
        ),
        "faithfulness": FaithfulnessMetric(
            model=judge, threshold=0.5, async_mode=False, include_reason=False
        ),
        "answer_relevancy": AnswerRelevancyMetric(
            model=judge, threshold=0.5, async_mode=False, include_reason=False
        ),
        "contextual_precision": ContextualPrecisionMetric(
            model=judge, threshold=0.5, async_mode=False, include_reason=False
        ),
    }


def make_test_case(case: dict[str, Any], result: dict[str, Any]) -> LLMTestCase:
    retrieval_context = [h["chunk"]["text"] for h in result.get("hits", [])]
    expected_output = case["expected"].get("answer") or ""
    if case.get("notes"):
        expected_output = f"{expected_output}\nRubric notes: {case['notes']}".strip()
    return LLMTestCase(
        input=case["input"],
        actual_output=result.get("answer") or "",
        expected_output=expected_output,
        retrieval_context=retrieval_context,
    )


def score_with_deepeval(
    case: dict[str, Any],
    result: dict[str, Any],
    metrics: dict[str, Any],
    include_correctness: bool = True,
) -> dict[str, Any]:
    """Run the DeepEval metric set on one answered case.

    Metrics that cannot be computed (missing inputs, provider error) are
    reported as None with a `<name>_error` note instead of failing the run —
    the deterministic score in metrics/engine.py remains authoritative.
    """
    tc = make_test_case(case, result)
    out: dict[str, Any] = {}
    for name, metric in metrics.items():
        if name == "correctness" and not include_correctness:
            continue
        try:
            metric.measure(tc)
            out[name] = metric.score
        except Exception as e:  # metric-level failure must not kill the run
            out[name] = None
            out[f"{name}_error"] = f"{type(e).__name__}: {e}"[:300]
    return out


class DeepEvalScorer:
    """Facade used by the runner: judge + metric set + scoring entry points."""

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.judge = OpenRouterJudge(cfg)
        self._metrics = build_metrics(self.judge)

    def _expected_output(self, case: dict[str, Any]) -> str:
        if case["expected"].get("answer") is None and case["failure_category"] == "ambiguous":
            return (
                "The system should NOT commit to one interpretation. It should "
                "ask for clarification or explicitly present the possible "
                f"interpretations. {case.get('notes', '')}"
            )
        return case["expected"].get("answer") or ""

    def correctness(self, case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        """G-Eval factual-equivalence verdict (also used for ambiguous cases,
        where the expected output describes correct clarifying behavior)."""
        metric = self._metrics["correctness"]
        tc = make_test_case(case, result)
        tc.expected_output = self._expected_output(case)
        try:
            metric.measure(tc)
            score = metric.score
            return {
                "correct": bool(score is not None and score >= 0.5),
                "score": score,
                "reason": getattr(metric, "reason", "") or "",
            }
        except Exception as e:
            return {"correct": False, "score": None,
                    "reason": f"judge failed: {type(e).__name__}: {e}"[:300]}

    def metrics(self, case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        """Faithfulness / relevancy / contextual precision for an answered case."""
        if not result.get("answer"):
            return {}
        return score_with_deepeval(case, result, self._metrics, include_correctness=False)
