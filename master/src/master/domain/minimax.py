from __future__ import annotations

from dataclasses import dataclass

from master.domain.board import AI, HUMAN, Board
from master.domain.game_rule import check_winner

WIN_SCORE = 10
WORST_CASE = -100
BEST_CASE = 100


@dataclass(frozen=True)
class ScoredMove:
    position: int
    score: int
    is_winning: bool
    is_blocking: bool


def minimax(board: Board, player: int, depth: int = 0) -> int:
    winner = check_winner(board)
    if winner == AI:
        return WIN_SCORE - depth
    if winner == HUMAN:
        return depth - WIN_SCORE
    if not board.empty_cells():
        return 0

    if player == AI:
        best = WORST_CASE
        for cell in board.empty_cells():
            score = minimax(board.set(cell, AI), HUMAN, depth + 1)
            best = max(best, score)
        return best
    else:
        best = BEST_CASE
        for cell in board.empty_cells():
            score = minimax(board.set(cell, HUMAN), AI, depth + 1)
            best = min(best, score)
        return best


def _would_win_next(board: Board, player: int) -> set[int]:
    winning_cells: set[int] = set()
    for cell in board.empty_cells():
        if check_winner(board.set(cell, player)) == player:
            winning_cells.add(cell)
    return winning_cells


def score_all_moves(board: Board, player: int) -> list[ScoredMove]:
    opponent = HUMAN if player == AI else AI
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

    moves.sort(key=lambda m: m.score, reverse=(player == AI))
    return moves
