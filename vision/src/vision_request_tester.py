from __future__ import annotations

import asyncio
import json
import os
import sys
from time import perf_counter

from websockets.asyncio.client import connect

REQUEST_MESSAGE = {"type": "request_board_state", "payload": {}}
EXPECTED_RESPONSE_TYPE = "board_state_response"


def _build_uri() -> str:
    host = os.getenv("MASTER_HOST", "0.0.0.0")
    port = os.getenv("MASTER_PORT", "8765")
    return f"ws://{host}:{port}/vision"


async def _read_enter() -> str:
    return await asyncio.to_thread(
        input,
        "Press Enter to send request (type 'q' + Enter to quit): ",
    )


async def run_tester() -> None:
    uri = _build_uri()
    print(f"Connect to: {uri}")

    async with connect(uri) as websocket:
        print("Connected. Waiting for Enter key...")
        while True:
            user_input = (await _read_enter()).strip().lower()
            if user_input in {"q", "quit", "exit"}:
                print("Exit tester.")
                return

            started = perf_counter()
            await websocket.send(json.dumps(REQUEST_MESSAGE, ensure_ascii=False))
            raw_response = await websocket.recv()
            elapsed_ms = (perf_counter() - started) * 1000.0

            print(f"elapsed: {elapsed_ms:.1f} ms")
            try:
                response = json.loads(raw_response)
            except json.JSONDecodeError:
                print(f"response(raw): {raw_response}")
                continue

            response_type = response.get("type")
            if response_type != EXPECTED_RESPONSE_TYPE:
                print(f"response(type={response_type}): {response}")
                continue

            payload = response.get("payload", {})
            board = payload.get("board")
            print(f"board: {board}")


def main() -> None:
    try:
        asyncio.run(run_tester())
    except KeyboardInterrupt:
        print("Interrupted by user.")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
