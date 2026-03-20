from __future__ import annotations

from master.domain.board import Board
from master.domain.models import GameResult

__all__ = [
    "WIN_LINES",
    "judge",
    "check_winner",
    "is_valid_human_move",
    "find_human_move",
    "is_valid_ai_move",
]

WIN_LINES: list[tuple[int, int, int]] = [
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
]


def check_winner(board: Board) -> int | None:
    for a, b, c in WIN_LINES:
        if board.get(a) != 0 and board.get(a) == board.get(b) == board.get(c):
            return board.get(a)
    return None


def judge(board: Board) -> GameResult:
    winner = check_winner(board)
    if winner == 1:
        return GameResult.WIN_HUMAN
    if winner == 2:
        return GameResult.WIN_AI
    if not board.empty_cells():
        return GameResult.DRAW
    return GameResult.ONGOING


def is_valid_human_move(current: Board, new_board: Board) -> bool:
    return find_human_move(current, new_board) is not None


def find_human_move(current: Board, new_board: Board) -> int | None:
    diff_index: int | None = None
    for i in range(9):
        old, new = current.get(i), new_board.get(i)
        if old == new:
            continue
        if diff_index is not None:
            return None
        if old != 0 or new != 1:
            return None
        diff_index = i
    return diff_index


def is_valid_ai_move(board: Board, position: int) -> bool:
    return 0 <= position <= 8 and board.get(position) == 0
