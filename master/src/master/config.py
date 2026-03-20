from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
}


def _load_dotenv() -> None:
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        if "#" in value:
            value = value[:value.index("#")]
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8765
    ai_strategy: str = "algorithm"
    llm_provider: str = "anthropic"
    llm_api_key: str = ""
    llm_model: str = ""
    vision_timeout: float = 1.0
    vision_max_retries: int = 3
    llm_timeout: float = 10.0
    llm_max_retries: int = 3
    llm_max_tokens: int = 256
    llm_temperature: float = 0.8
    robot_timeout: float = 30.0
    poll_interval: float = 1.0
    stable_count_required: int = 2
    game_over_wait: float = 5.0


def load_config() -> Config:
    _load_dotenv()
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    provider_key_env = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get(provider_key_env, "")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODELS.get(provider, ""))

    return Config(
        host=os.environ.get("MASTER_HOST", "0.0.0.0"),
        port=int(os.environ.get("MASTER_PORT", "8765")),
        ai_strategy=os.environ.get("MASTER_AI_STRATEGY", "algorithm"),
        llm_provider=provider,
        llm_api_key=api_key,
        llm_model=model,
        vision_timeout=float(os.environ.get("MASTER_VISION_TIMEOUT", "1.0")),
        vision_max_retries=int(os.environ.get("MASTER_VISION_MAX_RETRIES", "3")),
        llm_timeout=float(os.environ.get("MASTER_LLM_TIMEOUT", "10.0")),
        llm_max_retries=int(os.environ.get("MASTER_LLM_MAX_RETRIES", "3")),
        llm_max_tokens=int(os.environ.get("MASTER_LLM_MAX_TOKENS", "256")),
        llm_temperature=float(os.environ.get("MASTER_LLM_TEMPERATURE", "0.8")),
        robot_timeout=float(os.environ.get("MASTER_ROBOT_TIMEOUT", "30.0")),
        poll_interval=float(os.environ.get("MASTER_POLL_INTERVAL", "1.0")),
        stable_count_required=int(os.environ.get("MASTER_STABLE_COUNT", "2")),
        game_over_wait=float(os.environ.get("MASTER_GAME_OVER_WAIT", "5.0")),
    )
