from __future__ import annotations

from master.application.ports.robot_port import RobotPort
from master.domain.models import PlacementResult


class MockRobot(RobotPort):
    def __init__(self) -> None:
        self._next_result: PlacementResult | None = None
        self._place_calls: list[tuple[int, int]] = []
        self._reset_count = 0

    def set_next_result(self, result: PlacementResult) -> None:
        self._next_result = result

    @property
    def place_calls(self) -> list[tuple[int, int]]:
        return self._place_calls

    @property
    def reset_count(self) -> int:
        return self._reset_count

    async def place_piece(
        self, position: int, piece_type: int,
    ) -> PlacementResult:
        self._place_calls.append((position, piece_type))
        if self._next_result:
            return self._next_result
        return PlacementResult(success=True, position=position, error_detail=None)

    async def reset_robot(self) -> None:
        self._reset_count += 1
