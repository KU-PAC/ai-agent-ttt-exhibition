from __future__ import annotations

import json
import logging

from master.adapters.errors import ReactionGenerationError
from master.adapters.llm_utils import (
    analyze_move,
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
    "【打った後の盤面】と【この手の分析】を確認し、感情とセリフを返してください。\n"
    "分析に書かれていない状況（ブロック等）をセリフで語らないでください。\n"
    "判定の優先順位:\n"
    "1. 打った後に✕が縦・横・斜めに3つ揃っていれば → あなたの勝ち → happy\n"
    "2. 相手(〇)のリーチを防いだ手なら → surprised (危なかった！)\n"
    "3. 自分が有利になった手なら → excited (余裕)\n"
    "4. 不利な状況なら → sad\n"
    "5. 序盤・様子見 → normal\n\n"
    "出力フォーマット（厳守・JSONのみ返答）:\n"
    '{"emotion": "<normal|happy|angry|sad|surprised|shy|excited|smug|calm>", "dialogue": "<セリフ>"}'
)

GAME_OVER_SYSTEM_PROMPT = (
    "あなたは〇✕ゲーム（三目並べ）のAIプレイヤー（✕）です。\n"
    "ゲームが終了しました。結果に応じた結びのセリフを返してください。\n"
    "感情の目安:\n"
    "- happy: 勝った喜び\n"
    "- sad: 負けた悔しさ\n"
    "- calm: 引き分けの健闘を讃える\n\n"
    "出力フォーマット（厳守・JSONのみ返答）:\n"
    '{"emotion": "<normal|happy|angry|sad|surprised|shy|excited|smug|calm>", "dialogue": "<セリフ>"}'
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
        analysis = analyze_move(board, position, AI)
        full_history = list(move_history) + [Move(player=AI, position=position)]
        user_msg = (
            f"【打つ前の盤面】\n{render_board(board)}\n\n"
            f"あなた(✕)はマス{position}に打ちます。\n\n"
            f"【打った後の盤面】\n{render_board(after, highlight=position)}\n\n"
            f"【この手の分析】\n{analysis}\n\n"
            f"【これまでの流れ】\n{render_history(full_history)}"
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
                emotion = parse_emotion(str(raw.get("emotion", "normal")))
                dialogue = str(raw.get("dialogue", ""))
                return Reaction(emotion=emotion, dialogue=dialogue)
            except Exception as e:
                log.warning(
                    "Reaction LLM retry %d/%d: %s", attempt, self._max_retries, e
                )

        raise ReactionGenerationError(
            f"Reaction generation failed after {self._max_retries} retries"
        )
