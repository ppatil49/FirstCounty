import dataclasses

import pytest

from config import Settings
from engine.llm import (
    LLMError, OpenAICompatibleClient, ReplayClient, ReplayStore, build_client, make_cache_key,
)


@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(Settings.load(), replay_dir=tmp_path / "cache", record_replay=True)


def with_provider(settings, provider, model="m"):
    return dataclasses.replace(settings, llm_provider=provider, llm_model=model)


def test_replay_provider_needs_no_key(settings):
    assert isinstance(build_client(with_provider(settings, "replay")), ReplayClient)


def test_ollama_needs_no_key(settings):
    c = build_client(with_provider(settings, "ollama", "qwen2.5:7b"))
    assert isinstance(c, OpenAICompatibleClient) and c.provider == "ollama"


def test_gemini_requires_key(settings, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        build_client(with_provider(settings, "gemini"))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert build_client(with_provider(settings, "gemini")).provider == "gemini"


def test_azure_requires_endpoint_and_key(settings, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(LLMError, match="AZURE_OPENAI_ENDPOINT"):
        build_client(with_provider(settings, "azure_openai", "my-deployment"))
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    assert build_client(with_provider(settings, "azure_openai", "my-deployment")).provider == "azure_openai"


def test_unknown_provider_rejected(settings):
    with pytest.raises(LLMError, match="Unknown LLM_PROVIDER"):
        build_client(with_provider(settings, "nope"))


def test_replay_returns_saved_response_and_errors_on_miss(settings):
    store = ReplayStore(settings.replay_dir)
    key = make_cache_key("v1", "Earn 4.25%!")
    store.save(key, {"provider": "gemini", "model": "g", "response": '{"findings": []}'})
    client = ReplayClient(store)
    assert client.complete_json("s", "u", key).text == '{"findings": []}'
    with pytest.raises(LLMError, match="no saved review"):
        client.complete_json("s", "u", make_cache_key("v1", "something else"))


def test_cache_key_ignores_whitespace_but_not_prompt_version():
    assert make_cache_key("v1", "a  b\n c") == make_cache_key("v1", "a b c")
    assert make_cache_key("v1", "a") != make_cache_key("v2", "a")


def test_real_client_records_responses_for_replay(settings):
    class StubSDK:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    assert kwargs["temperature"] == 0
                    msg = type("M", (), {"content": '{"findings": []}'})
                    return type("R", (), {"choices": [type("C", (), {"message": msg})]})

    store = ReplayStore(settings.replay_dir)
    client = OpenAICompatibleClient("gemini", "g", StubSDK, store)
    client.complete_json("s", "u", "abc")
    assert store.load("abc")["response"] == '{"findings": []}'
