from __future__ import annotations

import asyncio
import logging

from master.application.ai_turn import AITurnProcessor
from master.application.human_turn import HumanTurnProcessor
from master.application.ports import (
    ReactionGeneratorPort,
    RobotPort,
    UnityPort,
    VisionPort,
)
from master.domain.board import AI, BOARD_SIZE, HUMAN, Board
from master.domain.errors import InvalidGameStateError
from master.domain.game_phase import GamePhase
from master.domain.game_rule import judge
from master.domain.models import GameResult, Move, make_fallback_reaction

log = logging.getLogger(__name__)


class GameManager:
    def __init__(
        self,
        vision: VisionPort,
        robot: RobotPort,
        unity: UnityPort,
        human_turn: HumanTurnProcessor,
        ai_turn: AITurnProcessor,
        reaction_generator: ReactionGeneratorPort,
        game_over_wait: float = 5.0,
    ) -> None:
        self._vision = vision
        self._robot = robot
        self._unity = unity
        self._human_turn = human_turn
        self._ai_turn = ai_turn
        self._reaction_generator = reaction_generator
        self._game_over_wait = game_over_wait

        self._board = Board.initial()
        self._phase = GamePhase.STANDBY
        self._move_history: list[Move] = []
        self._boards_history: list[Board] = []
        self._game_loop_task: asyncio.Task[None] | None = None

    @property
    def phase(self) -> GamePhase:
        return self._phase

    async def start_game(self, first_turn: str) -> None:
        if self._phase != GamePhase.STANDBY:
            raise InvalidGameStateError(
                f"Cannot start game in phase {self._phase.value}"
            )
        log.info("Starting game, first_turn=%s", first_turn)
        self._board = Board.initial()
        self._move_history = []
        self._boards_history = []
        self._game_loop_task = asyncio.create_task(self._game_loop(first_turn))

    async def force_reset(self) -> None:
        log.info("Force reset requested")
        if self._game_loop_task and not self._game_loop_task.done():
            self._game_loop_task.cancel()
            try:
                await self._game_loop_task
            except asyncio.CancelledError:
                pass
        await self._execute_reset()

    def get_internal_state(self) -> dict:
        return {
            "board": self._board.to_list(),
            "current_phase": self._phase.value,
        }

    async def _game_loop(self, first_turn: str) -> None:
        current_turn = first_turn
        try:
            while True:
                if current_turn == "human":
                    await self._run_human_turn()
                else:
                    await self._run_ai_turn()

                result = judge(self._board)
                if result != GameResult.ONGOING:
                    await self._handle_game_over(result)
                    return

                current_turn = "ai" if current_turn == "human" else "human"
        except asyncio.CancelledError:
            log.info("Game loop cancelled")
            raise
        except Exception as e:
            log.error("Game error: %s", e)
            await self._handle_error()

    async def _run_human_turn(self) -> None:
        self._phase = GamePhase.HUMAN_TURN
        await self._unity.set_state("human_turn")
        board_before = self._board
        self._board, position = await self._human_turn.execute(self._board)
        self._boards_history.append(board_before)
        self._move_history.append(Move(player=HUMAN, position=position))
        log.info("Human placed at %d", position)

    async def _run_ai_turn(self) -> None:
        self._phase = GamePhase.AI_THINKING
        board_before = self._board
        self._board = await self._ai_turn.execute(self._board, self._move_history)
        position = _find_diff(board_before, self._board)
        if position is not None:
            self._boards_history.append(board_before)
            self._move_history.append(Move(player=AI, position=position))
            log.info("AI placed at %d", position)

    async def _handle_game_over(self, result: GameResult) -> None:
        self._phase = GamePhase.GAME_OVER
        log.info("Game over: %s", result.value)

        try:
            reaction = await self._reaction_generator.generate_game_over(
                self._board,
                result,
                self._move_history,
            )
        except Exception:
            log.warning("Game over reaction generation failed, using fallback")
            reaction = make_fallback_reaction()

        await self._unity.play_reaction(reaction.emotion, reaction.dialogue)
        await asyncio.sleep(self._game_over_wait)
        await self._execute_reset()

    async def _handle_error(self) -> None:
        log.info("Handling error, sending error state to Unity")
        try:
            await self._unity.set_state("error")
        except Exception:
            log.warning("Failed to send error state to Unity")
        await self._execute_reset()

    async def _execute_reset(self) -> None:
        self._phase = GamePhase.RESETTING
        log.info("Executing reset")
        try:
            await self._robot.reset_robot()
        except Exception:
            log.warning("Robot reset failed, continuing reset")
        try:
            await self._unity.set_state("idle")
        except Exception:
            log.warning("Unity idle notification failed, continuing reset")
        self._board = Board.initial()
        self._phase = GamePhase.STANDBY
        self._move_history = []
        self._boards_history = []
        log.info("Reset complete, now STANDBY")

    async def on_client_disconnected(self, client_type: str) -> None:
        if self._phase not in (GamePhase.STANDBY, GamePhase.RESETTING):
            log.warning(
                "Client %s disconnected during game, forcing reset", client_type
            )
            await self.force_reset()


def _find_diff(before: Board, after: Board) -> int | None:
    for i in range(BOARD_SIZE):
        if before.get(i) != after.get(i):
            return i
    return None
