import pytest

from master.application.human_turn import HumanTurnProcessor
from master.domain.board import Board
from tests.mocks.mock_vision import MockVision


class TestHumanPolling:
    @pytest.mark.asyncio
    async def test_two_consecutive_same_confirms(self):
        current = Board.initial()
        valid = Board.from_list([0, 0, 0, 0, 1, 0, 0, 0, 0])
        vision = MockVision(responses=[valid, valid])
        proc = HumanTurnProcessor(vision=vision)
        proc.POLL_INTERVAL = 0.0

        board, pos = await proc.execute(current)
        assert pos == 4
        assert vision.call_count == 2

    @pytest.mark.asyncio
    async def test_change_midway_resets_count(self):
        current = Board.initial()
        a = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        b = Board.from_list([0, 1, 0, 0, 0, 0, 0, 0, 0])
        vision = MockVision(responses=[a, b, b])
        proc = HumanTurnProcessor(vision=vision)
        proc.POLL_INTERVAL = 0.0

        board, pos = await proc.execute(current)
        assert pos == 1
        assert vision.call_count == 3

    @pytest.mark.asyncio
    async def test_invalid_boards_skipped(self):
        current = Board.initial()
        invalid = Board.from_list([1, 1, 0, 0, 0, 0, 0, 0, 0])
        valid = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        vision = MockVision(responses=[invalid, invalid, valid, valid])
        proc = HumanTurnProcessor(vision=vision)
        proc.POLL_INTERVAL = 0.0

        board, pos = await proc.execute(current)
        assert pos == 0
        assert vision.call_count == 4
