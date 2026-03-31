"""
GameMaster - Masterプロトコル準拠のゲームロジック
LLM呼び出しでAIの手・感情・セリフを取得
"""
import json
import os
import random
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv
from .game_structures import (
    GameBoard, GameState, AIResponse,
    EMPTY, HUMAN, AI, CELL_SYMBOLS,
)

load_dotenv()

SYSTEM_PROMPT = """\
あなたは〇✕ゲーム（三目並べ）のAIプレイヤー（✕）です。
盤面データは9要素の配列で、0=空き, 1=人間(〇), 2=AI(✕)です。

以下のJSON形式で回答してください:
{
  "next_move": <0-8の整数>,
  "emotion": "<感情>",
  "dialogue": "<日本語のセリフ>"
}

感情の選択肢: normal, happy, angry, sad, surprised, shy, excited, smug, calm
"""

FALLBACK_DIALOGUES = [
    "なるほど、ではこちらにしましょう",
    "うーん、ここかな",
    "よし、決めました",
]


class GameMaster:

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY が設定されていません")
        self.model = model
        self.client = OpenAI(api_key=self.api_key)
        self.game_state = GameState()
        self.max_retries = 3

    def reset_game(self) -> dict:
        self.game_state = GameState()
        return {
            "board": self.game_state.board.cells,
            "current_phase": self.game_state.phase,
        }

    async def get_ai_move(self) -> AIResponse:
        if self.game_state.is_game_over:
            return self._fallback()

        board = self.game_state.board
        error_context = None

        for attempt in range(self.max_retries):
            try:
                user_msg = self._build_user_message(board, error_context)
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=256,
                    temperature=0.7,
                )
                content = response.choices[0].message.content
                parsed = json.loads(self._extract_json(content))
                move = parsed["next_move"]
                if not board.is_valid_move(move):
                    error_context = f"マス{move}は既に埋まっています。空きマス: {board.get_empty_positions()}"
                    continue
                return AIResponse(
                    move=move,
                    emotion=parsed.get("emotion", "normal"),
                    dialogue=parsed.get("dialogue", "ここにします"),
                )
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                error_context = f"JSON解析エラー: {e}"
                continue
            except Exception as e:
                error_context = f"LLMエラー: {e}"
                continue

        return self._fallback()

    def _build_user_message(self, board: GameBoard, error_context: Optional[str] = None) -> str:
        msg = f"現在の盤面: {board.cells}\n空きマス: {board.get_empty_positions()}"
        if error_context:
            msg += f"\n\n前回のエラー: {error_context}\n正しい手を選び直してください。"
        return msg

    def _fallback(self) -> AIResponse:
        empty = self.game_state.board.get_empty_positions()
        move = random.choice(empty) if empty else 0
        return AIResponse(
            move=move,
            emotion="normal",
            dialogue=random.choice(FALLBACK_DIALOGUES),
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start:end + 1]
        return text
