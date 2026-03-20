from __future__ import annotations

import asyncio
import json
import logging
import random

from openai import AsyncOpenAI

from master.application.ports.ai_strategy_port import AIStrategyPort
from master.domain.board import Board
from master.domain.errors import LLMInvalidResponseError
from master.domain.game_rule import is_valid_ai_move
from master.domain.models import (
    FALLBACK_DIALOGUES,
    FALLBACK_EMOTION,
    AIDecision,
    Emotion,
    Move,
)

__all__ = ["LLMStrategy"]

log = logging.getLogger(__name__)

MAX_RETRIES = 3
LLM_TIMEOUT = 10.0

SYSTEM_PROMPT = (
    "あなたは〇✕ゲーム（三目並べ）のAIプレイヤーです。"
    "盤面を受け取り、次の一手、感情、セリフをJSON形式で返してください。\n"
    "盤面の値: 0=空き, 1=人間(〇), 2=AI(✕)\n"
    "配列インデックス:\n[0][1][2]\n[3][4][5]\n[6][7][8]\n\n"
    "出力フォーマット（厳守）:\n"
    '{"next_move": <0~8の整数>, "emotion": "<joy|sorrow|angry|fun|neutral>", '
    '"dialogue": "<セリフ>"}'
)

EMOTION_MAP: dict[str, Emotion] = {e.value: e for e in Emotion}


class LLMStrategy(AIStrategyPort):
    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def decide(
        self, board: Board, move_history: list[Move],
    ) -> AIDecision:
        error_context: str | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                messages = self._build_prompt(board, error_context)
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self._model,
                        messages=messages,
                        response_format={"type": "json_object"},
                        temperature=0.8,
                    ),
                    timeout=LLM_TIMEOUT,
                )
                content = response.choices[0].message.content or "{}"
                raw = json.loads(content)
                return self._parse_response(raw, board)
            except (json.JSONDecodeError, LLMInvalidResponseError, KeyError, ValueError) as e:
                error_context = f"Attempt {attempt} failed: {e}"
                log.warning("LLM retry %d/%d: %s", attempt, MAX_RETRIES, e)
            except (TimeoutError, asyncio.TimeoutError):
                error_context = f"Attempt {attempt} timed out after {LLM_TIMEOUT}s"
                log.warning("LLM timeout %d/%d", attempt, MAX_RETRIES)

        log.warning("LLM exhausted retries, using fallback")
        return self._fallback(board)

    def _build_prompt(
        self, board: Board, error_context: str | None,
    ) -> list[dict[str, str]]:
        user_msg = f"現在の盤面: {board.to_list()}\n空きマス: {board.empty_cells()}"
        if error_context:
            user_msg += f"\n\n前回のエラー: {error_context}\n正しいJSONで再回答してください。"
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

    @staticmethod
    def _parse_response(raw: dict, board: Board) -> AIDecision:
        next_move = int(raw["next_move"])
        if not is_valid_ai_move(board, next_move):
            raise LLMInvalidResponseError(
                f"Invalid move {next_move}: cell not empty or out of range"
            )
        emotion_str = str(raw.get("emotion", "neutral")).lower()
        emotion = EMOTION_MAP.get(emotion_str, Emotion.NEUTRAL)
        dialogue = str(raw.get("dialogue", ""))
        return AIDecision(next_move=next_move, emotion=emotion, dialogue=dialogue)

    @staticmethod
    def _fallback(board: Board) -> AIDecision:
        position = random.choice(board.empty_cells())
        return AIDecision(
            next_move=position,
            emotion=FALLBACK_EMOTION,
            dialogue=random.choice(FALLBACK_DIALOGUES),
        )
