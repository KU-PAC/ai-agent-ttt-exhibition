from __future__ import annotations

from abc import ABC, abstractmethod

from master.domain.board import Board
from master.domain.models import Move, Reaction

__all__ = ["ReactionGeneratorPort"]


class ReactionGeneratorPort(ABC):
    @abstractmethod
    async def generate(
        self, board: Board, position: int, move_history: list[Move],
    ) -> Reaction: ...
