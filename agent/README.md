# sushitech_agent

## setup
```bash
uv sync
```

## test
1. バックエンドの起動
```bash
uv run uvicorn src.backend.game_api:app --reload --port 8765
```

2. Unity の起動
Unity Editor で UnityAgent プロジェクトを開き、Play モードに入ります。
コンソールに `Connected to Master server` と表示されれば接続成功です。

3. WebSocket 経由でテスト

Control WebSocket (`ws://localhost:8765/control`) に接続してコマンドを送信します:

```bash
uv run python -c "
import asyncio, json, websockets
async def test():
    async with websockets.connect('ws://localhost:8765/control') as ws:
        # ゲーム開始
        await ws.send(json.dumps({'type': 'start_game', 'payload': {'first_turn': 'human'}}))
        print('Game started')

        # 内部状態取得
        await ws.send(json.dumps({'type': 'get_internal_state', 'payload': {}}))
        resp = await ws.recv()
        data = json.loads(resp)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        assert data['type'] == 'internal_state_response'
        print('OK!')
asyncio.run(test())
"
```

4. 状態確認
```bash
curl http://localhost:8765/game/status
```

## 通信プロトコル (Master仕様準拠)

すべての WebSocket メッセージは `{type, payload}` 形式で統一されています。

### 盤面配列

```
[0][1][2]
[3][4][5]
[6][7][8]
```

- `0` = 空き
- `1` = 人間のコマ(〇)
- `2` = AIのコマ(✕)

### WebSocket エンドポイント

| パス | クライアント | 説明 |
|------|-------------|------|
| `/unity` | Unity | 演出クライアント |
| `/control` | 制御端末 | ゲーム開始/リセット/状態取得 |

---

### Master → Unity

#### 状態変更 (`set_state`)

```json
{
  "type": "set_state",
  "payload": {
    "state": "thinking"
  }
}
```

| state | 説明 |
|-------|------|
| `thinking` | AIが思考中 |
| `idle` | 待機状態 |
| `human_turn` | 人間のターン |
| `error` | エラー発生 |

---

#### 演出指示 (`play_reaction`)

```json
{
  "type": "play_reaction",
  "payload": {
    "emotion": "happy",
    "dialogue": "そこですか！"
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `emotion` | `string` | 感情の種類（下表参照） |
| `dialogue` | `string` | キャラクターのセリフ（日本語） |

**感情の選択肢**:
`normal`, `happy`, `angry`, `sad`, `surprised`, `shy`, `excited`, `smug`, `calm`

---

### Control → Master

#### ゲーム開始 (`start_game`)

```json
{"type": "start_game", "payload": {"first_turn": "human"}}
```

#### 人間の手 (`human_move`)

```json
{"type": "human_move", "payload": {"position": 4}}
```

#### 強制リセット (`force_reset`)

```json
{"type": "force_reset", "payload": {}}
```

#### 内部状態取得 (`get_internal_state`)

```json
{"type": "get_internal_state", "payload": {}}
```

レスポンス:
```json
{
  "type": "internal_state_response",
  "payload": {
    "board": [1, 0, 2, 0, 1, 0, 0, 0, 0],
    "current_phase": "human_turn"
  }
}
```
