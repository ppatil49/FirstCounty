"""Data shapes for engine input and output."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["high", "medium", "low"]


class Finding(BaseModel):
    issue_code: str
    regulation: str
    offending_text: str | None
    explanation: str
    suggested_fix: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    needs_human_review: bool = False
    validation_notes: list[str] = Field(default_factory=list)


class ReviewResult(BaseModel):
    findings: list[Finding]
    classification: dict = Field(default_factory=dict)
    dropped: list[dict] = Field(default_factory=list)  # findings removed by validation, with reasons
    model: str
    provider: str
    prompt_version: str
    taxonomy_version: str
    latency_ms: int = 0
    cache_key: str = ""
