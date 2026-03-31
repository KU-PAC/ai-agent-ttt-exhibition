from __future__ import annotations

import asyncio
import json
import logging
import random

from master.adapters.errors import LLMInvalidResponseError
from master.adapters.llm_utils import extract_json, parse_emotion
from master.application.ports import AIStrategyPort, LLMClientPort
from master.domain.board import Board
from master.domain.game_rule import is_valid_ai_move
from master.domain.models import FALLBACK_DIALOGUES, FALLBACK_EMOTION, AIDecision, Move

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "あなたは〇✕ゲーム（三目並べ）のAIプレイヤーです。"
    "盤面を受け取り、次の一手、感情、セリフをJSON形式で返してください。\n"
    "盤面の値: 0=空き, 1=人間(〇), 2=AI(✕)\n"
    "配列インデックス:\n[0][1][2]\n[3][4][5]\n[6][7][8]\n\n"
    "出力フォーマット（厳守・JSONのみ返答）:\n"
    '{"next_move": <0~8の整数>, "emotion": "<normal|happy|angry|sad|surprised|shy|excited|smug|calm>", '
    '"dialogue": "<セリフ>"}'
)


class LLMStrategy(AIStrategyPort):
    def __init__(
        self,
        llm_client: LLMClientPort,
        max_retries: int = 3,
        timeout: float = 10.0,
    ) -> None:
        self._llm = llm_client
        self._max_retries = max_retries
        self._timeout = timeout

    async def decide(
        self,
        board: Board,
        move_history: list[Move],
    ) -> AIDecision:
        error_context: str | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                user_msg = self._build_user_message(board, error_context)
                content = await self._llm.chat(SYSTEM_PROMPT, user_msg, self._timeout)
                raw = json.loads(extract_json(content))
                return self._parse_response(raw, board)
            except (
                json.JSONDecodeError,
                LLMInvalidResponseError,
                KeyError,
                ValueError,
            ) as e:
                error_context = f"Attempt {attempt} failed: {e}"
                log.warning("LLM retry %d/%d: %s", attempt, self._max_retries, e)
            except (TimeoutError, asyncio.TimeoutError):
                error_context = f"Attempt {attempt} timed out"
                log.warning("LLM timeout %d/%d", attempt, self._max_retries)

        log.warning("LLM exhausted retries, using fallback")
        return self._fallback(board)

    @staticmethod
    def _build_user_message(board: Board, error_context: str | None) -> str:
        msg = f"現在の盤面: {board.to_list()}\n空きマス: {board.empty_cells()}"
        if error_context:
            msg += (
                f"\n\n前回のエラー: {error_context}\n正しいJSONで再回答してください。"
            )
        return msg

    @staticmethod
    def _parse_response(raw: dict, board: Board) -> AIDecision:
        next_move = int(raw["next_move"])
        if not is_valid_ai_move(board, next_move):
            raise LLMInvalidResponseError(
                f"Invalid move {next_move}: cell not empty or out of range"
            )
        emotion = parse_emotion(str(raw.get("emotion", "normal")))
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
