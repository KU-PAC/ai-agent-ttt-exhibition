このリポジトリはUnityと連携して動作するSTS（Speech to Speech）エージェントのバックエンド実装です。

## 概要
Unity側で音声入力ボタンが押されると、FastAPIのエンドポイントが呼び出され、OpenAI Realtime APIの音声入力が開始されます。この時、音声と同時にテキストプロンプトも入力されます。VAD（Voice Activity Detection）はRealtime API側で実行されるため、バックエンドは処理済みテキストの返却を待ちます。
このモデルをSoundTalkModelと呼びます。
テキストが返却された時点で、Unity側にFastAPIのWebSocketでメッセージを送ります。src/old/connect_unity.pyを参照
```python
message = json.dumps(
    {
        "content": reply,
        "action": action,
        "emotion": emotion,
    }
)
```
返却されるテキストは**構造化出力**であり、エージェントの感情やツール利用（Nothing, WebSearch, Think）を制御する情報を含みます。
ツールがNothing以外の場合は、AssistModel（GPT-4.1 mini）を呼び出して追加処理を行います。
追加処理が完了したら、会話履歴を含めて別のTextTalkModel（GPT-4.1 mini）に処理結果を伝えて、応答を作成します。
こちらの応答もUnity側にFastAPIのWebSocketでメッセージを送ります。
SoundTalkModelとTextTalkModelはモデルと入力（音声かテキストか）が異なるだけであり、会話履歴やプロンプトは共有します。

## 実装方針
- バックエンドはWebSocketで実装し、`src/api.py`に実装します。
- エージェント関連のロジックは`src/agent.py`に実装します。
- エージェント制御用プロンプトは`src/prompt.py`に実装します。

## バックエンドの主な機能
1. **音声入力の開始**
   Unityからのリクエストを受け、音声＋テキストプロンプトをOpenAI Realtime APIへ送信します。また、過去の会話履歴もテキスト形式で渡します。この時、前回の応答が完了した時点から、一定時間以上経過している場合は会話履歴を削除します。
2. **RealtimeAPIへの入力**
   音声データとテキストプロンプトをAPIに送信し、VAD後の構造化テキスト出力を受信します。
3. **応答の作成**
   構造化出力を解析し、エージェントの感情やツール利用（Nothing, WebSearch, Think）を制御します。
4. **ツール呼び出し**
   ツールがNothing以外の場合は、assist model（GPT-4.1 mini等）を呼び出して追加処理を行います。

## 実装時の参考
- `src/old/ai_tuber.py`に類似機能の実装例がありますが、langchainを使わずにシンプルに実装してください。
- 入出力形式や構造化出力の例、感情・ツール制御のロジックなどは`src/old/ai_tuber.py`を参考にできます。
- プロンプトについてはsrc/old/prompt_define.pyを参考にできます。

## ディレクトリ構成例
- src/api.py ... FastAPIエンドポイント
- src/agent.py ... エージェント処理
- src/prompt.py ... プロンプト定義
- src/old/*.py ... 旧実装（参考用）
