"""
FastAPI エンドポイント - 三目並べゲーム用
Master / Robot / Unity 間の通信
"""

import json
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from contextlib import asynccontextmanager
from .game_master import GameMaster
from .game_structures import make_unity_message

# グローバル状態
game_master: GameMaster = None
unity_websockets: Set[WebSocket] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーション初期化・シャットダウン"""
    global game_master
    # 起動時
    game_master = GameMaster()
    print("✅ GameMaster を初期化しました")
    yield
    # シャットダウン時
    print("⏹️ アプリケーション終了")


app = FastAPI(title="三目並べゲーム API", lifespan=lifespan)


# ===== Unity WebSocket =====

@app.websocket("/ws/unity")
async def websocket_unity(websocket: WebSocket):
    """Unity クライアント接続"""
    await websocket.accept()
    unity_websockets.add(websocket)
    try:
        print(f"✅ Unity 接続 (接続数: {len(unity_websockets)})")
        # Unity からのメッセージを受け付ける（将来の拡張用）
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type", "")
            payload = message.get("payload", {})
            print(f"📨 Unity from: type={msg_type}, payload={payload}")
    except WebSocketDisconnect:
        print(f"❌ Unity 切断")
        unity_websockets.discard(websocket)


async def broadcast_to_unity(message: dict):
    """Unity クライアントにブロードキャスト ({type, payload} 形式)"""
    for ws in unity_websockets:
        try:
            await ws.send_json(message)
        except Exception as e:
            print(f"❌ Unity 送信エラー: {e}")


# ===== REST エンドポイント =====

@app.get("/game/status")
async def get_game_status():
    """ゲーム状態を取得"""
    return game_master.get_game_status()


@app.post("/game/start")
async def start_game():
    """ゲームを開始"""
    result = game_master.reset_game()
    msg = make_unity_message("game_start", {
        "board": game_master.game_state.board.cells,
        "board_state": result["board"],
    })
    await broadcast_to_unity(msg)
    return result


@app.post("/game/play-turn")
async def play_turn():
    """
    1ターン実行
    LLM から手を取得 → 盤面を更新 → Unity に通知
    """
    if game_master.game_state.is_game_over:
        raise HTTPException(status_code=400, detail="ゲームは既に終了しています")

    # LLM からの手を取得
    ai_response = await game_master.get_ai_move()
    if not ai_response:
        raise HTTPException(status_code=500, detail="LLM 呼び出し失敗")

    # 手が有効かチェック
    if not game_master.game_state.board.is_valid_move(ai_response.move):
        raise HTTPException(status_code=400, detail=f"無効な手: {ai_response.move}")

    # 盤面に駒を配置
    game_master.game_state.board.place_mark(ai_response.move, "O")

    # Unity に感情・セリフ・盤面を送信
    msg = make_unity_message("speech", {
        "emotion": ai_response.emotion,
        "speech": ai_response.speech,
        "board": game_master.game_state.board.cells,
        "board_state": game_master.game_state.board.to_text(),
    })
    await broadcast_to_unity(msg)

    # 勝者をチェック
    winner = game_master.game_state.board.check_winner()
    if winner:
        game_master.game_state.is_game_over = True
        game_master.game_state.winner = winner

        if winner == "draw":
            emotion, speech = "calm", "引き分けです！"
        elif winner == "O":
            emotion, speech = "happy", "勝ちました！"
        else:
            emotion, speech = "sad", "負けました..."

        result_msg = make_unity_message("game_over", {
            "winner": winner,
            "emotion": emotion,
            "speech": speech,
            "board": game_master.game_state.board.cells,
            "board_state": game_master.game_state.board.to_text(),
        })
        await broadcast_to_unity(result_msg)

    # ターンを交代
    game_master.game_state.current_player = "X" if game_master.game_state.current_player == "O" else "O"
    game_master.game_state.turn_count += 1

    return {
        "success": True,
        "move": ai_response.move,
        "emotion": ai_response.emotion,
        "speech": ai_response.speech,
        "board": game_master.game_state.board.to_text(),
        "game_over": game_master.game_state.is_game_over,
        "winner": game_master.game_state.winner
    }


@app.post("/game/simulate-failure")
async def simulate_failure(position: int = 4):
    """テスト用: 配置失敗をシミュレート"""
    msg = make_unity_message("placement_failure", {
        "error_message": "コマの配置に失敗しました",
        "position": position,
    })
    await broadcast_to_unity(msg)
    return {"success": True, "message": "placement_failure sent to Unity"}


@app.get("/health")
async def health():
    """ヘルスチェック"""
    return {
        "status": "ok",
        "unity_connections": len(unity_websockets)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
