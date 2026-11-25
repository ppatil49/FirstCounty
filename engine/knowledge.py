"""Loads the regulation reference and issue taxonomy that ground every review."""
from __future__ import annotations

import json
from functools import lru_cache

from config import REGULATIONS_DIR


@lru_cache(maxsize=1)
def reference_text() -> str:
    return (REGULATIONS_DIR / "reference.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def taxonomy() -> dict[str, dict]:
    """issue_code -> {code, regulation, description}"""
    raw = json.loads((REGULATIONS_DIR / "issue_taxonomy.json").read_text(encoding="utf-8"))
    return {item["code"]: item for item in raw["issue_codes"]}


@lru_cache(maxsize=1)
def taxonomy_version() -> str:
    raw = json.loads((REGULATIONS_DIR / "issue_taxonomy.json").read_text(encoding="utf-8"))
    return str(raw.get("version", "unknown"))
