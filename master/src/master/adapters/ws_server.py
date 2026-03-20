from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import Any, Awaitable, Callable

import websockets
from websockets.asyncio.server import Server, ServerConnection

__all__ = ["ClientType", "WebSocketServer", "WebSocketConnection"]

log = logging.getLogger(__name__)


class ClientType(Enum):
    VISION = "vision"
    ROBOT = "robot"
    UNITY = "unity"
    CONTROL = "control"


PATH_TO_CLIENT: dict[str, ClientType] = {
    "/vision": ClientType.VISION,
    "/robot": ClientType.ROBOT,
    "/unity": ClientType.UNITY,
    "/control": ClientType.CONTROL,
}


class WebSocketConnection:
    def __init__(self, ws: ServerConnection) -> None:
        self._ws = ws
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._recv_task: asyncio.Task[None] | None = None

    def start_receiving(self) -> None:
        self._recv_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self) -> None:
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")
                if msg_type in self._pending:
                    self._pending[msg_type].set_result(msg)
        except websockets.ConnectionClosed:
            pass
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("WebSocket closed"))
            self._pending.clear()

    async def send(self, message: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(message))

    async def request(
        self, message: dict[str, Any], response_type: str, timeout: float,
    ) -> dict[str, Any]:
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[response_type] = fut
        try:
            await self._ws.send(json.dumps(message))
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(response_type, None)

    async def close(self) -> None:
        if self._recv_task and not self._recv_task.done():
            self._recv_task.cancel()
        await self._ws.close()


class WebSocketServer:
    def __init__(self) -> None:
        self._clients: dict[ClientType, WebSocketConnection] = {}
        self._server: Server | None = None
        self._on_disconnect: Callable[[str], Awaitable[None]] | None = None
        self._control_handler: Any | None = None
        self._game_manager: Any | None = None

    def set_disconnect_handler(
        self, handler: Callable[[str], Awaitable[None]],
    ) -> None:
        self._on_disconnect = handler

    def set_control_handler(self, handler: Any) -> None:
        self._control_handler = handler

    def set_game_manager(self, game_manager: Any) -> None:
        self._game_manager = game_manager

    def get_client(self, client_type: ClientType) -> WebSocketConnection | None:
        return self._clients.get(client_type)

    async def start(self, host: str, port: int) -> None:
        self._server = await websockets.serve(
            self._handle_connection, host, port,
        )
        log.info("WebSocket server started on ws://%s:%d", host, port)
        await self._server.wait_closed()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            log.info("WebSocket server stopped")

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        path = websocket.request.path if websocket.request else "/"
        client_type = PATH_TO_CLIENT.get(path)
        if client_type is None:
            log.warning("Unknown path: %s", path)
            await websocket.close()
            return

        conn = WebSocketConnection(websocket)
        self._clients[client_type] = conn
        log.info("Client connected: %s", client_type.value)

        if client_type == ClientType.CONTROL:
            await self._handle_control_loop(websocket)
        else:
            conn.start_receiving()
            try:
                await websocket.wait_closed()
            finally:
                self._clients.pop(client_type, None)
                log.info("Client disconnected: %s", client_type.value)
                if self._on_disconnect:
                    await self._on_disconnect(client_type.value)

    async def _handle_control_loop(self, websocket: ServerConnection) -> None:
        try:
            async for raw in websocket:
                msg = json.loads(raw)
                if self._control_handler and self._game_manager:
                    response = await self._control_handler.handle_message(
                        msg, self._game_manager,
                    )
                    if response is not None:
                        await websocket.send(json.dumps(response))
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.pop(ClientType.CONTROL, None)
            log.info("Control client disconnected")
