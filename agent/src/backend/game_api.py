"""
WebSocketサーバー - Masterプロトコル準拠
Master仕様に基づきUnity/Robot/Vision/Controlクライアントを管理
"""

import asyncio
import json
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
from .game_master import GameMaster
from .game_structures import (
    GameState, HUMAN, AI,
    make_set_state_message,
    make_play_reaction_message,
    make_internal_state_response,
)

game_master: GameMaster = None
unity_ws: Optional[WebSocket] = None
game_loop_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global game_master
    game_master = GameMaster()
    yield


app = FastAPI(title="TTT Agent - Master Protocol", lifespan=lifespan)


async def send_to_unity(message: dict):
    if unity_ws is None:
        return
    try:
        await unity_ws.send_json(message)
    except Exception:
        pass


async def set_unity_state(state: str):
    await send_to_unity(make_set_state_message(state))


async def play_reaction(emotion: str, dialogue: str):
    await send_to_unity(make_play_reaction_message(emotion, dialogue))


async def run_ai_turn():
    state = game_master.game_state
    board = state.board

    await set_unity_state("thinking")

    ai_response = await game_master.get_ai_move()

    await play_reaction(ai_response.emotion, ai_response.dialogue)

    board.place_mark(ai_response.move, AI)
    state.turn_count += 1

    winner = board.check_winner()
    if winner:
        state.is_game_over = True
        state.winner = winner
        state.phase = "game_over"
        return winner

    state.current_player = HUMAN
    state.phase = "human_turn"
    await set_unity_state("human_turn")
    return None


async def run_human_turn(position: int) -> Optional[str]:
    state = game_master.game_state
    board = state.board

    if not board.is_valid_move(position):
        return None

    board.place_mark(position, HUMAN)
    state.turn_count += 1

    winner = board.check_winner()
    if winner:
        state.is_game_over = True
        state.winner = winner
        state.phase = "game_over"
        return winner

    state.current_player = AI
    state.phase = "ai_thinking"
    return None


async def execute_reset():
    global game_loop_task
    if game_loop_task and not game_loop_task.done():
        game_loop_task.cancel()
        game_loop_task = None
    game_master.reset_game()
    await set_unity_state("idle")


@app.websocket("/unity")
async def websocket_unity(websocket: WebSocket):
    global unity_ws
    await websocket.accept()
    unity_ws = websocket
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        unity_ws = None


@app.websocket("/control")
async def websocket_control(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type", "")
            payload = message.get("payload", {})

            if msg_type == "start_game":
                first_turn = payload.get("first_turn", "human")
                game_master.reset_game()
                state = game_master.game_state
                state.phase = "human_turn" if first_turn == "human" else "ai_thinking"
                state.current_player = HUMAN if first_turn == "human" else AI
                state.is_game_over = False
                if first_turn == "human":
                    await set_unity_state("human_turn")
                else:
                    result = await run_ai_turn()
                    if result:
                        await handle_game_over(result)

            elif msg_type == "human_move":
                position = payload.get("position", -1)
                result = await run_human_turn(position)
                if result:
                    await handle_game_over(result)
                else:
                    result = await run_ai_turn()
                    if result:
                        await handle_game_over(result)

            elif msg_type == "force_reset":
                await execute_reset()

            elif msg_type == "get_internal_state":
                resp = make_internal_state_response(
                    game_master.game_state.board.cells,
                    game_master.game_state.phase,
                )
                await websocket.send_json(resp)

    except WebSocketDisconnect:
        await execute_reset()


async def handle_game_over(result: str):
    if result == "win_ai":
        await play_reaction("happy", "やったー！勝ちました！")
    elif result == "win_human":
        await play_reaction("sad", "負けちゃいました…次は頑張ります！")
    else:
        await play_reaction("calm", "引き分けですね！いい勝負でした！")

    await asyncio.sleep(5.0)
    await execute_reset()


@app.get("/game/status")
async def get_game_status():
    state = game_master.game_state
    return {
        "board": state.board.cells,
        "current_phase": state.phase,
        "current_player": state.current_player,
        "turn_count": state.turn_count,
        "is_game_over": state.is_game_over,
        "winner": state.winner,
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "unity_connected": unity_ws is not None,
    }
