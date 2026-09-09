"""Tests for LLM OpenRouter Subsystem."""

import pytest

from ragfilings.llm import (
    BaseLLMClient,
    ChatMessage,
    LLMFactory,
    LLMResponse,
    OpenRouterClient,
    TokenUsage,
    get_llm_client,
)


def test_chat_message_and_token_usage_models():
    msg = ChatMessage(role="user", content="Hello")
    assert msg.to_dict() == {"role": "user", "content": "Hello"}
    assert ChatMessage.from_dict({"role": "system", "content": "Rule"}).role == "system"

    usage = TokenUsage(input_tokens=100, output_tokens=50, cost_usd=0.005)
    assert usage.to_dict()["cost_usd"] == 0.005

    resp = LLMResponse(content="Answer", usage=usage, model="test-model")
    assert resp.cost_usd == 0.005
    assert resp.content == "Answer"


def test_openrouter_client_initialization():
    or_client = OpenRouterClient(api_key="sk-or-test", default_model="test-model")
    assert or_client.provider_name == "openrouter"
    assert or_client.default_model == "test-model"
    assert or_client.is_available()


def test_normalize_messages():
    msgs = [
        ChatMessage(role="system", content="Sys"),
        {"role": "user", "content": "Usr"},
    ]
    norm = BaseLLMClient.normalize_messages(msgs)
    assert norm == [
        {"role": "system", "content": "Sys"},
        {"role": "user", "content": "Usr"},
    ]

    with pytest.raises(ValueError):
        BaseLLMClient.normalize_messages(["invalid string message"])  # type: ignore


def test_factory_client_creation():
    client = LLMFactory.create_client(default_model="test-model")
    assert isinstance(client, OpenRouterClient)
    assert client.default_model == "test-model"


def test_get_llm_client_helper():
    client = get_llm_client()
    assert isinstance(client, OpenRouterClient)


def test_luna_request_omits_unsupported_temperature():
    from types import SimpleNamespace
    requests = []

    def complete(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))],
                               usage=None)

    client = OpenRouterClient(api_key='sk-or-test', default_model='openai/gpt-5.6-luna')
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
    client.complete([{'role': 'user', 'content': 'hello'}], max_tokens=128)
    assert 'temperature' not in requests[0]
    assert requests[0]['max_tokens'] == 128


def test_is_transient_error_classification():
    from ragfilings.llm.factory import is_transient_error

    class FakeStatusError(Exception):
        def __init__(self, status_code):
            self.status_code = status_code

    assert is_transient_error(FakeStatusError(429)) is True
    assert is_transient_error(FakeStatusError(503)) is True
    assert is_transient_error(FakeStatusError(400)) is False
    assert is_transient_error(FakeStatusError(401)) is False
    assert is_transient_error(FakeStatusError(402)) is False
    assert is_transient_error(ConnectionError("Connection aborted")) is True
    assert is_transient_error(ValueError("Bad payload")) is False


def test_complete_with_resilience_fails_fast_on_400():
    from ragfilings.llm.factory import complete_with_resilience

    class FakeClient:
        def __init__(self):
            self.calls = 0

        def complete(self, **kwargs):
            self.calls += 1
            err = Exception("Bad request")
            err.status_code = 400
            raise err

    fake = FakeClient()
    with pytest.raises(Exception) as excinfo:
        complete_with_resilience([{"role": "user", "content": "hi"}], cfg={}, client=fake)

    assert excinfo.value.status_code == 400
    assert fake.calls == 1  # No retries on 400!
