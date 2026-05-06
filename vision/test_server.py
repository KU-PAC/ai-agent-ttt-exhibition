from __future__ import annotations

import argparse
import asyncio
import json
from time import perf_counter

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

REQUEST_MESSAGE = {"type": "request_board_state", "payload": {}}
EXPECTED_RESPONSE_TYPE = "board_state_response"


class VisionTestServer:
    def __init__(self) -> None:
        self._vision_ws: ServerConnection | None = None
        self._request_lock = asyncio.Lock()

    async def handle_connection(self, websocket: ServerConnection) -> None:
        path = websocket.request.path if websocket.request else "/"
        if path != "/vision":
            print(f"[WARN] Unknown path: {path}")
            await websocket.close()
            return

        if self._vision_ws is not None:
            print("[INFO] Closing previous vision connection")
            await self._vision_ws.close()

        self._vision_ws = websocket
        print("[INFO] Vision client connected on /vision")
        try:
            await websocket.wait_closed()
        finally:
            if self._vision_ws is websocket:
                self._vision_ws = None
            print("[INFO] Vision client disconnected")

    async def request_board_state(self, timeout: float) -> None:
        if self._vision_ws is None:
            print("[WARN] Vision client is not connected yet")
            return

        async with self._request_lock:
            try:
                started = perf_counter()
                await self._vision_ws.send(
                    json.dumps(REQUEST_MESSAGE, ensure_ascii=False)
                )
                raw_response = await asyncio.wait_for(
                    self._vision_ws.recv(),
                    timeout=timeout,
                )
                elapsed_ms = (perf_counter() - started) * 1000.0
            except TimeoutError:
                print(f"[WARN] Response timeout after {timeout:.1f}s")
                return
            except ConnectionClosed as exc:
                print(f"[WARN] Vision connection closed: {exc}")
                return

        print(f"[INFO] elapsed: {elapsed_ms:.1f} ms")
        self._print_response(raw_response)

    @staticmethod
    def _print_response(raw_response: str) -> None:
        try:
            response = json.loads(raw_response)
        except json.JSONDecodeError:
            print(f"[WARN] response(raw): {raw_response}")
            return

        if not isinstance(response, dict):
            print(f"[WARN] response(non-object): {response!r}")
            return

        response_type = response.get("type")
        if response_type != EXPECTED_RESPONSE_TYPE:
            print(f"[WARN] response(type={response_type}): {response}")
            return

        payload = response.get("payload", {})
        if not isinstance(payload, dict):
            print(f"[WARN] response(payload invalid): {response}")
            return

        board = payload.get("board")
        print(f"[RECV] board: {board}")


async def command_loop(server: VisionTestServer, timeout: float) -> None:
    print("Press Enter to request board state, or type q + Enter to quit")
    while True:
        cmd = (await asyncio.to_thread(input, "cmd> ")).strip().lower()
        if cmd in {"q", "quit", "exit"}:
            break
        await server.request_board_state(timeout=timeout)


async def main_async(host: str, port: int, timeout: float) -> None:
    server = VisionTestServer()
    async with serve(server.handle_connection, host, port):
        print(f"[INFO] Test server listening at ws://{host}:{port}/vision")
        await command_loop(server, timeout=timeout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vision test WebSocket server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    asyncio.run(main_async(args.host, args.port, args.timeout))


if __name__ == "__main__":
    main()