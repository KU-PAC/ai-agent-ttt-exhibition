from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from master.application.ports.robot_port import RobotPort
from master.domain.errors import RobotTimeoutError
from master.domain.models import PlacementResult

if TYPE_CHECKING:
    from master.adapters.ws_server import WebSocketServer

__all__ = ["RobotWebSocketAdapter"]

log = logging.getLogger(__name__)

PLACEMENT_TIMEOUT = 30.0


class RobotWebSocketAdapter(RobotPort):
    def __init__(self, ws_server: WebSocketServer) -> None:
        self._ws_server = ws_server

    async def place_piece(
        self, position: int, piece_type: int,
    ) -> PlacementResult:
        from master.adapters.ws_server import ClientType

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
                timeout=PLACEMENT_TIMEOUT,
            )
            payload = response["payload"]
            return PlacementResult(
                success=payload["success"],
                position=payload["position"],
                error_detail=payload.get("error_detail"),
            )
        except (TimeoutError, asyncio.TimeoutError) as e:
            raise RobotTimeoutError(
                f"Robot timeout after {PLACEMENT_TIMEOUT}s"
            ) from e

    async def reset_robot(self) -> None:
        from master.adapters.ws_server import ClientType

        conn = self._ws_server.get_client(ClientType.ROBOT)
        if conn is None:
            log.warning("Robot not connected for reset")
            return
        await conn.send({"type": "reset_robot", "payload": {}})
