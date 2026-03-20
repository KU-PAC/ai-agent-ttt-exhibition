from __future__ import annotations

from abc import ABC, abstractmethod

from master.domain.board import Board

__all__ = ["VisionPort"]


class VisionPort(ABC):
    @abstractmethod
    async def request_board_state(self) -> Board: ...
