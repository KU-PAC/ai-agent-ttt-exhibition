"""
三目並べ（〇×ゲーム）の型定義
Master仕様準拠: 0=空き, 1=人間(〇), 2=AI(✕)
"""

from dataclasses import dataclass, field
from typing import Literal, List, Optional, Any, Dict

EMPTY = 0
HUMAN = 1
AI = 2

CELL_SYMBOLS = {EMPTY: "＿", HUMAN: "〇", AI: "✕"}

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


@dataclass
class GameBoard:
    cells: List[int] = field(default_factory=lambda: [0] * 9)

    def to_text(self) -> str:
        rows = []
        for i in range(3):
            row = [CELL_SYMBOLS[self.cells[i * 3 + j]] for j in range(3)]
            rows.append(" | ".join(row))
        return "\n-----------\n".join(rows)

    def is_valid_move(self, position: int) -> bool:
        if not (0 <= position <= 8):
            return False
        return self.cells[position] == EMPTY

    def place_mark(self, position: int, player: int) -> bool:
        if not self.is_valid_move(position):
            return False
        self.cells[position] = player
        return True

    def check_winner(self) -> Optional[str]:
        for line in WIN_LINES:
            values = [self.cells[i] for i in line]
            if values[0] != EMPTY and all(v == values[0] for v in values):
                if values[0] == HUMAN:
                    return "win_human"
                else:
                    return "win_ai"
        if all(cell != EMPTY for cell in self.cells):
            return "draw"
        return None

    def get_empty_positions(self) -> List[int]:
        return [i for i in range(9) if self.cells[i] == EMPTY]


@dataclass
class GameState:
    board: GameBoard = field(default_factory=GameBoard)
    current_player: int = HUMAN
    is_game_over: bool = False
    winner: Optional[str] = None
    turn_count: int = 0
    phase: str = "standby"


@dataclass
class AIResponse:
    move: int
    emotion: str
    dialogue: str


def make_set_state_message(state: str) -> Dict[str, Any]:
    return {
        "type": "set_state",
        "payload": {"state": state},
    }


def make_play_reaction_message(emotion: str, dialogue: str) -> Dict[str, Any]:
    return {
        "type": "play_reaction",
        "payload": {"emotion": emotion, "dialogue": dialogue},
    }


def make_place_piece_message(position: int, piece_type: int) -> Dict[str, Any]:
    return {
        "type": "place_piece",
        "payload": {"position": position, "piece_type": piece_type},
    }


def make_request_board_state_message() -> Dict[str, Any]:
    return {
        "type": "request_board_state",
        "payload": {},
    }


def make_internal_state_response(board: List[int], phase: str) -> Dict[str, Any]:
    return {
        "type": "internal_state_response",
        "payload": {"board": board, "current_phase": phase},
    }
