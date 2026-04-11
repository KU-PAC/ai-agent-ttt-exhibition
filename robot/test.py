import asyncio
import websockets
import json

async def test():
    uri = "ws://127.0.0.1:8000/ws"
    async with websockets.connect(uri) as ws:

        await ws.send(json.dumps({
            "type": "place_piece",
            "payload": {
                "position": 8,
                "piece_type": 2
            }
        }))

        res = await ws.recv()

        data = json.loads(res)

        print(data)

asyncio.run(test())