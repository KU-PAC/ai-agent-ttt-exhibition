from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["Config", "load_config"]


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8765
    ai_strategy: str = "algorithm"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    vision_timeout: float = 1.0
    vision_max_retries: int = 3
    llm_timeout: float = 10.0
    llm_max_retries: int = 3
    robot_timeout: float = 30.0
    poll_interval: float = 1.0
    stable_count_required: int = 2
    game_over_wait: float = 5.0


def load_config() -> Config:
    return Config(
        host=os.environ.get("MASTER_HOST", "0.0.0.0"),
        port=int(os.environ.get("MASTER_PORT", "8765")),
        ai_strategy=os.environ.get("MASTER_AI_STRATEGY", "algorithm"),
        llm_api_key=os.environ.get("OPENAI_API_KEY", ""),
        llm_model=os.environ.get("MASTER_LLM_MODEL", "gpt-4o"),
        vision_timeout=float(os.environ.get("MASTER_VISION_TIMEOUT", "1.0")),
        vision_max_retries=int(os.environ.get("MASTER_VISION_MAX_RETRIES", "3")),
        llm_timeout=float(os.environ.get("MASTER_LLM_TIMEOUT", "10.0")),
        llm_max_retries=int(os.environ.get("MASTER_LLM_MAX_RETRIES", "3")),
        robot_timeout=float(os.environ.get("MASTER_ROBOT_TIMEOUT", "30.0")),
        poll_interval=float(os.environ.get("MASTER_POLL_INTERVAL", "1.0")),
        stable_count_required=int(os.environ.get("MASTER_STABLE_COUNT", "2")),
        game_over_wait=float(os.environ.get("MASTER_GAME_OVER_WAIT", "5.0")),
    )
