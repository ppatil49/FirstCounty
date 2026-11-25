"""Central settings. Everything environment-specific comes from env vars / .env,
so the same code runs on a laptop and on Azure."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
ADS_DIR = DATA_DIR / "ads"
REGULATIONS_DIR = DATA_DIR / "regulations"
ANSWER_KEY_PATH = DATA_DIR / "answer_key" / "sample_answers.json"
RESULTS_DIR = ROOT / "eval" / "results"

# Default model per provider; override with LLM_MODEL.
DEFAULT_MODELS = {
    "gemini": "gemini-3.6-flash",
    "ollama": "qwen2.5:7b",
    "openai": "gpt-4.1",
    "azure_openai": "",  # Azure uses the deployment name
    "replay": "replay",
}


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_model: str
    llm_base_url: str | None
    database_url: str
    low_confidence_threshold: float
    replay_dir: Path
    record_replay: bool

    @staticmethod
    def load() -> "Settings":
        provider = os.getenv("LLM_PROVIDER", "replay").strip().lower()
        model = os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODELS.get(provider, "")
        if provider == "azure_openai":
            model = os.getenv("AZURE_OPENAI_DEPLOYMENT", model)
        db_default = f"sqlite:///{(ROOT / 'var' / 'fcb.db').as_posix()}"
        return Settings(
            llm_provider=provider,
            llm_model=model,
            llm_base_url=os.getenv("LLM_BASE_URL") or None,
            database_url=os.getenv("DATABASE_URL", db_default),
            low_confidence_threshold=float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.6")),
            replay_dir=Path(os.getenv("REPLAY_DIR", str(RESULTS_DIR / "replay_cache"))),
            record_replay=os.getenv("RECORD_REPLAY", "true").lower() == "true",
        )
