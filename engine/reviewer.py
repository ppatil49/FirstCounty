"""review_ad(): one marketing piece in, validated findings out."""
from __future__ import annotations

import re
import time

from config import Settings
from engine.knowledge import taxonomy_version
from engine.llm import LLMClient, build_client, make_cache_key
from engine.prompts import PROMPT_VERSION, system_prompt, user_prompt
from engine.schemas import ReviewResult
from engine.validate import parse_json, validate_findings

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def split_front_matter(text: str) -> tuple[dict, str]:
    """Sample ads carry YAML-style front matter (ad_id, channel, product).
    Returns (metadata, body). The ad_id is never sent to the model."""
    m = FRONT_MATTER.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]


class Reviewer:
    def __init__(self, llm: LLMClient, low_confidence_threshold: float = 0.6):
        self.llm = llm
        self.threshold = low_confidence_threshold

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "Reviewer":
        settings = settings or Settings.load()
        return cls(build_client(settings), settings.low_confidence_threshold)

    def review(self, content: str, channel: str, product: str) -> ReviewResult:
        key = make_cache_key(PROMPT_VERSION, content)
        start = time.perf_counter()
        response = self.llm.complete_json(system_prompt(), user_prompt(content, channel, product), key)
        latency = int((time.perf_counter() - start) * 1000)

        data = parse_json(response.text)
        findings, dropped = validate_findings(data.get("findings", []), content, self.threshold)
        return ReviewResult(
            findings=findings,
            classification=data.get("classification", {}) or {},
            dropped=dropped,
            model=response.model,
            provider=self.llm.provider,
            prompt_version=PROMPT_VERSION,
            taxonomy_version=taxonomy_version(),
            latency_ms=latency,
            cache_key=key,
        )
