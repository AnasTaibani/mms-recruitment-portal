"""Central AI configuration — read from the backend environment only (never sent to the browser)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AIConfig:
    api_key: str | None
    model: str
    timeout: float
    max_retries: int
    base_url: str | None          # optional: OpenAI-compatible gateway / proxy; leave unset for api.openai.com
    max_question_chars: int = 1000
    max_context_messages: int = 10
    max_context_chars: int = 1500


def load_config() -> AIConfig:
    return AIConfig(
        api_key=(os.environ.get("OPENAI_API_KEY") or "").strip() or None,
        model=(os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini").strip(),
        timeout=float(os.environ.get("OPENAI_TIMEOUT_SECONDS") or 30),
        max_retries=int(os.environ.get("OPENAI_MAX_RETRIES") or 2),
        base_url=(os.environ.get("OPENAI_BASE_URL") or "").strip() or None,
    )
