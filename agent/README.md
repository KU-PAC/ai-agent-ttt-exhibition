# sushitech_agent

## setup
```bash
uv sync
```


## test
1. バックエンドの起動
```bash
uv run uvicorn src.backend.game_api:app --reload --port 8000
```

2. Unity の起動
Unity Editor で UnityAgent プロジェクトを開き、Play モードに入ります。
コンソールに Connected to server と表示されれば接続成功です。

3. API を叩いてテスト
バックエンドが起動中 & Unity が接続中の状態で、別のターミナルから以下を実行します：

- ゲーム開始
```bash
curl -X POST http://localhost:8000/game/start
```
→ Unity のキャラクターが「ゲーム開始ですね！頑張りましょう！」と反応、盤面UIが初期化されるはず

- 1ターン実行（LLM が手を打つ）
```bash
curl -X POST http://localhost:8000/game/play-turn
```
→ キャラクターが感情付きのセリフを読み上げ、盤面UIに O が配置される

- 配置失敗シミュレート
```bash
curl -X POST "http://localhost:8000/game/simulate-failure?position=3"
```
→ キャラクターが驚き表情で「あれ、うまく置けなかったみたい…」と反応

- 状態確認
```bash
curl http://localhost:8000/game/status
```
4. Unity なしでのバックエンド単体テスト
Unity を起動せずに WebSocket のメッセージフォーマットだけ検証したい場合は：

```bash
uv run python -c "
import asyncio, json, aiohttp
async def test():
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect('ws://localhost:8000/ws/unity') as ws:
            await s.post('http://localhost:8000/game/start')
            msg = await ws.receive(timeout=5)
            data = json.loads(msg.data)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            assert data['type'] == 'game_start'
            assert 'board' in data['payload']
            print('OK!')
asyncio.run(test())
"
```
これで {"type": "game_start", "payload": {...}} 形式のメッセージが確認できます。


## API形式

すべての WebSocket メッセージは `{type, payload}` 形式で統一されています。

### WebSocket 接続

- **エンドポイント**: `ws://localhost:8000/ws/unity`
- **方向**: Unity クライアント ↔ Backend（FastAPI）

---

### Master → Unity

#### ゲーム開始通知（`game_start`）

ゲームが開始された時に送信されます。盤面UIの初期化に使用します。

```json
{
  "type": "game_start",
  "payload": {
    "board": ["", "", "", "", "", "", "", "", ""],
    "board_state": "```\n0 | 1 | 2\n-----------\n3 | 4 | 5\n-----------\n6 | 7 | 8\n```"
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `board` | `string[9]` | 盤面の状態。`""` = 空, `"O"` = AI, `"X"` = 相手 |
| `board_state` | `string` | テキスト形式の盤面表示（デバッグ用） |

---

#### LLM 発話通知（`speech`）

LLM が手を打った後、感情付きのセリフと更新後の盤面を送信します。

```json
{
  "type": "speech",
  "payload": {
    "emotion": "happy",
    "speech": "ここに置きます！",
    "board": ["", "", "", "", "O", "", "", "", ""],
    "board_state": "xxx"
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `emotion` | `string` | 感情の種類（下表参照） |
| `speech` | `string` | キャラクターのセリフ（日本語） |
| `board` | `string[9]` | 更新後の盤面状態 |
| `board_state` | `string` | テキスト形式の盤面表示 |

**感情の選択肢**:
`normal`, `happy`, `angry`, `sad`, `surprised`, `shy`, `excited`, `smug`, `calm`

---

#### ゲーム終了通知（`game_over`）

勝敗が確定した時に送信されます。

```json
{
  "type": "game_over",
  "payload": {
    "winner": "O",
    "emotion": "happy",
    "speech": "勝ちました！",
    "board": ["O", "X", "O", "X", "O", "", "X", "", "O"],
    "board_state": "xxx"
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `winner` | `string` | 勝者。`"O"` = AI勝利, `"X"` = 相手勝利, `"draw"` = 引き分け |
| `emotion` | `string` | 感情の種類 |
| `speech` | `string` | キャラクターのセリフ |
| `board` | `string[9]` | 最終盤面状態 |
| `board_state` | `string` | テキスト形式の盤面表示 |

---

#### 配置失敗通知（`placement_failure`）

Robot がコマの配置に失敗した場合に送信されます。

```json
{
  "type": "placement_failure",
  "payload": {
    "error_message": "コマの配置に失敗しました",
    "position": 4
  }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `error_message` | `string` | エラーメッセージ |
| `position` | `int` | 失敗した位置（0-8） |

---