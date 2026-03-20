from __future__ import annotations

import logging

from master.application.ports import AIStrategyPort, RobotPort, UnityPort, VisionPort
from master.domain.board import AI, Board
from master.domain.errors import PlacementError
from master.domain.models import Move

log = logging.getLogger(__name__)


class AITurnProcessor:
    def __init__(
        self,
        strategy: AIStrategyPort,
        robot: RobotPort,
        vision: VisionPort,
        unity: UnityPort,
    ) -> None:
        self._strategy = strategy
        self._robot = robot
        self._vision = vision
        self._unity = unity

    async def execute(self, board: Board, move_history: list[Move]) -> Board:
        await self._unity.set_state("thinking")

        decision = await self._strategy.decide(board, move_history)
        log.info(
            "AI decided: position=%d emotion=%s",
            decision.next_move, decision.emotion.value,
        )

        await self._unity.play_reaction(decision.emotion, decision.dialogue)

        result = await self._robot.place_piece(decision.next_move, AI)
        if not result.success:
            raise PlacementError(
                f"Robot failed at position {result.position}: {result.error_detail}"
            )

        return await self._verify_placement(board, decision.next_move)

    async def _verify_placement(self, board: Board, position: int) -> Board:
        expected = board.set(position, AI)
        actual = await self._vision.request_board_state()
        if actual != expected:
            raise PlacementError(
                f"Vision mismatch after placement at {position}: "
                f"expected={expected.to_list()}, actual={actual.to_list()}"
            )
        return expected
