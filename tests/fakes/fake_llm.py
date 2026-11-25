"""Deterministic stand-in for an LLM so tests never need a network or API key."""
from __future__ import annotations

import json
from typing import Callable

from engine.llm import LLMError, LLMResponse


def finding(code: str, quote: str | None = None, severity: str = "high", confidence: float = 0.9,
            explanation: str = "test explanation", fix: str = "test fix") -> dict:
    return {"issue_code": code, "regulation": "model-supplied citation", "offending_text": quote,
            "explanation": explanation, "suggested_fix": fix, "severity": severity, "confidence": confidence}


class FakeLLM:
    provider = "fake"
    model = "fake-model-1"

    def __init__(self, responder: Callable[[str], list[dict] | str] | None = None, fail: bool = False):
        """responder(user_prompt) -> list of finding dicts, or a raw string to return verbatim."""
        self.responder = responder or (lambda _prompt: [])
        self.fail = fail
        self.calls: list[dict] = []

    def complete_json(self, system: str, user: str, cache_key: str) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "cache_key": cache_key})
        if self.fail:
            raise LLMError("fake outage")
        out = self.responder(user)
        text = out if isinstance(out, str) else json.dumps(
            {"classification": {"product_category": "test"}, "findings": out})
        return LLMResponse(text=text, model=self.model)
