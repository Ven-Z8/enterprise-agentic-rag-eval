"""Offline regression checks: distinct model roles and reranker switching."""

import sys
from types import SimpleNamespace

import pytest

from ragfilings import retrieval
from ragfilings.llm.factory import get_model_for_role


@pytest.mark.parametrize("role", ["planning", "runtime"])
def test_explicit_role_does_not_use_generator(role):
    cfg = {"generation": {"model": "generator"}, role: {"model": "selected"}}
    assert get_model_for_role(cfg, role) == "selected"


def test_legacy_judge_setting_is_resolved():
    cfg = {"generation": {"model": "generator"}, "eval": {"judge_model": "judge"}}
    assert get_model_for_role(cfg, "judge") == "judge"


def test_legacy_planning_uses_extraction():
    cfg = {"generation": {"model": "generator"}, "extraction": {"model": "extractor"}}
    assert get_model_for_role(cfg, "planning") == "extractor"


def test_switching_reranker_reloads_model(monkeypatch):
    monkeypatch.setattr(retrieval, "_reranker_model", None)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(CrossEncoder=lambda name: SimpleNamespace(name=name)),
    )
    first = retrieval._get_reranker("test/first")
    second = retrieval._get_reranker("test/second")
    assert first.name == "test/first"
    assert second.name == "test/second"
    assert retrieval._get_reranker("test/second") is second


def test_qwen_structured_requests_disable_thinking(monkeypatch):
    import instructor
    from pydantic import BaseModel

    from ragfilings.llm.openrouter import OpenRouterClient
    from ragfilings.llm.structured import complete_structured

    class Result(BaseModel):
        ok: bool

    captured = {}

    def complete(**kwargs):
        captured.update(kwargs)
        return Result(ok=True), SimpleNamespace(usage=None)

    fake = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create_with_completion=complete))
    )
    monkeypatch.setattr(instructor, "from_openai", lambda client: fake)
    client = OpenRouterClient(api_key="sk-or-test")
    client._client = object()
    complete_structured(
        [], Result, {"runtime": {"model": "qwen/qwen3.8-flash"}}, role="runtime", client=client
    )
    assert captured["extra_body"]["reasoning"] == {"enabled": False}


@pytest.mark.parametrize("decompose", [False, True])
def test_standard_pipeline_passes_configured_reranker(monkeypatch, decompose):
    from ragfilings.pipeline import engine

    calls = []

    def search(query, strategy, top_k, **kwargs):
        calls.append(kwargs.get("reranker_name"))
        return [{"chunk": {"id": "c1", "text": "evidence"}, "score": 0.9}]

    pack = SimpleNamespace(
        needs_decomposition=lambda query: decompose,
        decompose_query=lambda query, cfg: ["part one", "part two"],
    )
    monkeypatch.setattr(engine, "get_pack", lambda domain: pack)
    monkeypatch.setattr(
        engine, "answer", lambda *args, **kwargs: {"refused": False, "answer": "ok"}
    )
    engine.ask(
        "question",
        {"retrieval": {"reranker": "test/selected"}},
        index=SimpleNamespace(search=search),
        strategy="hybrid_rerank",
    )
    assert calls == ["test/selected"] * (2 if decompose else 1)
