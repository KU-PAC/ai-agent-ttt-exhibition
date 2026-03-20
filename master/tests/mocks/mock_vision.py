from __future__ import annotations

from master.application.ports.vision_port import VisionPort
from master.domain.board import Board


class MockVision(VisionPort):
    def __init__(self, responses: list[Board] | None = None) -> None:
        self._responses = list(responses or [])
        self._call_count = 0

    def set_responses(self, responses: list[Board]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    async def request_board_state(self) -> Board:
        self._call_count += 1
        if self._responses:
            return self._responses.pop(0)
        return Board.initial()
