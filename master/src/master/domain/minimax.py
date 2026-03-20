from __future__ import annotations

from dataclasses import dataclass

from master.domain.board import Board
from master.domain.game_rule import check_winner

__all__ = ["ScoredMove", "minimax", "score_all_moves"]


@dataclass(frozen=True)
class ScoredMove:
    position: int
    score: int
    is_winning: bool
    is_blocking: bool


def minimax(board: Board, player: int, depth: int = 0) -> int:
    winner = check_winner(board)
    if winner == 2:
        return 10 - depth
    if winner == 1:
        return depth - 10
    if not board.empty_cells():
        return 0

    if player == 2:
        best = -100
        for cell in board.empty_cells():
            score = minimax(board.set(cell, 2), 1, depth + 1)
            best = max(best, score)
        return best
    else:
        best = 100
        for cell in board.empty_cells():
            score = minimax(board.set(cell, 1), 2, depth + 1)
            best = min(best, score)
        return best


def _would_win_next(board: Board, player: int) -> set[int]:
    winning_cells: set[int] = set()
    for cell in board.empty_cells():
        if check_winner(board.set(cell, player)) == player:
            winning_cells.add(cell)
    return winning_cells


def score_all_moves(board: Board, player: int) -> list[ScoredMove]:
    opponent = 1 if player == 2 else 2
    opponent_winning = _would_win_next(board, opponent)

    moves: list[ScoredMove] = []
    for cell in board.empty_cells():
        next_board = board.set(cell, player)
        score = minimax(next_board, opponent, depth=1)
        is_winning = check_winner(next_board) == player
        is_blocking = cell in opponent_winning
        moves.append(ScoredMove(
            position=cell,
            score=score,
            is_winning=is_winning,
            is_blocking=is_blocking,
        ))

    moves.sort(key=lambda m: m.score, reverse=(player == 2))
    return moves
