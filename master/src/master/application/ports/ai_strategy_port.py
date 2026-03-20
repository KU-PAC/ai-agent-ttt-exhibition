from __future__ import annotations

from abc import ABC, abstractmethod

from master.domain.board import Board
from master.domain.models import AIDecision, Move

__all__ = ["AIStrategyPort"]


class AIStrategyPort(ABC):
    @abstractmethod
    async def decide(
        self, board: Board, move_history: list[Move],
    ) -> AIDecision: ...
