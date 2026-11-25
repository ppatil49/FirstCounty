"""LLM provider switch.

Every real provider (Gemini, Ollama, OpenAI, Azure OpenAI) is reached through the
OpenAI-compatible chat-completions API, so moving to Azure is a config change.
`replay` serves saved responses so the app, tests and eval run without any API key.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from config import Settings

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OLLAMA_BASE_URL = "http://localhost:11434/v1/"


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    text: str
    model: str


class LLMClient(Protocol):
    provider: str
    model: str

    def complete_json(self, system: str, user: str, cache_key: str) -> LLMResponse: ...


def normalize_for_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def make_cache_key(prompt_version: str, content: str) -> str:
    """Replay key depends only on prompt version + ad body, so a sample ad
    submitted through the UI hits the same cached review as the eval run."""
    digest = hashlib.sha256(f"{prompt_version}\n{normalize_for_key(content)}".encode()).hexdigest()
    return digest[:24]


class ReplayStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def load(self, key: str) -> dict | None:
        p = self.path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def save(self, key: str, record: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path(key).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")


class OpenAICompatibleClient:
    def __init__(self, provider: str, model: str, client, replay: ReplayStore | None):
        self.provider = provider
        self.model = model
        self._client = client
        self._replay = replay

    def complete_json(self, system: str, user: str, cache_key: str) -> LLMResponse:
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # network, auth, rate limit after retries
            raise LLMError(f"{self.provider} call failed: {exc}") from exc
        text = resp.choices[0].message.content or ""
        if self._replay is not None:
            self._replay.save(cache_key, {"provider": self.provider, "model": self.model, "response": text})
        return LLMResponse(text=text, model=self.model)


class ReplayClient:
    provider = "replay"

    def __init__(self, store: ReplayStore):
        self._store = store
        self.model = "replay"

    def complete_json(self, system: str, user: str, cache_key: str) -> LLMResponse:
        record = self._store.load(cache_key)
        if record is None:
            raise LLMError(
                "Replay mode has no saved review for this exact text. Use one of the sample ads, "
                "or set LLM_PROVIDER to gemini / ollama / openai / azure_openai in .env."
            )
        return LLMResponse(text=record["response"], model=f"replay:{record.get('model', '?')}")


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise LLMError(f"{name} is not set. Add it to your .env file.")
    return value


def build_client(settings: Settings) -> LLMClient:
    store = ReplayStore(settings.replay_dir)
    recorder = store if settings.record_replay else None
    p = settings.llm_provider
    if p == "replay":
        return ReplayClient(store)

    from openai import AzureOpenAI, OpenAI  # imported lazily: replay/tests need no SDK setup

    common = {"max_retries": 5, "timeout": 300}
    if p == "gemini":
        client = OpenAI(api_key=_require("GEMINI_API_KEY"), base_url=settings.llm_base_url or GEMINI_BASE_URL, **common)
    elif p == "ollama":
        client = OpenAI(api_key="ollama", base_url=settings.llm_base_url or OLLAMA_BASE_URL, **common)
    elif p == "openai":
        client = OpenAI(api_key=_require("OPENAI_API_KEY"), base_url=settings.llm_base_url, **common)
    elif p == "azure_openai":
        client = AzureOpenAI(
            api_key=_require("AZURE_OPENAI_API_KEY"),
            azure_endpoint=_require("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            **common,
        )
    else:
        raise LLMError(f"Unknown LLM_PROVIDER '{p}'. Use gemini, ollama, openai, azure_openai or replay.")
    if not settings.llm_model:
        raise LLMError("LLM_MODEL is not set.")
    return OpenAICompatibleClient(p, settings.llm_model, client, recorder)
