import asyncio

import pytest
from tests.mocks.mock_llm import MockAIStrategy, MockReactionGenerator
from tests.mocks.mock_robot import MockRobot
from tests.mocks.mock_unity import MockUnity
from tests.mocks.mock_vision import MockVision

from master.adapters.errors import RobotTimeoutError
from master.application.ai_turn import AITurnProcessor
from master.application.game_manager import GameManager
from master.application.human_turn import HumanTurnProcessor
from master.domain.board import Board
from master.domain.game_phase import GamePhase
from master.domain.models import AIDecision, Emotion


def _build_gm(
    vision: MockVision | None = None,
    robot: MockRobot | None = None,
    strategy: MockAIStrategy | None = None,
) -> tuple[GameManager, MockVision, MockRobot, MockUnity, MockAIStrategy]:
    vision = vision or MockVision()
    robot = robot or MockRobot()
    unity = MockUnity()
    strategy = strategy or MockAIStrategy()
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
    return gm, vision, robot, unity, strategy


class TestForceReset:
    @pytest.mark.asyncio
    async def test_force_reset_returns_to_standby(self):
        gm, vision, *_ = _build_gm()
        vision.set_responses([Board.initial()] * 100)

        await gm.start_game("human")
        await asyncio.sleep(0.05)
        assert gm.phase != GamePhase.STANDBY

        await gm.force_reset()
        assert gm.phase == GamePhase.STANDBY

    @pytest.mark.asyncio
    async def test_force_reset_clears_board(self):
        gm, *_ = _build_gm()
        await gm.force_reset()
        state = gm.get_internal_state()
        assert state["board"] == [0] * 9
        assert state["current_phase"] == "standby"


class TestClientDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_during_game_resets(self):
        gm, vision, *_ = _build_gm()
        vision.set_responses([Board.initial()] * 100)

        await gm.start_game("human")
        await asyncio.sleep(0.05)

        await gm.on_client_disconnected("vision")
        await asyncio.sleep(0.05)
        assert gm.phase == GamePhase.STANDBY

    @pytest.mark.asyncio
    async def test_disconnect_during_standby_no_reset(self):
        gm, *_ = _build_gm()
        assert gm.phase == GamePhase.STANDBY
        await gm.on_client_disconnected("vision")
        assert gm.phase == GamePhase.STANDBY


class TestRobotTimeout:
    @pytest.mark.asyncio
    async def test_robot_timeout_triggers_automatic_error_and_reset(self):
        human_board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        vision = MockVision(responses=[human_board, human_board])
        robot = MockRobot()
        robot.set_error(RobotTimeoutError("Robot timeout after 30.0s"))
        strategy = MockAIStrategy()
        strategy.set_decisions(
            [
                AIDecision(next_move=4, emotion=Emotion.NORMAL, dialogue="t"),
            ]
        )

        gm, vision_m, robot_m, unity, strategy_m = _build_gm(
            vision=vision,
            robot=robot,
            strategy=strategy,
        )
        await gm.start_game("human")
        await asyncio.sleep(0.3)

        assert gm.phase == GamePhase.STANDBY
        assert "error" in unity.state_calls


class TestGameOverFlow:
    @pytest.mark.asyncio
    async def test_game_over_resets_to_standby(self):
        human_boards = [
            Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0]),
            Board.from_list([1, 1, 0, 2, 0, 0, 0, 0, 0]),
            Board.from_list([1, 1, 1, 2, 2, 0, 0, 0, 0]),
        ]
        ai_decisions = [
            AIDecision(next_move=3, emotion=Emotion.NORMAL, dialogue="t"),
            AIDecision(next_move=4, emotion=Emotion.NORMAL, dialogue="t"),
        ]
        vision_responses = [
            human_boards[0],
            human_boards[0],
            Board.from_list([1, 0, 0, 2, 0, 0, 0, 0, 0]),
            human_boards[1],
            human_boards[1],
            Board.from_list([1, 1, 0, 2, 2, 0, 0, 0, 0]),
            human_boards[2],
            human_boards[2],
        ]
        vision = MockVision(vision_responses)
        robot = MockRobot()
        strategy = MockAIStrategy()
        strategy.set_decisions(ai_decisions)

        unity = MockUnity()
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
        await asyncio.sleep(0.5)

        assert gm.phase == GamePhase.STANDBY
        state = gm.get_internal_state()
        assert state["board"] == [0] * 9
        assert len(unity.reaction_calls) >= 1
        assert len(unity.board_calls) >= 3  # human, ai, human, ai, human moves + reset
        assert unity.board_calls[-1] == [0] * 9  # last call is reset


class TestGetInternalState:
    def test_initial_state(self):
        gm, *_ = _build_gm()
        state = gm.get_internal_state()
        assert state == {
            "board": [0, 0, 0, 0, 0, 0, 0, 0, 0],
            "current_phase": "standby",
        }
