import pytest

from master.application.ai_turn import AITurnProcessor
from master.domain.board import Board
from master.domain.errors import PlacementError
from master.domain.models import AIDecision, Emotion, PlacementResult
from tests.mocks.mock_llm import MockAIStrategy
from tests.mocks.mock_robot import MockRobot
from tests.mocks.mock_unity import MockUnity
from tests.mocks.mock_vision import MockVision


def _make_processor(
    strategy: MockAIStrategy | None = None,
    robot: MockRobot | None = None,
    vision: MockVision | None = None,
    unity: MockUnity | None = None,
) -> AITurnProcessor:
    return AITurnProcessor(
        strategy=strategy or MockAIStrategy(),
        robot=robot or MockRobot(),
        vision=vision or MockVision(),
        unity=unity or MockUnity(),
    )


class TestAITurnProcessor:
    @pytest.mark.asyncio
    async def test_normal_flow(self):
        board = Board.initial()
        expected_board = board.set(4, 2)

        strategy = MockAIStrategy()
        strategy.set_decisions(
            [
                AIDecision(next_move=4, emotion=Emotion.JOY, dialogue="ここだ！"),
            ]
        )
        vision = MockVision(responses=[expected_board])
        unity = MockUnity()

        proc = _make_processor(strategy=strategy, vision=vision, unity=unity)
        result = await proc.execute(board, [])

        assert result == expected_board
        assert "thinking" in unity.state_calls
        assert len(unity.reaction_calls) == 1
        assert unity.reaction_calls[0][0] == Emotion.JOY

    @pytest.mark.asyncio
    async def test_robot_failure_raises(self):
        board = Board.initial()
        strategy = MockAIStrategy()
        strategy.set_decisions(
            [
                AIDecision(next_move=4, emotion=Emotion.NEUTRAL, dialogue="test"),
            ]
        )
        robot = MockRobot()
        robot.set_next_result(
            PlacementResult(success=False, position=4, error_detail="motor error"),
        )

        proc = _make_processor(strategy=strategy, robot=robot)
        with pytest.raises(PlacementError, match="Robot failed"):
            await proc.execute(board, [])

    @pytest.mark.asyncio
    async def test_vision_mismatch_raises(self):
        board = Board.initial()
        strategy = MockAIStrategy()
        strategy.set_decisions(
            [
                AIDecision(next_move=4, emotion=Emotion.NEUTRAL, dialogue="test"),
            ]
        )
        wrong_board = board.set(0, 2)
        vision = MockVision(responses=[wrong_board])

        proc = _make_processor(strategy=strategy, vision=vision)
        with pytest.raises(PlacementError, match="Vision mismatch"):
            await proc.execute(board, [])
