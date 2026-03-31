"""
ハードウェアシミュレーター (Vision + Robot モック)

Master に Vision / Robot クライアントとして接続し、
REST API で人間の手入力を受け付ける。

本番時はこのプロセスの代わりに実機カメラ・アームが Master に接続する。

起動: uv run uvicorn simulator.hw_simulator:app --port 8001
前提: Master が ws://localhost:8765 で起動済みであること
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from websockets.asyncio.client import connect, ClientConnection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)

EMPTY, HUMAN, AI = 0, 1, 2
CELL_SYMBOLS = {EMPTY: "＿", HUMAN: "〇", AI: "✕"}
MASTER_URL = os.environ.get("MASTER_URL", "ws://localhost:8765")


class HardwareSimulator:
    def __init__(self, master_url: str) -> None:
        self._master_url = master_url
        self._board: list[int] = [EMPTY] * 9
        self._vision_ws: ClientConnection | None = None
        self._robot_ws: ClientConnection | None = None
        self._tasks: list[asyncio.Task] = []

    @property
    def board(self) -> list[int]:
        return list(self._board)

    async def connect(self) -> None:
        self._vision_ws = await connect(f"{self._master_url}/vision")
        self._robot_ws = await connect(f"{self._master_url}/robot")
        log.info("Connected to Master as Vision + Robot")
        self._tasks.append(asyncio.create_task(self._vision_loop()))
        self._tasks.append(asyncio.create_task(self._robot_loop()))

    async def disconnect(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        for ws in (self._vision_ws, self._robot_ws):
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass

    def set_human_move(self, position: int) -> bool:
        if not (0 <= position <= 8):
            return False
        if self._board[position] != EMPTY:
            return False
        self._board[position] = HUMAN
        log.info("Human piece at %d, board=%s", position, self._board)
        return True

    async def start_game(self, first_turn: str) -> None:
        self._board = [EMPTY] * 9
        async with connect(f"{self._master_url}/control") as ws:
            await ws.send(json.dumps({
                "type": "start_game",
                "payload": {"first_turn": first_turn},
            }))
        log.info("Game started (first_turn=%s)", first_turn)

    async def force_reset(self) -> None:
        async with connect(f"{self._master_url}/control") as ws:
            await ws.send(json.dumps({
                "type": "force_reset",
                "payload": {},
            }))
        self._board = [EMPTY] * 9
        log.info("Force reset")

    async def get_internal_state(self) -> dict:
        try:
            async with connect(f"{self._master_url}/control") as ws:
                await ws.send(json.dumps({
                    "type": "get_internal_state",
                    "payload": {},
                }))
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                msg = json.loads(raw)
                if msg.get("type") == "internal_state_response":
                    return msg["payload"]
        except Exception:
            pass
        return {"board": self.board, "current_phase": "unknown"}

    async def _vision_loop(self) -> None:
        try:
            async for raw in self._vision_ws:
                msg = json.loads(raw)
                if msg.get("type") == "request_board_state":
                    await self._vision_ws.send(json.dumps({
                        "type": "board_state_response",
                        "payload": {"board": list(self._board)},
                    }))
        except asyncio.CancelledError:
            return
        except Exception as e:
            log.error("Vision loop error: %s", e)

    async def _robot_loop(self) -> None:
        try:
            async for raw in self._robot_ws:
                msg = json.loads(raw)
                msg_type = msg.get("type")

                if msg_type == "place_piece":
                    pos = msg["payload"]["position"]
                    piece = msg["payload"].get("piece_type", AI)
                    self._board[pos] = piece
                    log.info("Robot placed piece_type=%d at %d", piece, pos)
                    await self._robot_ws.send(json.dumps({
                        "type": "placement_result",
                        "payload": {
                            "success": True,
                            "position": pos,
                            "error_detail": None,
                        },
                    }))

                elif msg_type == "reset_robot":
                    self._board = [EMPTY] * 9
                    log.info("Robot reset")

        except asyncio.CancelledError:
            return
        except Exception as e:
            log.error("Robot loop error: %s", e)


hw: HardwareSimulator | None = None


def _render(cells: list[int]) -> str:
    rows = []
    for r in range(3):
        parts = [f" {CELL_SYMBOLS.get(cells[r * 3 + c], '?')} " for c in range(3)]
        rows.append("|".join(parts))
    return "\n----+----+----\n".join(rows)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global hw
    hw = HardwareSimulator(master_url=MASTER_URL)
    for attempt in range(10):
        try:
            await hw.connect()
            break
        except Exception as e:
            log.warning("Master connection attempt %d failed: %s", attempt + 1, e)
            await asyncio.sleep(2)
    else:
        log.error("Could not connect to Master at %s", MASTER_URL)
    yield
    if hw:
        await hw.disconnect()


app = FastAPI(title="Hardware Simulator (Vision + Robot)", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.post("/game/start")
async def start_game(first_turn: str = "human"):
    if first_turn not in ("human", "ai"):
        raise HTTPException(400, "first_turn must be 'human' or 'ai'")
    await hw.start_game(first_turn)
    return {"status": "started", "first_turn": first_turn, "board": hw.board}


@app.post("/game/human-move")
async def human_move(position: int):
    if not hw.set_human_move(position):
        raise HTTPException(400, f"invalid move at position {position}")
    return {"success": True, "position": position, "board": hw.board}


@app.post("/game/reset")
async def reset():
    await hw.force_reset()
    return {"status": "reset"}


@app.get("/game/status")
async def get_status():
    state = await hw.get_internal_state()
    return {**state, "board_display": _render(state.get("board", hw.board))}


@app.get("/health")
async def health():
    return {"status": "ok", "master_url": MASTER_URL}
