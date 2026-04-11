from __future__ import annotations

from master.application.ports import (
    AIStrategyPort,
    LLMClientPort,
    ReactionGeneratorPort,
)
from master.domain.board import Board
from master.domain.models import AIDecision, Emotion, GameResult, Move, Reaction


class MockAIStrategy(AIStrategyPort):
    def __init__(self) -> None:
        self._decisions: list[AIDecision] = []

    def set_decisions(self, decisions: list[AIDecision]) -> None:
        self._decisions = list(decisions)

    async def decide(
        self,
        board: Board,
        move_history: list[Move],
    ) -> AIDecision:
        if self._decisions:
            return self._decisions.pop(0)
        empty = board.empty_cells()
        return AIDecision(
            next_move=empty[0],
            emotion=Emotion.NORMAL,
            dialogue="テスト",
        )


class MockReactionGenerator(ReactionGeneratorPort):
    def __init__(self, reaction: Reaction | None = None) -> None:
        self._reaction = reaction or Reaction(
            emotion=Emotion.NORMAL,
            dialogue="テスト",
        )

    async def generate(
        self,
        board: Board,
        position: int,
        move_history: list[Move],
    ) -> Reaction:
        return self._reaction

    async def generate_game_over(
        self,
        board: Board,
        result: GameResult,
        move_history: list[Move],
    ) -> Reaction:
        return self._reaction


class MockLLMClient(LLMClientPort):
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])
        self.call_count = 0

    async def chat(
        self,
        system: str,
        user_message: str,
        timeout: float = 10.0,
    ) -> str:
        self.call_count += 1
        if self._responses:
            return self._responses.pop(0)
        return '{"emotion": "normal", "dialogue": "テスト"}'
