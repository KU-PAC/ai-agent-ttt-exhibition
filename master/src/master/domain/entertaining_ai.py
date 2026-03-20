from __future__ import annotations

import random
from enum import Enum

from master.domain.board import AI, HUMAN, Board
from master.domain.minimax import score_all_moves
from master.domain.models import Move

GOOD_MOVE_GAP = 2
DEFAULT_SKILL = 0.5
SKILL_WEIGHTS = {
    "optimal": 1.0,
    "good": 0.7,
    "mistake": 0.2,
    "blunder": 0.0,
}
ENTERTAINING_SKILL_THRESHOLD = 0.6
MID_TIER_HALF_WIDTH = 1


class MoveQuality(Enum):
    OPTIMAL = "optimal"
    GOOD = "good"
    MISTAKE = "mistake"
    BLUNDER = "blunder"


def evaluate_human_move(board_before: Board, position: int) -> MoveQuality:
    scored = score_all_moves(board_before, HUMAN)
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

    ai_wins_after = score_all_moves(board_before.set(position, HUMAN), AI)
    if ai_wins_after and ai_wins_after[0].is_winning:
        return MoveQuality.BLUNDER

    gap = best_score - move_score
    if gap == 0:
        return MoveQuality.OPTIMAL
    if gap <= GOOD_MOVE_GAP:
        return MoveQuality.GOOD
    return MoveQuality.MISTAKE


def estimate_skill(move_history: list[Move], boards_history: list[Board]) -> float:
    human_moves = [
        (boards_history[i], m.position)
        for i, m in enumerate(move_history)
        if m.player == HUMAN
    ]
    if not human_moves:
        return DEFAULT_SKILL

    total = sum(
        SKILL_WEIGHTS[evaluate_human_move(b, p).value]
        for b, p in human_moves
    )
    return total / len(human_moves)


def select_move(
    board: Board,
    move_history: list[Move],
    boards_history: list[Board],
) -> int:
    scored = score_all_moves(board, AI)
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
    if skill > ENTERTAINING_SKILL_THRESHOLD:
        safe_moves = [m for m in scored if m.score >= 0]
        pool = safe_moves if safe_moves else scored
        return pool[-1].position

    mid = len(scored) // 2
    start = max(0, mid - MID_TIER_HALF_WIDTH)
    end = min(len(scored), mid + MID_TIER_HALF_WIDTH + 1)
    return random.choice(scored[start:end]).position


def _last_human_quality(
    move_history: list[Move],
    boards_history: list[Board],
) -> MoveQuality | None:
    for i in range(len(move_history) - 1, -1, -1):
        if move_history[i].player == HUMAN:
            return evaluate_human_move(boards_history[i], move_history[i].position)
    return None
