from __future__ import annotations

import asyncio
import logging

from master.application.ports import AIStrategyPort, ReactionGeneratorPort
from master.domain.board import Board
from master.domain.entertaining_ai import select_move
from master.domain.models import AIDecision, Move, make_fallback_reaction

log = logging.getLogger(__name__)


class AlgorithmStrategy(AIStrategyPort):
    def __init__(self, reaction_generator: ReactionGeneratorPort) -> None:
        self._reaction_generator = reaction_generator

    async def decide(
        self, board: Board, move_history: list[Move],
    ) -> AIDecision:
        boards_history = _reconstruct_boards(move_history)
        position = select_move(board, move_history, boards_history)
        log.info("Algorithm selected position %d", position)

        try:
            reaction = await self._reaction_generator.generate(
                board, position, move_history,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("Reaction generation failed, using fallback")
            reaction = make_fallback_reaction()

        return AIDecision(
            next_move=position,
            emotion=reaction.emotion,
            dialogue=reaction.dialogue,
        )


def _reconstruct_boards(move_history: list[Move]) -> list[Board]:
    boards: list[Board] = []
    current = Board.initial()
    for move in move_history:
        boards.append(current)
        current = current.set(move.position, move.player)
    return boards
