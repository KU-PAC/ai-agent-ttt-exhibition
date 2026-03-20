from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from websockets.asyncio.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from simulator.board_ui import prompt_human_move, render_board, render_index_guide

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

MASTER_HOST = "localhost"
MASTER_PORT = 8765


async def start_master() -> asyncio.Task[None]:
    from master.main import main
    task = asyncio.create_task(main())
    await asyncio.sleep(1.5)
    return task


async def run_game() -> None:
    base = f"ws://{MASTER_HOST}:{MASTER_PORT}"
    board = [0] * 9

    v_ws = await connect(f"{base}/vision")
    r_ws = await connect(f"{base}/robot")
    u_ws = await connect(f"{base}/unity")

    states: asyncio.Queue[str] = asyncio.Queue()
    reactions: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
    place_events: asyncio.Queue[int] = asyncio.Queue()

    async def vision_loop() -> None:
        try:
            async for raw in v_ws:
                msg = json.loads(raw)
                if msg.get("type") == "request_board_state":
                    await v_ws.send(json.dumps({
                        "type": "board_state_response",
                        "payload": {"board": list(board)},
                    }))
        except Exception:
            pass

    async def robot_loop() -> None:
        try:
            async for raw in r_ws:
                msg = json.loads(raw)
                if msg.get("type") == "place_piece":
                    pos = msg["payload"]["position"]
                    board[pos] = msg["payload"].get("piece_type", 2)
                    await r_ws.send(json.dumps({
                        "type": "placement_result",
                        "payload": {"success": True, "position": pos, "error_detail": None},
                    }))
                    await place_events.put(pos)
        except Exception:
            pass

    async def unity_loop() -> None:
        try:
            async for raw in u_ws:
                msg = json.loads(raw)
                if msg["type"] == "set_state":
                    await states.put(msg["payload"]["state"])
                elif msg["type"] == "play_reaction":
                    await reactions.put((msg["payload"]["emotion"], msg["payload"]["dialogue"]))
        except Exception:
            pass

    asyncio.create_task(vision_loop())
    asyncio.create_task(robot_loop())
    asyncio.create_task(unity_loop())
    await asyncio.sleep(0.5)

    print("\n===========================")
    print("    〇✕ゲーム シミュレータ")
    print("===========================")
    print("\nマス番号:")
    print(render_index_guide())

    first = input("\n先手を選択 [h]uman / [a]i (default: human): ").strip().lower()
    first_turn = "ai" if first in ("a", "ai") else "human"

    async with connect(f"{base}/control") as c_ws:
        await c_ws.send(json.dumps({
            "type": "start_game",
            "payload": {"first_turn": first_turn},
        }))
        await asyncio.sleep(0.1)

    print(f"\nゲーム開始 (先手: {'人間' if first_turn == 'human' else 'AI'})")

    while True:
        try:
            state = await asyncio.wait_for(states.get(), timeout=30.0)
        except asyncio.TimeoutError:
            print("\n[TIMEOUT] Masterからの応答がありません。")
            break

        if state == "idle":
            try:
                emotion, dialogue = await asyncio.wait_for(reactions.get(), timeout=1.0)
                print(f"\nAI [{emotion}]: 「{dialogue}」")
            except asyncio.TimeoutError:
                pass
            break

        if state == "error":
            print("\n[ERROR] エラーが発生しました。")
            break

        if state == "human_turn":
            print(f"\n{render_board(board)}")
            pos = await asyncio.get_event_loop().run_in_executor(
                None, prompt_human_move, board,
            )
            board[pos] = 1
            print(f"\n{render_board(board)}")
            continue

        if state == "thinking":
            print("\nAI思考中...")
            try:
                emotion, dialogue = await asyncio.wait_for(reactions.get(), timeout=20.0)
                print(f"AI [{emotion}]: 「{dialogue}」")
            except asyncio.TimeoutError:
                print("  (セリフ取得タイムアウト)")

            try:
                ai_pos = await asyncio.wait_for(place_events.get(), timeout=20.0)
                print(f"\n{render_board(board)}")
            except asyncio.TimeoutError:
                print("  (配置タイムアウト)")
                break
            continue

    winner = None
    for a, b, c in [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]:
        if board[a] != 0 and board[a] == board[b] == board[c]:
            winner = board[a]
            break

    print(f"\n--- ゲーム終了 ---")
    if winner == 1:
        print("結果: 人間の勝ち!")
    elif winner == 2:
        print("結果: AIの勝ち!")
    elif 0 not in board:
        print("結果: 引き分け!")

    print(f"\n最終盤面:")
    print(render_board(board))

    await v_ws.close()
    await r_ws.close()
    await u_ws.close()


async def main() -> None:
    print("Master起動中...")
    master_task = await start_master()
    print(f"Master起動完了 ws://{MASTER_HOST}:{MASTER_PORT}")

    try:
        await run_game()
    except KeyboardInterrupt:
        print("\n中断されました。")
    except Exception as e:
        print(f"\nエラー: {e}")
    finally:
        master_task.cancel()
        try:
            await master_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
