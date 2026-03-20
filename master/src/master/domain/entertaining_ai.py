from __future__ import annotations

import random
from enum import Enum

from master.domain.board import Board
from master.domain.minimax import score_all_moves
from master.domain.models import Move

__all__ = [
    "MoveQuality",
    "evaluate_human_move",
    "estimate_skill",
    "select_move",
]


class MoveQuality(Enum):
    OPTIMAL = "optimal"
    GOOD = "good"
    MISTAKE = "mistake"
    BLUNDER = "blunder"


def evaluate_human_move(board_before: Board, position: int) -> MoveQuality:
    scored = score_all_moves(board_before, 1)
    if not scored:
        return MoveQuality.OPTIMAL

    best_score = scored[0].score
    move_score: int | None = None
    for m in scored:
        if m.position == position:
            move_score = m.score
            break

    if move_score is None:
        return MoveQuality.BLUNDER

    ai_wins_after = score_all_moves(board_before.set(position, 1), 2)
    if ai_wins_after and ai_wins_after[0].is_winning:
        return MoveQuality.BLUNDER

    gap = best_score - move_score
    if gap == 0:
        return MoveQuality.OPTIMAL
    if gap <= 2:
        return MoveQuality.GOOD
    return MoveQuality.MISTAKE


def estimate_skill(move_history: list[Move], boards_history: list[Board]) -> float:
    human_moves = [
        (boards_history[i], m.position)
        for i, m in enumerate(move_history)
        if m.player == 1
    ]
    if not human_moves:
        return 0.5

    weights = {
        MoveQuality.OPTIMAL: 1.0,
        MoveQuality.GOOD: 0.7,
        MoveQuality.MISTAKE: 0.2,
        MoveQuality.BLUNDER: 0.0,
    }
    total = sum(weights[evaluate_human_move(b, p)] for b, p in human_moves)
    return total / len(human_moves)


def select_move(
    board: Board,
    move_history: list[Move],
    boards_history: list[Board],
) -> int:
    scored = score_all_moves(board, 2)
    if not scored:
        return board.empty_cells()[0]

    winning_moves = [m for m in scored if m.is_winning]
    if winning_moves:
        return winning_moves[0].position

    blocking_moves = [m for m in scored if m.is_blocking]
    if blocking_moves:
        return blocking_moves[0].position

    last_human_quality = _last_human_quality(move_history, boards_history)
    if last_human_quality in (MoveQuality.MISTAKE, MoveQuality.BLUNDER):
        return scored[0].position

    skill = estimate_skill(move_history, boards_history)
    if skill > 0.6:
        safe_moves = [m for m in scored if m.score >= 0]
        pool = safe_moves if safe_moves else scored
        return pool[-1].position

    mid = len(scored) // 2
    start = max(0, mid - 1)
    end = min(len(scored), mid + 2)
    return random.choice(scored[start:end]).position


def _last_human_quality(
    move_history: list[Move],
    boards_history: list[Board],
) -> MoveQuality | None:
    for i in range(len(move_history) - 1, -1, -1):
        if move_history[i].player == 1:
            return evaluate_human_move(boards_history[i], move_history[i].position)
    return None
