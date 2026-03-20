from __future__ import annotations

import asyncio
import json
import logging

from openai import AsyncOpenAI

from master.application.ports.reaction_generator_port import ReactionGeneratorPort
from master.domain.board import Board
from master.domain.errors import ReactionGenerationError
from master.domain.models import Emotion, Move, Reaction

__all__ = ["LLMReactionAdapter"]

log = logging.getLogger(__name__)

LLM_TIMEOUT = 10.0
MAX_RETRIES = 3

EMOTION_MAP: dict[str, Emotion] = {e.value: e for e in Emotion}

SYSTEM_PROMPT = (
    "あなたは〇✕ゲーム（三目並べ）のAIプレイヤーです。"
    "あなたが打つ手は既に決まっています。"
    "この状況にふさわしい感情とセリフを返してください。\n"
    "出力フォーマット（厳守）:\n"
    '{"emotion": "<joy|sorrow|angry|fun|neutral>", "dialogue": "<セリフ>"}'
)


class LLMReactionAdapter(ReactionGeneratorPort):
    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(
        self, board: Board, position: int, move_history: list[Move],
    ) -> Reaction:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                messages = self._build_reaction_prompt(board, position, move_history)
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self._model,
                        messages=messages,
                        response_format={"type": "json_object"},
                        temperature=0.9,
                    ),
                    timeout=LLM_TIMEOUT,
                )
                content = response.choices[0].message.content or "{}"
                raw = json.loads(content)
                emotion_str = str(raw.get("emotion", "neutral")).lower()
                emotion = EMOTION_MAP.get(emotion_str, Emotion.NEUTRAL)
                dialogue = str(raw.get("dialogue", ""))
                return Reaction(emotion=emotion, dialogue=dialogue)
            except Exception as e:
                log.warning("Reaction LLM retry %d/%d: %s", attempt, MAX_RETRIES, e)

        raise ReactionGenerationError(
            f"Reaction generation failed after {MAX_RETRIES} retries"
        )

    @staticmethod
    def _build_reaction_prompt(
        board: Board, position: int, move_history: list[Move],
    ) -> list[dict[str, str]]:
        history_str = ", ".join(
            f"{'人間' if m.player == 1 else 'AI'}→マス{m.position}"
            for m in move_history
        )
        user_msg = (
            f"現在の盤面: {board.to_list()}\n"
            f"あなたはマス{position}に打ちます。\n"
            f"これまでの手: [{history_str}]"
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
