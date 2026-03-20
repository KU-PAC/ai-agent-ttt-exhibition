from __future__ import annotations

import json
import logging

from master.adapters.errors import ReactionGenerationError
from master.adapters.llm_utils import (
    extract_json,
    parse_emotion,
    render_board,
    render_history,
)
from master.application.ports import LLMClientPort, ReactionGeneratorPort
from master.domain.board import AI, Board
from master.domain.models import GameResult, Move, Reaction

log = logging.getLogger(__name__)

REACTION_SYSTEM_PROMPT = (
    "あなたは〇✕ゲーム（三目並べ）のAIプレイヤー（✕）です。\n"
    "あなたが打つ手は既に決まっています。\n"
    "盤面の状況・流れを読み取り、この一手にふさわしい感情とセリフを返してください。\n"
    "感情の目安:\n"
    "- joy: 勝てそう、有利になった\n"
    "- angry: 相手にやられた、悔しい防御\n"
    "- sorrow: 不利、追い詰められた\n"
    "- fun: 余裕がある、楽しんでいる\n"
    "- neutral: 序盤、様子見\n\n"
    "出力フォーマット（厳守・JSONのみ返答）:\n"
    '{"emotion": "<joy|sorrow|angry|fun|neutral>", "dialogue": "<セリフ>"}'
)

GAME_OVER_SYSTEM_PROMPT = (
    "あなたは〇✕ゲーム（三目並べ）のAIプレイヤー（✕）です。\n"
    "ゲームが終了しました。結果に応じた結びのセリフを返してください。\n"
    "感情の目安:\n"
    "- joy: 勝った喜び\n"
    "- sorrow: 負けた悔しさ\n"
    "- fun: 引き分けの健闘を讃える\n\n"
    "出力フォーマット（厳守・JSONのみ返答）:\n"
    '{"emotion": "<joy|sorrow|angry|fun|neutral>", "dialogue": "<セリフ>"}'
)

RESULT_LABELS: dict[GameResult, str] = {
    GameResult.WIN_HUMAN: "人間(〇)の勝ち",
    GameResult.WIN_AI: "AI(✕)の勝ち",
    GameResult.DRAW: "引き分け",
}


class LLMReactionAdapter(ReactionGeneratorPort):
    def __init__(
        self,
        llm_client: LLMClientPort,
        max_retries: int = 3,
        timeout: float = 10.0,
    ) -> None:
        self._llm = llm_client
        self._max_retries = max_retries
        self._timeout = timeout

    async def generate(
        self,
        board: Board,
        position: int,
        move_history: list[Move],
    ) -> Reaction:
        after = board.set(position, AI)
        user_msg = (
            f"【打つ前の盤面】\n{render_board(board)}\n\n"
            f"あなた(✕)はマス{position}に打ちます。\n\n"
            f"【打った後の盤面】（★があなたの手）\n{render_board(after, highlight=position)}\n\n"
            f"【これまでの流れ】\n{render_history(move_history)}"
        )
        return await self._call_llm(REACTION_SYSTEM_PROMPT, user_msg)

    async def generate_game_over(
        self,
        board: Board,
        result: GameResult,
        move_history: list[Move],
    ) -> Reaction:
        label = RESULT_LABELS.get(result, "不明")
        user_msg = (
            f"【最終盤面】\n{render_board(board)}\n\n"
            f"結果: {label}\n\n"
            f"【試合の流れ】\n{render_history(move_history)}"
        )
        return await self._call_llm(GAME_OVER_SYSTEM_PROMPT, user_msg)

    async def _call_llm(self, system: str, user_msg: str) -> Reaction:
        for attempt in range(1, self._max_retries + 1):
            try:
                content = await self._llm.chat(system, user_msg, self._timeout)
                raw = json.loads(extract_json(content))
                emotion = parse_emotion(str(raw.get("emotion", "neutral")))
                dialogue = str(raw.get("dialogue", ""))
                return Reaction(emotion=emotion, dialogue=dialogue)
            except Exception as e:
                log.warning(
                    "Reaction LLM retry %d/%d: %s", attempt, self._max_retries, e
                )

        raise ReactionGenerationError(
            f"Reaction generation failed after {self._max_retries} retries"
        )
