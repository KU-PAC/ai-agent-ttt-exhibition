# Unity Agent (3Dキャラクター演出)

Masterモジュールの `/unity` エンドポイントに直接接続し、`set_state` / `play_reaction` を受信して3Dキャラクターの演出を行う。

## アーキテクチャ（本番同等）

```
[Master :8765]
 ├── /vision ← カメラモジュール (本番) / HWシミュレータ (開発)
 ├── /robot  ← アームロボット (本番) / HWシミュレータ (開発)
 ├── /unity  ← Unity (本プロジェクト、直接接続)
 └── /control ← 制御端末
```

## Unity 起動手順

1. Master を起動
```bash
cd ../master
uv run python -m master.main
```

2. ハードウェアシミュレータを起動（開発時のみ）
```bash
cd ../master
uv run uvicorn simulator.hw_simulator:app --port 8001
```

3. Unity Editor で `UnityAgent` プロジェクトを開き Play モードに入る
   - `Connected to Master server` と表示されれば接続成功

4. ゲームプレイ（シミュレータ経由）
```bash
curl -X POST "http://localhost:8001/game/start?first_turn=human"
curl -X POST "http://localhost:8001/game/human-move?position=4"
curl http://localhost:8001/game/status
curl -X POST http://localhost:8001/game/reset
```

## Master → Unity プロトコル

| type | payload | 用途 |
|------|---------|------|
| `set_state` | `{"state": "thinking"}` | 状態変更（thinking/idle/human_turn/error） |
| `play_reaction` | `{"emotion": "happy", "dialogue": "..."}` | 感情+セリフ → 表情・音声合成 |

## 感情値

`normal`, `happy`, `angry`, `sad`, `surprised`, `shy`, `excited`, `smug`, `calm`

## 盤面 (Master仕様)

```
[0][1][2]
[3][4][5]
[6][7][8]
```
`0`=空き, `1`=人間(〇), `2`=AI(✕)
