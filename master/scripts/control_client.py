from __future__ import annotations

import asyncio
import json
import os

from websockets.legacy.client import connect

HOST = os.getenv("MASTER_HOST", "127.0.0.1")
PORT = int(os.getenv("MASTER_PORT", "8765"))
CONTROL_URL = f"ws://{HOST}:{PORT}/control"


async def _read_enter() -> None:
    await asyncio.to_thread(input, "")


async def main() -> None:
    print(f"[CONTROL] Connecting to {CONTROL_URL}")
    async with connect(CONTROL_URL) as ws:
        print("[CONTROL] Ready. Press Enter to send start/reset alternately.")
        print("[CONTROL] First Enter sends: start_game(first_turn=human)")

        send_start = True
        while True:
            await _read_enter()

            if send_start:
                payload = {
                    "type": "start_game",
                    "payload": {"first_turn": "human"},
                }
                label = "start_game(first_turn=human)"
            else:
                payload = {
                    "type": "force_reset",
                    "payload": {},
                }
                label = "force_reset()"

            await ws.send(json.dumps(payload))
            print(f"[CONTROL] Sent: {label}")
            send_start = not send_start


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[CONTROL] Stopped.")
