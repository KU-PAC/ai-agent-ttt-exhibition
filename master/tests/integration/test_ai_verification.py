import asyncio

import pytest
from tests.mocks.mock_llm import MockAIStrategy, MockReactionGenerator
from tests.mocks.mock_robot import MockRobot
from tests.mocks.mock_unity import MockUnity
from tests.mocks.mock_vision import MockVision

from master.application.ai_turn import AITurnProcessor
from master.application.game_manager import GameManager
from master.application.human_turn import HumanTurnProcessor
from master.domain.board import Board
from master.domain.errors import PlacementError
from master.domain.game_phase import GamePhase
from master.domain.models import AIDecision, Emotion, PlacementResult


class TestAIVerificationUnit:
    @pytest.mark.asyncio
    async def test_vision_mismatch_raises(self):
        board = Board.initial()
        strategy = MockAIStrategy()
        strategy.set_decisions(
            [
                AIDecision(next_move=4, emotion=Emotion.NORMAL, dialogue="t"),
            ]
        )
        wrong_board = board.set(0, 2)
        vision = MockVision(responses=[wrong_board])
        proc = AITurnProcessor(
            strategy=strategy,
            robot=MockRobot(),
            vision=vision,
            unity=MockUnity(),
        )
        with pytest.raises(PlacementError, match="Vision mismatch"):
            await proc.execute(board, [])

    @pytest.mark.asyncio
    async def test_robot_failure_raises(self):
        board = Board.initial()
        strategy = MockAIStrategy()
        strategy.set_decisions(
            [
                AIDecision(next_move=4, emotion=Emotion.NORMAL, dialogue="t"),
            ]
        )
        robot = MockRobot()
        robot.set_next_result(
            PlacementResult(success=False, position=4, error_detail="jam"),
        )
        proc = AITurnProcessor(
            strategy=strategy,
            robot=robot,
            vision=MockVision(),
            unity=MockUnity(),
        )
        with pytest.raises(PlacementError, match="Robot failed"):
            await proc.execute(board, [])


class TestAIVerificationGameManager:
    @pytest.mark.asyncio
    async def test_vision_mismatch_triggers_error_and_reset(self):
        human_board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        wrong_ai_board = Board.from_list([1, 2, 0, 0, 0, 0, 0, 0, 0])
        vision = MockVision(
            responses=[
                human_board,
                human_board,
                wrong_ai_board,
            ]
        )
        robot = MockRobot()
        unity = MockUnity()
        strategy = MockAIStrategy()
        strategy.set_decisions(
            [
                AIDecision(next_move=4, emotion=Emotion.NORMAL, dialogue="t"),
            ]
        )
        reaction_gen = MockReactionGenerator()
        human_turn = HumanTurnProcessor(vision=vision, poll_interval=0.0)
        ai_turn = AITurnProcessor(
            strategy=strategy,
            robot=robot,
            vision=vision,
            unity=unity,
        )
        gm = GameManager(
            vision=vision,
            robot=robot,
            unity=unity,
            human_turn=human_turn,
            ai_turn=ai_turn,
            reaction_generator=reaction_gen,
            game_over_wait=0.0,
        )
        await gm.start_game("human")
        await asyncio.sleep(0.3)

        assert gm.phase == GamePhase.STANDBY
        assert "error" in unity.state_calls

    @pytest.mark.asyncio
    async def test_robot_failure_triggers_error_and_reset(self):
        human_board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        vision = MockVision(
            responses=[
                human_board,
                human_board,
            ]
        )
        robot = MockRobot()
        robot.set_next_result(
            PlacementResult(success=False, position=4, error_detail="motor"),
        )
        unity = MockUnity()
        strategy = MockAIStrategy()
        strategy.set_decisions(
            [
                AIDecision(next_move=4, emotion=Emotion.NORMAL, dialogue="t"),
            ]
        )
        reaction_gen = MockReactionGenerator()
        human_turn = HumanTurnProcessor(vision=vision, poll_interval=0.0)
        ai_turn = AITurnProcessor(
            strategy=strategy,
            robot=robot,
            vision=vision,
            unity=unity,
        )
        gm = GameManager(
            vision=vision,
            robot=robot,
            unity=unity,
            human_turn=human_turn,
            ai_turn=ai_turn,
            reaction_generator=reaction_gen,
            game_over_wait=0.0,
        )
        await gm.start_game("human")
        await asyncio.sleep(0.3)

        assert gm.phase == GamePhase.STANDBY
        assert "error" in unity.state_calls
