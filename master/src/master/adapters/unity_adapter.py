from __future__ import annotations

import logging

from master.adapters.ws_server import ClientType, WebSocketServer
from master.application.ports import UnityPort
from master.domain.board import Board
from master.domain.models import Emotion

log = logging.getLogger(__name__)


class UnityWebSocketAdapter(UnityPort):
    def __init__(self, ws_server: WebSocketServer) -> None:
        self._ws_server = ws_server

    async def set_state(self, state: str) -> None:
        conn = self._ws_server.get_client(ClientType.UNITY)
        if conn is None:
            log.warning("Unity not connected, skipping set_state(%s)", state)
            return
        await conn.send({"type": "set_state", "payload": {"state": state}})

    async def play_reaction(self, emotion: Emotion, dialogue: str) -> None:
        conn = self._ws_server.get_client(ClientType.UNITY)
        if conn is None:
            log.warning("Unity not connected, skipping play_reaction")
            return
        await conn.send(
            {
                "type": "play_reaction",
                "payload": {"emotion": emotion.value, "dialogue": dialogue},
            }
        )

    async def update_board(self, board: Board) -> None:
        conn = self._ws_server.get_client(ClientType.UNITY)
        if conn is None:
            log.warning("Unity not connected, skipping update_board")
            return
        await conn.send(
            {
                "type": "board_update",
                "payload": {"board": board.to_list()},
            }
        )
