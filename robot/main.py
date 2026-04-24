import asyncio
import json
import os
import subprocess

import websockets

MASTER_URL = os.environ.get("MASTER_URL", "ws://localhost:8765")


def reset_robot() -> None:
    # Placeholder: reset behavior will be implemented later.
    return


def _run_replay(position: int) -> tuple[bool, str | None]:
    dataset_repo_id = f"kupac/pick_place_fixed0{position}"

    cmd = [
        "lerobot-replay",
        "--robot.type=so101_follower",
        "--robot.port=/dev/ttyACM0",
        "--robot.id=F5",
        f"--dataset.repo_id={dataset_repo_id}",
        "--dataset.episode=0",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return True, None

    detail = (result.stderr or result.stdout or "lerobot-replay failed").strip()
    return False, detail


async def run_robot_client() -> None:
    ws_url = f"{MASTER_URL}/robot"
    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    msg_type = data.get("type")
                    if msg_type == "reset_robot":
                        reset_robot()
                        continue

                    if msg_type != "place_piece":
                        continue

                    payload = data.get("payload")
                    if not isinstance(payload, dict) or "position" not in payload:
                        continue

                    position = payload["position"]
                    success, error_detail = _run_replay(position)

                    response = {
                        "type": "placement_result",
                        "payload": {
                            "success": success,
                            "position": position,
                            "error_detail": error_detail,
                        },
                    }
                    await ws.send(json.dumps(response))
        except Exception:
            await asyncio.sleep(1.0)


def main() -> None:
    asyncio.run(run_robot_client())


if __name__ == "__main__":
    main()