import pytest

from master.application.human_turn import HumanTurnProcessor
from master.domain.board import Board
from tests.mocks.mock_vision import MockVision


class TestHumanTurnProcessor:
    @pytest.mark.asyncio
    async def test_stable_move_confirmed(self):
        current = Board.initial()
        moved = Board.from_list([0, 0, 0, 0, 1, 0, 0, 0, 0])
        vision = MockVision(responses=[moved, moved])
        processor = HumanTurnProcessor(vision=vision, poll_interval=0.0)

        board, position = await processor.execute(current)
        assert position == 4
        assert board == moved
        assert vision.call_count == 2

    @pytest.mark.asyncio
    async def test_unstable_then_stable(self):
        current = Board.initial()
        move_a = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        move_b = Board.from_list([0, 0, 0, 0, 1, 0, 0, 0, 0])
        vision = MockVision(responses=[move_a, move_b, move_b])
        processor = HumanTurnProcessor(vision=vision, poll_interval=0.0)

        board, position = await processor.execute(current)
        assert position == 4
        assert vision.call_count == 3

    @pytest.mark.asyncio
    async def test_invalid_board_ignored(self):
        current = Board.initial()
        invalid = Board.from_list([2, 0, 0, 0, 0, 0, 0, 0, 0])
        valid = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        vision = MockVision(responses=[invalid, valid, valid])
        processor = HumanTurnProcessor(vision=vision, poll_interval=0.0)

        board, position = await processor.execute(current)
        assert position == 0
        assert vision.call_count == 3


class TestStabilityLogic:
    def test_valid_move_starts_count(self):
        current = Board.initial()
        received = Board.from_list([0, 0, 0, 0, 1, 0, 0, 0, 0])
        proc = HumanTurnProcessor(vision=MockVision(), poll_interval=0.0)
        candidate, count, stable = proc._validate_and_check_stability(
            current, received, None, 0,
        )
        assert candidate == received
        assert count == 1
        assert stable is False

    def test_same_move_twice_is_stable(self):
        current = Board.initial()
        received = Board.from_list([0, 0, 0, 0, 1, 0, 0, 0, 0])
        proc = HumanTurnProcessor(vision=MockVision(), poll_interval=0.0)
        candidate, count, stable = proc._validate_and_check_stability(
            current, received, received, 1,
        )
        assert stable is True
        assert count == 2

    def test_different_valid_move_resets(self):
        current = Board.initial()
        prev = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        new = Board.from_list([0, 1, 0, 0, 0, 0, 0, 0, 0])
        proc = HumanTurnProcessor(vision=MockVision(), poll_interval=0.0)
        candidate, count, stable = proc._validate_and_check_stability(
            current, new, prev, 1,
        )
        assert candidate == new
        assert count == 1
        assert stable is False

    def test_invalid_move_resets(self):
        current = Board.initial()
        invalid = Board.from_list([2, 0, 0, 0, 0, 0, 0, 0, 0])
        proc = HumanTurnProcessor(vision=MockVision(), poll_interval=0.0)
        candidate, count, stable = proc._validate_and_check_stability(
            current, invalid, None, 1,
        )
        assert candidate is None
        assert count == 0
        assert stable is False
