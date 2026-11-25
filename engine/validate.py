"""Deterministic checks on raw model output. The model proposes; this code
decides what is allowed through, so bad codes or invented quotes never reach users."""
from __future__ import annotations

import json
import re

from engine.knowledge import taxonomy
from engine.schemas import Finding

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}
QUOTE_MISMATCH_PENALTY = 0.2


class OutputParseError(ValueError):
    pass


def parse_json(text: str) -> dict:
    """Parse model output, tolerating ```json fences or stray text around the object."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise OutputParseError("Model output contains no JSON object.")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OutputParseError(f"Model output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise OutputParseError("Model output JSON is not an object.")
    return data


def _normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[*_#`>\\]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in_text(quote: str, content: str) -> bool:
    q = _normalize(quote).strip(" .,;:!\"'")
    return bool(q) and q in _normalize(content)


def validate_findings(raw: list, content: str, low_confidence_threshold: float) -> tuple[list[Finding], list[dict]]:
    """Returns (kept findings, dropped items with reasons)."""
    codes = taxonomy()
    kept: list[Finding] = []
    dropped: list[dict] = []

    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            dropped.append({"item": item, "reason": "not an object"})
            continue
        code = str(item.get("issue_code", "")).strip().upper()
        if code not in codes:
            dropped.append({"item": item, "reason": f"unknown issue_code '{code}'"})
            continue

        notes: list[str] = []
        severity = str(item.get("severity", "medium")).lower()
        if severity not in SEVERITY_RANK:
            notes.append(f"severity '{severity}' replaced with 'medium'")
            severity = "medium"
        try:
            confidence = min(max(float(item.get("confidence", 0.5)), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.5
            notes.append("confidence missing or invalid; set to 0.5")

        quote = item.get("offending_text")
        if isinstance(quote, str) and quote.strip().lower() in {"", "null", "none", "n/a"}:
            quote = None
        if quote is not None and not quote_in_text(str(quote), content):
            notes.append(f"quoted text not found in the piece: \"{quote}\"")
            quote = None
            confidence = max(0.0, confidence - QUOTE_MISMATCH_PENALTY)

        kept.append(
            Finding(
                issue_code=code,
                # Citation always comes from the taxonomy, never from the model.
                regulation=codes[code]["regulation"],
                offending_text=quote,
                explanation=str(item.get("explanation", "")).strip(),
                suggested_fix=str(item.get("suggested_fix", "")).strip(),
                severity=severity,
                confidence=round(confidence, 2),
                validation_notes=notes,
            )
        )

    merged = merge_duplicates(kept)
    for f in merged:
        f.needs_human_review = f.confidence < low_confidence_threshold
    return merged, dropped


def merge_duplicates(findings: list[Finding]) -> list[Finding]:
    """One finding per issue_code: keep the strongest severity and confidence,
    combine explanations and fixes."""
    by_code: dict[str, Finding] = {}
    for f in findings:
        if f.issue_code not in by_code:
            by_code[f.issue_code] = f.model_copy(deep=True)
            continue
        cur = by_code[f.issue_code]
        if SEVERITY_RANK[f.severity] > SEVERITY_RANK[cur.severity]:
            cur.severity = f.severity
        cur.confidence = max(cur.confidence, f.confidence)
        cur.offending_text = cur.offending_text or f.offending_text
        if f.explanation and f.explanation not in cur.explanation:
            cur.explanation = f"{cur.explanation} {f.explanation}".strip()
        if f.suggested_fix and f.suggested_fix not in cur.suggested_fix:
            cur.suggested_fix = f"{cur.suggested_fix} {f.suggested_fix}".strip()
        cur.validation_notes = cur.validation_notes + f.validation_notes + ["merged duplicate finding"]
    return sorted(by_code.values(), key=lambda f: (-SEVERITY_RANK[f.severity], -f.confidence))
