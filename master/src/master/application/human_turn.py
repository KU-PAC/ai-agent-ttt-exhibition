from __future__ import annotations

import asyncio
import logging

from master.application.ports import VisionPort
from master.domain.board import Board
from master.domain.game_rule import find_human_move, is_valid_human_move

log = logging.getLogger(__name__)


class HumanTurnProcessor:
    def __init__(
        self,
        vision: VisionPort,
        poll_interval: float = 1.0,
        stable_count_required: int = 2,
    ) -> None:
        self._vision = vision
        self._poll_interval = poll_interval
        self._stable_count_required = stable_count_required

    async def execute(self, current_board: Board) -> tuple[Board, int]:
        candidate: Board | None = None
        stable_count = 0

        while True:
            received = await self._vision.request_board_state()
            candidate, stable_count, is_stable = self._validate_and_check_stability(
                current_board, received, candidate, stable_count,
            )
            if is_stable and candidate is not None:
                position = find_human_move(current_board, candidate)
                if position is None:
                    candidate = None
                    stable_count = 0
                    continue
                log.info("Human move confirmed at position %d", position)
                return candidate, position

            await asyncio.sleep(self._poll_interval)

    def _validate_and_check_stability(
        self,
        current_board: Board,
        received_board: Board,
        prev_candidate: Board | None,
        stable_count: int,
    ) -> tuple[Board | None, int, bool]:
        if not is_valid_human_move(current_board, received_board):
            return None, 0, False

        if prev_candidate is not None and received_board == prev_candidate:
            new_count = stable_count + 1
            return received_board, new_count, new_count >= self._stable_count_required
        return received_board, 1, 1 >= self._stable_count_required
