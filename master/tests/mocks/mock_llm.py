from __future__ import annotations

from master.application.ports.ai_strategy_port import AIStrategyPort
from master.application.ports.reaction_generator_port import ReactionGeneratorPort
from master.domain.board import Board
from master.domain.models import AIDecision, Emotion, Move, Reaction


class MockAIStrategy(AIStrategyPort):
    def __init__(self) -> None:
        self._decisions: list[AIDecision] = []

    def set_decisions(self, decisions: list[AIDecision]) -> None:
        self._decisions = list(decisions)

    async def decide(
        self, board: Board, move_history: list[Move],
    ) -> AIDecision:
        if self._decisions:
            return self._decisions.pop(0)
        empty = board.empty_cells()
        return AIDecision(
            next_move=empty[0],
            emotion=Emotion.NEUTRAL,
            dialogue="テスト",
        )


class MockReactionGenerator(ReactionGeneratorPort):
    def __init__(self, reaction: Reaction | None = None) -> None:
        self._reaction = reaction or Reaction(
            emotion=Emotion.NEUTRAL, dialogue="テスト",
        )

    async def generate(
        self, board: Board, position: int, move_history: list[Move],
    ) -> Reaction:
        return self._reaction
