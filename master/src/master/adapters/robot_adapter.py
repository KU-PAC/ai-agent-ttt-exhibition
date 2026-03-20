from __future__ import annotations

import asyncio
import logging

from master.adapters.errors import RobotTimeoutError
from master.adapters.ws_server import ClientType, WebSocketServer
from master.application.ports import RobotPort
from master.domain.models import PlacementResult

log = logging.getLogger(__name__)


class RobotWebSocketAdapter(RobotPort):
    def __init__(
        self,
        ws_server: WebSocketServer,
        placement_timeout: float = 30.0,
    ) -> None:
        self._ws_server = ws_server
        self._placement_timeout = placement_timeout

    async def place_piece(
        self,
        position: int,
        piece_type: int,
    ) -> PlacementResult:
        conn = self._ws_server.get_client(ClientType.ROBOT)
        if conn is None:
            raise RobotTimeoutError("Robot client not connected")
        try:
            response = await conn.request(
                {
                    "type": "place_piece",
                    "payload": {"position": position, "piece_type": piece_type},
                },
                response_type="placement_result",
                timeout=self._placement_timeout,
            )
            payload = response["payload"]
            return PlacementResult(
                success=payload["success"],
                position=payload["position"],
                error_detail=payload.get("error_detail"),
            )
        except (KeyError, TypeError) as e:
            raise RobotTimeoutError(f"Robot malformed response: {e}") from e
        except (TimeoutError, asyncio.TimeoutError) as e:
            raise RobotTimeoutError(
                f"Robot timeout after {self._placement_timeout}s"
            ) from e

    async def reset_robot(self) -> None:
        conn = self._ws_server.get_client(ClientType.ROBOT)
        if conn is None:
            log.warning("Robot not connected for reset")
            return
        await conn.send({"type": "reset_robot", "payload": {}})
