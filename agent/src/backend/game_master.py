"""
Master モジュール - 三目並べゲームの主管者
ゲーム管理、LLM呼び出し、他モジュールとの通信
"""
import os
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv
from .game_structures import GameBoard, GameState, AIResponse

load_dotenv()

class GameMaster:
    """三目並べゲームの主管者"""

    GAME_PROMPT = """
あなたは三目並べ（〇×ゲーム）をプレイするAIです。

【盤面情報】
現在の盤面状態: {board_state}
- "-" は空きマス（0-8の位置番号）
- "O" はあなたの前の手
- "X" は相手の前の手

【ルール】
- 3x3 のグリッド上に "O" を置きます
- 3つの "O" が一列に並んだらあなたの勝ちです
- "X" が3つ揃ったら相手の勝ちです
- すべてのマスが埋まったら引き分けです

【タスク】
空き位置の中から最適な位置を選んでください。戦略的に置きましょう。
利用可能な位置: {available_positions}

【出力形式】
以下のJSON形式で出力してください：
{{
  "move": <0-8の整数>,
  "emotion": "<enum値>",
  "speech": "<日本語の発話>"
}}

【感情の選択肢】
normal, happy, angry, sad, surprised, shy, excited, smug, calm

【発話の例】
- "このマスに置きます" (通常時)
- "勝つぞ！" (有利な場合)
- "難しいな..." (困った場合)
"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        """
        初期化

        Args:
            api_key: OpenAI API キー（環境変数から取得）
            model: 使用するモデル
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API キーが設定されていません。環境変数 OPENAI_API_KEY を設定してください。")
        self.model = model
        self.client = OpenAI(api_key=self.api_key)
        self.game_state = GameState(board=GameBoard(), current_player="O")
        self.llm_move_count = 0  # LLMが置いた回数（テスト用）

    def reset_game(self) -> dict:
        """ゲームをリセット"""
        self.game_state = GameState(board=GameBoard(), current_player="O")
        return {
            "status": "〇×ゲーム進行中",
            "board": self.game_state.board.to_text(),
            "turn_count": 0
        }

    async def get_ai_move(self) -> Optional[AIResponse]:
        """
        LLMから次の手を取得

        Returns:
            AIResponse オブジェクト、またはエラー時は None
        """
        if self.game_state.is_game_over:
            return None

        board_state = self.game_state.board.to_compact()
        available = self.game_state.board.get_empty_positions()

        prompt = self.GAME_PROMPT.format(
            board_state=board_state,
            available_positions=str(available)
        )

        try:
            # 通常の chat completion でテスト
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=200,
                temperature=0.7
            )

            content = response.choices[0].message.content
            print(f"LLM 応答: {content}")
            
            # JSON パースを試行
            import json
            try:
                parsed = json.loads(content)
                return AIResponse(
                    move=parsed.get("move", 0),
                    emotion=parsed.get("emotion", "normal"),
                    speech=parsed.get("speech", "わかりません")
                )
            except json.JSONDecodeError:
                # JSON ではない場合はデフォルト値を返す
                return AIResponse(
                    move=4,  # 中央
                    emotion="normal",
                    speech="中央に置きます"
                )

        except Exception as e:
            print(f"LLM 呼び出しエラー: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_game_status(self) -> dict:
        """現在のゲーム状態を取得"""
        return {
            "status": self.game_state.get_status(),
            "board": self.game_state.board.to_text(),
            "current_player": self.game_state.current_player,
            "turn_count": self.game_state.turn_count,
            "is_game_over": self.game_state.is_game_over,
            "winner": self.game_state.winner
        }
