from __future__ import annotations

import asyncio
import logging

from master.application.ports.vision_port import VisionPort
from master.domain.board import Board
from master.domain.game_rule import find_human_move, is_valid_human_move

__all__ = ["HumanTurnProcessor"]

log = logging.getLogger(__name__)


class HumanTurnProcessor:
    POLL_INTERVAL: float = 1.0
    STABLE_COUNT_REQUIRED: int = 2

    def __init__(self, vision: VisionPort) -> None:
        self._vision = vision

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
                assert position is not None
                log.info("Human move confirmed at position %d", position)
                return candidate, position

            await asyncio.sleep(self.POLL_INTERVAL)

    @staticmethod
    def _validate_and_check_stability(
        current_board: Board,
        received_board: Board,
        prev_candidate: Board | None,
        stable_count: int,
    ) -> tuple[Board | None, int, bool]:
        if not is_valid_human_move(current_board, received_board):
            return None, 0, False

        if prev_candidate is not None and received_board == prev_candidate:
            new_count = stable_count + 1
            return received_board, new_count, new_count >= HumanTurnProcessor.STABLE_COUNT_REQUIRED
        return received_board, 1, 1 >= HumanTurnProcessor.STABLE_COUNT_REQUIRED
