import asyncio

import pytest

from master.application.ai_turn import AITurnProcessor
from master.application.game_manager import GameManager
from master.application.human_turn import HumanTurnProcessor
from master.domain.board import Board
from master.domain.game_phase import GamePhase
from tests.mocks.mock_llm import MockAIStrategy, MockReactionGenerator
from tests.mocks.mock_robot import MockRobot
from tests.mocks.mock_unity import MockUnity
from tests.mocks.mock_vision import MockVision


def _build_gm() -> tuple[GameManager, MockVision, MockRobot, MockUnity, MockAIStrategy]:
    vision = MockVision()
    robot = MockRobot()
    unity = MockUnity()
    strategy = MockAIStrategy()
    reaction_gen = MockReactionGenerator()
    human_turn = HumanTurnProcessor(vision=vision, poll_interval=0.0)
    ai_turn = AITurnProcessor(
        strategy=strategy, robot=robot, vision=vision, unity=unity,
    )
    gm = GameManager(
        vision=vision, robot=robot, unity=unity,
        human_turn=human_turn, ai_turn=ai_turn,
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


class TestGetInternalState:
    def test_initial_state(self):
        gm, *_ = _build_gm()
        state = gm.get_internal_state()
        assert state == {
            "board": [0, 0, 0, 0, 0, 0, 0, 0, 0],
            "current_phase": "standby",
        }
