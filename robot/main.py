from fastapi import FastAPI, WebSocket
import subprocess

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        data = await ws.receive_json()

        payload = data.get("payload")

        position = payload["position"]

        cmd = [
            "lerobot-replay",
            "--robot.type=so101_follower",
            "--robot.port=/dev/ttyACM0",
            "--robot.id=F5",
            "--dataset.repo_id=oyokoi451/pick_place_fixed3",
            f"--dataset.episode={position}"
        ]

        subprocess.run(cmd)

        response = {
            "type": "placement_result",
            "payload": {
                "success": True,
                "position": position,
                "error_detail": ""
            }
        }

        await ws.send_json(response)