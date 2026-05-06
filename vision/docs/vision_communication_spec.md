# Vision モジュール 通信仕様書

master モジュールが vision モジュールに要求する WebSocket 通信インタフェースを定義するドキュメントです。

---

## 1. 接続仕様

| 項目 | 値 |
|---|---|
| プロトコル | WebSocket |
| 接続先 | master が起動する WebSocket サーバー |
| パス | `/vision` |
| デフォルトアドレス | `ws://127.0.0.1:8765/vision` |
| 環境変数 | `MASTER_HOST`（デフォルト: `127.0.0.1`）、`MASTER_PORT`（デフォルト: `8765`） |
| メッセージ形式 | JSON（UTF-8） |
| 接続方向 | **vision クライアントが master サーバーへ接続する** |

vision モジュールは起動後、上記アドレスへ WebSocket 接続を確立し、master からのリクエストを待機します。

`MASTER_HOST` に `0.0.0.0` や `::` のような bind アドレスが設定された場合、vision クライアントは接続先として `127.0.0.1` を使用します。

---

## 2. メッセージフォーマット

すべてのメッセージは以下の共通構造を持ちます。

```json
{
  "type": "<メッセージ種別>",
  "payload": { ... }
}
```

---

## 3. メッセージ仕様

### 3.1 盤面状態要求

master が vision に盤面の現在状態を問い合わせます。

#### リクエスト（master → vision）

```json
{
  "type": "request_board_state",
  "payload": {}
}
```

#### レスポンス（vision → master）

```json
{
  "type": "board_state_response",
  "payload": {
    "board": [0, 1, 0, 2, 1, 2, 0, 0, 1]
  }
}
```

**`payload.board` フィールド仕様：**

| 項目 | 値 |
|---|---|
| 型 | `list[int]`（長さ 9） |
| 並び順 | 左上から右下へ行優先（row-major）、インデックス 0〜8 |
| セル値 | `0` = 空、`1` = 人間（赤駒）、`2` = AI（青駒） |

**盤面インデックス対応：**

```
0 | 1 | 2
---------
3 | 4 | 5
---------
6 | 7 | 8
```

---

## 4. タイムアウトとリトライ

master 側のリトライポリシーは以下のとおりです。vision はリクエスト受信後、できるだけ速やかにレスポンスを返す必要があります。

| 項目 | デフォルト値 | 環境変数 |
|---|---|---|
| 1回あたりのタイムアウト | 1.0 秒 | `MASTER_VISION_TIMEOUT` |
| 最大リトライ回数 | 3 回 | `MASTER_VISION_MAX_RETRIES` |

すべてのリトライが失敗した場合、master は `VisionTimeoutError` を発生させます。

---

## 5. ポーリング動作（人間ターン検出）

人間のターン中、master は盤面変化を検出するために以下の間隔で繰り返し `request_board_state` を送信します。

| 項目 | デフォルト値 | 環境変数 |
|---|---|---|
| ポーリング間隔 | 1.0 秒 | `MASTER_POLL_INTERVAL` |
| 安定確認回数 | 2 回連続一致 | `MASTER_STABLE_COUNT` |

vision は各リクエストに対して、その瞬間のカメラ認識結果を返せばよく、ポーリングの状態管理は master 側で行います。

---

## 6. エラーハンドリング

| 状況 | master の挙動 |
|---|---|
| vision が未接続 | 即座に `VisionTimeoutError` を発生（リトライなし） |
| タイムアウト | 警告ログを出力し、リトライ |
| レスポンスの JSON 構造が不正（`KeyError` / `TypeError`） | 警告ログを出力し、リトライ |
| すべてのリトライ失敗 | `VisionTimeoutError` を発生させ、上位レイヤーへ伝播 |

---

## 7. 実装参照

| ファイル | 役割 |
|---|---|
| [src/master/adapters/vision_adapter.py](../src/master/adapters/vision_adapter.py) | VisionPort の WebSocket 実装 |
| [src/master/application/ports.py](../src/master/application/ports.py) | `VisionPort` 抽象インタフェース定義 |
| [src/master/adapters/ws_server.py](../src/master/adapters/ws_server.py) | WebSocket サーバー・接続管理 |
| [src/master/application/human_turn.py](../src/master/application/human_turn.py) | ポーリングによる人間ターン検出ロジック |
| [tests/mocks/mock_vision.py](../tests/mocks/mock_vision.py) | テスト用モック実装 |
