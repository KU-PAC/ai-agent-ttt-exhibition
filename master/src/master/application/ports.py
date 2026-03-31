from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from master.domain.board import Board
from master.domain.models import (
    AIDecision,
    Emotion,
    GameResult,
    Move,
    PlacementResult,
    Reaction,
)


class AIStrategyPort(ABC):
    @abstractmethod
    async def decide(
        self,
        board: Board,
        move_history: list[Move],
    ) -> AIDecision: ...


class ReactionGeneratorPort(ABC):
    @abstractmethod
    async def generate(
        self,
        board: Board,
        position: int,
        move_history: list[Move],
    ) -> Reaction: ...

    @abstractmethod
    async def generate_game_over(
        self,
        board: Board,
        result: GameResult,
        move_history: list[Move],
    ) -> Reaction: ...


class LLMClientPort(ABC):
    @abstractmethod
    async def chat(
        self,
        system: str,
        user_message: str,
        timeout: float = 10.0,
    ) -> str: ...


class VisionPort(ABC):
    @abstractmethod
    async def request_board_state(self) -> Board: ...


class RobotPort(ABC):
    @abstractmethod
    async def place_piece(
        self,
        position: int,
        piece_type: int,
    ) -> PlacementResult: ...

    @abstractmethod
    async def reset_robot(self) -> None: ...


class UnityPort(ABC):
    @abstractmethod
    async def set_state(self, state: str) -> None: ...

    @abstractmethod
    async def play_reaction(
        self,
        emotion: Emotion,
        dialogue: str,
    ) -> None: ...

    @abstractmethod
    async def update_board(self, board: Board) -> None: ...


class GameManagerProtocol(Protocol):
    async def start_game(self, first_turn: str) -> None: ...
    async def force_reset(self) -> None: ...
    def get_internal_state(self) -> dict[str, Any]: ...
    async def on_client_disconnected(self, client_type: str) -> None: ...
