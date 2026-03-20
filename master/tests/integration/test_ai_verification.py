import pytest

from master.application.ai_turn import AITurnProcessor
from master.domain.board import Board
from master.domain.errors import PlacementError
from master.domain.models import AIDecision, Emotion, PlacementResult
from tests.mocks.mock_llm import MockAIStrategy
from tests.mocks.mock_robot import MockRobot
from tests.mocks.mock_unity import MockUnity
from tests.mocks.mock_vision import MockVision


class TestAIVerification:
    @pytest.mark.asyncio
    async def test_vision_mismatch_after_success(self):
        board = Board.initial()
        strategy = MockAIStrategy()
        strategy.set_decisions([
            AIDecision(next_move=4, emotion=Emotion.NEUTRAL, dialogue="t"),
        ])
        wrong_board = board.set(0, 2)
        vision = MockVision(responses=[wrong_board])
        robot = MockRobot()
        unity = MockUnity()

        proc = AITurnProcessor(
            strategy=strategy, robot=robot, vision=vision, unity=unity,
        )
        with pytest.raises(PlacementError, match="Vision mismatch"):
            await proc.execute(board, [])

    @pytest.mark.asyncio
    async def test_robot_failure(self):
        board = Board.initial()
        strategy = MockAIStrategy()
        strategy.set_decisions([
            AIDecision(next_move=4, emotion=Emotion.NEUTRAL, dialogue="t"),
        ])
        robot = MockRobot()
        robot.set_next_result(
            PlacementResult(success=False, position=4, error_detail="jam"),
        )

        proc = AITurnProcessor(
            strategy=strategy, robot=robot,
            vision=MockVision(), unity=MockUnity(),
        )
        with pytest.raises(PlacementError, match="Robot failed"):
            await proc.execute(board, [])
