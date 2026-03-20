from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from master.application.ports.vision_port import VisionPort
from master.domain.board import Board
from master.domain.errors import VisionTimeoutError

if TYPE_CHECKING:
    from master.adapters.ws_server import WebSocketServer

__all__ = ["VisionWebSocketAdapter"]

log = logging.getLogger(__name__)

TIMEOUT = 1.0
MAX_RETRIES = 3


class VisionWebSocketAdapter(VisionPort):
    def __init__(self, ws_server: WebSocketServer) -> None:
        self._ws_server = ws_server

    async def request_board_state(self) -> Board:
        from master.adapters.ws_server import ClientType

        for attempt in range(1, MAX_RETRIES + 1):
            conn = self._ws_server.get_client(ClientType.VISION)
            if conn is None:
                raise VisionTimeoutError("Vision client not connected")
            try:
                response = await conn.request(
                    {"type": "request_board_state", "payload": {}},
                    response_type="board_state_response",
                    timeout=TIMEOUT,
                )
                cells = response["payload"]["board"]
                return Board.from_list(cells)
            except (TimeoutError, asyncio.TimeoutError):
                log.warning("Vision timeout (attempt %d/%d)", attempt, MAX_RETRIES)
                if attempt == MAX_RETRIES:
                    raise VisionTimeoutError(
                        f"Vision failed after {MAX_RETRIES} retries"
                    )
        raise VisionTimeoutError("Vision unreachable")


import asyncio  # noqa: E402 — deferred to avoid circular
