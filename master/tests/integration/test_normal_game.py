import asyncio

import pytest

from master.application.ai_turn import AITurnProcessor
from master.application.game_manager import GameManager
from master.application.human_turn import HumanTurnProcessor
from master.domain.board import Board
from master.domain.game_phase import GamePhase
from master.domain.models import AIDecision, Emotion
from tests.mocks.mock_llm import MockAIStrategy
from tests.mocks.mock_robot import MockRobot
from tests.mocks.mock_unity import MockUnity
from tests.mocks.mock_vision import MockVision


def _build_game(
    vision_responses: list[Board],
    ai_decisions: list[AIDecision],
) -> tuple[GameManager, MockVision, MockRobot, MockUnity, MockAIStrategy]:
    vision = MockVision(vision_responses)
    robot = MockRobot()
    unity = MockUnity()
    strategy = MockAIStrategy()
    strategy.set_decisions(ai_decisions)

    human_turn = HumanTurnProcessor(vision=vision)
    human_turn.POLL_INTERVAL = 0.0
    ai_turn = AITurnProcessor(
        strategy=strategy, robot=robot, vision=vision, unity=unity,
    )
    game_manager = GameManager(
        strategy=strategy, vision=vision, robot=robot,
        unity=unity, human_turn=human_turn, ai_turn=ai_turn,
    )
    return game_manager, vision, robot, unity, strategy


class TestNormalGame:
    @pytest.mark.asyncio
    async def test_human_wins_full_game(self):
        # Human: 0,1,2 (top row). AI: 3,4
        # Turns: H0, A3, H1, A4, H2 → human wins
        human_boards = [
            Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0]),
            Board.from_list([1, 1, 0, 2, 0, 0, 0, 0, 0]),
            Board.from_list([1, 1, 1, 2, 2, 0, 0, 0, 0]),
        ]
        ai_decisions = [
            AIDecision(next_move=3, emotion=Emotion.NEUTRAL, dialogue="t"),
            AIDecision(next_move=4, emotion=Emotion.NEUTRAL, dialogue="t"),
        ]

        # Vision responses: H poll×2, AI verify, H poll×2, AI verify, H poll×2
        vision_responses = [
            human_boards[0], human_boards[0],  # H turn 1 stable
            Board.from_list([1, 0, 0, 2, 0, 0, 0, 0, 0]),  # AI verify
            human_boards[1], human_boards[1],  # H turn 2 stable
            Board.from_list([1, 1, 0, 2, 2, 0, 0, 0, 0]),  # AI verify
            human_boards[2], human_boards[2],  # H turn 3 stable
        ]

        gm, *_ = _build_game(vision_responses, ai_decisions)
        await gm.start_game("human")
        await asyncio.sleep(0.5)

        # Wait for game to finish
        for _ in range(50):
            if gm.phase == GamePhase.STANDBY:
                break
            await asyncio.sleep(0.1)

        assert gm.phase == GamePhase.STANDBY

    @pytest.mark.asyncio
    async def test_game_ends_in_standby(self):
        board_after_ai = Board.from_list([0, 0, 0, 0, 2, 0, 0, 0, 0])
        human_move = Board.from_list([1, 0, 0, 0, 2, 0, 0, 0, 0])
        ai2_board = Board.from_list([1, 0, 0, 2, 2, 0, 0, 0, 0])
        human_move2 = Board.from_list([1, 1, 0, 2, 2, 0, 0, 0, 0])
        ai3_board = Board.from_list([1, 1, 0, 2, 2, 0, 2, 0, 0])
        human_move3 = Board.from_list([1, 1, 1, 2, 2, 0, 2, 0, 0])

        vision_responses = [
            board_after_ai,  # AI verify
            human_move, human_move,  # H stable
            ai2_board,  # AI verify
            human_move2, human_move2,  # H stable
            ai3_board,  # AI verify
            human_move3, human_move3,  # H stable — H wins
        ]
        ai_decisions = [
            AIDecision(next_move=4, emotion=Emotion.FUN, dialogue="t"),
            AIDecision(next_move=3, emotion=Emotion.FUN, dialogue="t"),
            AIDecision(next_move=6, emotion=Emotion.FUN, dialogue="t"),
        ]

        gm, *_ = _build_game(vision_responses, ai_decisions)
        await gm.start_game("ai")

        for _ in range(100):
            if gm.phase == GamePhase.STANDBY:
                break
            await asyncio.sleep(0.1)

        assert gm.phase == GamePhase.STANDBY
