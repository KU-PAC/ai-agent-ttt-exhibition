"""
三目並べ（〇×ゲーム）の型定義
"""

from dataclasses import dataclass, field
from typing import Literal, List, Optional, Any, Dict


@dataclass
class GameBoard:
    """3x3 の盤面状態"""
    cells: List[Literal["", "O", "X"]] = field(default_factory=lambda: [""] * 9)

    def to_text(self) -> str:
        """盤面をテキスト形式で返す (表示用)"""
        board_text = "```\n"
        for i in range(3):
            row = []
            for j in range(3):
                cell = self.cells[i * 3 + j]
                if cell == "":
                    row.append(str(i * 3 + j))
                else:
                    row.append(cell)
            board_text += " | ".join(row) + "\n"
            if i < 2:
                board_text += "-----------\n"
        board_text += "```"
        return board_text

    def to_compact(self) -> str:
        """盤面をコンパクト形式で返す (LLM入力用)"""
        return "".join([cell if cell else "-" for cell in self.cells])

    def is_valid_move(self, position: int) -> bool:
        """指定位置に置けるかチェック (0-8)"""
        if not (0 <= position <= 8):
            return False
        return self.cells[position] == ""

    def place_mark(self, position: int, mark: Literal["O", "X"]) -> bool:
        """指定位置にマークを置く"""
        if not self.is_valid_move(position):
            return False
        self.cells[position] = mark
        return True

    def check_winner(self) -> Literal["O", "X", "draw", None]:
        """勝者をチェック"""
        # 勝利パターン
        winning_patterns = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],  # 行
            [0, 3, 6], [1, 4, 7], [2, 5, 8],  # 列
            [0, 4, 8], [2, 4, 6],  # 対角線
        ]

        for pattern in winning_patterns:
            values = [self.cells[i] for i in pattern]
            if values[0] != "" and all(v == values[0] for v in values):
                return values[0]

        # 全て埋まった場合は引き分け
        if all(cell != "" for cell in self.cells):
            return "draw"

        return None

    def get_empty_positions(self) -> List[int]:
        """空いている位置のリストを返す"""
        return [i for i in range(9) if self.cells[i] == ""]

    def get_available_positions(self) -> List[int]:
        """空いている位置のリストを返す（エイリアス）"""
        return self.get_empty_positions()


@dataclass
class GameState:
    """ゲーム状態"""
    board: GameBoard = field(default_factory=GameBoard)
    current_player: Literal["O", "X"] = "O"
    is_game_over: bool = False
    winner: Literal["O", "X", "draw", None] = None
    turn_count: int = 0

    def get_status(self) -> str:
        """ゲーム状態をテキストで返す"""
        if self.is_game_over:
            if self.winner == "draw":
                return "引き分け"
            else:
                return f"{self.winner} の勝ち"
        return f"〇×ゲーム進行中 (次: {self.current_player}, ターン: {self.turn_count})"


# ===== WebSocket メッセージ型 =====
# 通信フォーマット: {"type": "xxx", "payload": {...}}

@dataclass
class MasterToRobotMessage:
    """Master → Robot: 指し手命令"""
    type: Literal["move", "reset"] = "move"
    position: int = None  # 0-8 (reset の場合は None)


@dataclass
class RobotToMasterMessage:
    """Robot → Master: 配置結果"""
    type: Literal["move_result", "board_state"] = "move_result"
    success: bool = True
    position: int = None  # move_result の場合に値が入る
    board: List[Literal["", "O", "X"]] = field(default_factory=lambda: [""] * 9)


def make_unity_message(msg_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unity向けメッセージを {type, payload} フォーマットで生成

    Args:
        msg_type: メッセージタイプ ("speech", "game_start", "game_over", "placement_failure", "error")
        payload: タイプに応じたペイロード辞書

    Returns:
        {"type": msg_type, "payload": payload}
    """
    return {
        "type": msg_type,
        "payload": payload,
    }


@dataclass
class AIResponse:
    """OpenAI の構造化出力"""
    move: int  # 0-8
    emotion: Literal["normal", "happy", "angry", "sad", "surprised", "shy", "excited", "smug", "calm"]
    speech: str
