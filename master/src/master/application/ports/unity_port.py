from __future__ import annotations

from abc import ABC, abstractmethod

from master.domain.models import Emotion

__all__ = ["UnityPort"]


class UnityPort(ABC):
    @abstractmethod
    async def set_state(self, state: str) -> None: ...

    @abstractmethod
    async def play_reaction(
        self, emotion: Emotion, dialogue: str,
    ) -> None: ...
