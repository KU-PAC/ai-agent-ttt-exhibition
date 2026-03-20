from __future__ import annotations

from abc import ABC, abstractmethod

from master.domain.models import PlacementResult

__all__ = ["RobotPort"]


class RobotPort(ABC):
    @abstractmethod
    async def place_piece(
        self, position: int, piece_type: int,
    ) -> PlacementResult: ...

    @abstractmethod
    async def reset_robot(self) -> None: ...
