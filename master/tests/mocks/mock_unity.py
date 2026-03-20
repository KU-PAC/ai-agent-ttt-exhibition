from __future__ import annotations

from master.application.ports import UnityPort
from master.domain.models import Emotion


class MockUnity(UnityPort):
    def __init__(self) -> None:
        self.state_calls: list[str] = []
        self.reaction_calls: list[tuple[Emotion, str]] = []

    async def set_state(self, state: str) -> None:
        self.state_calls.append(state)

    async def play_reaction(self, emotion: Emotion, dialogue: str) -> None:
        self.reaction_calls.append((emotion, dialogue))
