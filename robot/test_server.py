import argparse
import asyncio
import json
from typing import Any

import websockets
from websockets.asyncio.server import ServerConnection, serve


class RobotTestServer:
    def __init__(self) -> None:
        self._robot_ws: ServerConnection | None = None

    async def handle_connection(self, websocket: ServerConnection) -> None:
        path = websocket.request.path if websocket.request else "/"
        if path != "/robot":
            print(f"[WARN] Unknown path: {path}")
            await websocket.close()
            return

        self._robot_ws = websocket
        print("[INFO] Robot client connected on /robot")

        try:
            async for raw in websocket:
                data = self._safe_json_load(raw)
                if data is None:
                    print(f"[WARN] Invalid JSON response: {raw}")
                    continue
                print(f"[RECV] {json.dumps(data, ensure_ascii=False)}")
        except Exception as exc:
            print(f"[WARN] Robot connection error: {exc}")
        finally:
            if self._robot_ws is websocket:
                self._robot_ws = None
            print("[INFO] Robot client disconnected")

    @staticmethod
    def _safe_json_load(raw: Any) -> dict[str, Any] | None:
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None

    async def send_place_piece(self, position: int, piece_type: int = 2) -> None:
        if self._robot_ws is None:
            print("[WARN] Robot client is not connected yet")
            return

        message = {
            "type": "place_piece",
            "payload": {
                "position": position,
                "piece_type": piece_type,
            },
        }
        await self._robot_ws.send(json.dumps(message))
        print(f"[SEND] place_piece position={position} piece_type={piece_type}")

    async def send_reset(self) -> None:
        if self._robot_ws is None:
            print("[WARN] Robot client is not connected yet")
            return

        message = {
            "type": "reset_robot",
            "payload": {},
        }
        await self._robot_ws.send(json.dumps(message))
        print("[SEND] reset_robot")


async def command_loop(server: RobotTestServer) -> None:
    print("Commands: 00-08 => place_piece(position 0-8), 10 => reset_robot, q => quit")
    while True:
        cmd = (await asyncio.to_thread(input, "cmd> ")).strip()

        if cmd in {"q", "quit", "exit"}:
            break

        if cmd == "10":
            await server.send_reset()
            continue

        if len(cmd) == 2 and cmd.startswith("0") and cmd[1].isdigit():
            pos = int(cmd[1])
            if 0 <= pos <= 8:
                await server.send_place_piece(position=pos)
                continue

        print("[WARN] Invalid command. Use 00-08, 10, or q")


async def main_async(host: str, port: int) -> None:
    server = RobotTestServer()
    async with serve(server.handle_connection, host, port):
        print(f"[INFO] Test server listening at ws://{host}:{port}/robot")
        await command_loop(server)


def main() -> None:
    parser = argparse.ArgumentParser(description="Robot test WebSocket server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    asyncio.run(main_async(args.host, args.port))


if __name__ == "__main__":
    main()
