from __future__ import annotations

import asyncio
import logging

from master.adapters.errors import VisionTimeoutError
from master.adapters.ws_server import ClientType, WebSocketServer
from master.application.ports import VisionPort
from master.domain.board import Board

log = logging.getLogger(__name__)


class VisionWebSocketAdapter(VisionPort):
    def __init__(
        self, ws_server: WebSocketServer,
        timeout: float = 1.0, max_retries: int = 3,
    ) -> None:
        self._ws_server = ws_server
        self._timeout = timeout
        self._max_retries = max_retries

    async def request_board_state(self) -> Board:
        for attempt in range(1, self._max_retries + 1):
            conn = self._ws_server.get_client(ClientType.VISION)
            if conn is None:
                raise VisionTimeoutError("Vision client not connected")
            try:
                response = await conn.request(
                    {"type": "request_board_state", "payload": {}},
                    response_type="board_state_response",
                    timeout=self._timeout,
                )
                cells = response["payload"]["board"]
                return Board.from_list(cells)
            except (TimeoutError, asyncio.TimeoutError):
                log.warning("Vision timeout (attempt %d/%d)", attempt, self._max_retries)
            except (KeyError, TypeError) as e:
                log.warning("Vision malformed response (attempt %d/%d): %s", attempt, self._max_retries, e)

        raise VisionTimeoutError(f"Vision failed after {self._max_retries} retries")
