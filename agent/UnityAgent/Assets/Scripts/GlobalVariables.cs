using System;
using System.Collections.Generic;

// ===== WebSocket メッセージフォーマット =====
// 通信フォーマット: {"type": "xxx", "payload": {...}}

/// <summary>
/// WebSocket受信メッセージの基本フォーマット
/// JsonUtility でパースするため payload は文字列で受け個別にパースする
/// </summary>
[Serializable]
public class GameMessage
{
    /// <summary>
    /// メッセージタイプ: "speech", "game_start", "game_over", "placement_failure", "error"
    /// </summary>
    public string type;
    /// <summary>
    /// ペイロード (JSON文字列)
    /// NOTE: JsonUtilityではネストしたオブジェクトを直接パースできないため文字列で受ける
    /// </summary>
    public string payload;
}

// ===== Payload データクラス =====

/// <summary>
/// speech: LLMの発話情報
/// </summary>
[Serializable]
public class SpeechPayload
{
    public string emotion;
    public string speech;
    public string[] board;
    public string board_state;
}

/// <summary>
/// game_start: ゲーム開始通知
/// </summary>
[Serializable]
public class GameStartPayload
{
    public string[] board;
    public string board_state;
}

/// <summary>
/// game_over: ゲーム終了通知
/// </summary>
[Serializable]
public class GameOverPayload
{
    /// <summary> 勝者: "O", "X", "draw" </summary>
    public string winner;
    public string emotion;
    public string speech;
    public string[] board;
    public string board_state;
}

/// <summary>
/// placement_failure: Robotの配置失敗通知
/// </summary>
[Serializable]
public class PlacementFailurePayload
{
    public string error_message;
    public int position;
}

/// <summary>
/// error: エラー通知
/// </summary>
[Serializable]
public class ErrorPayload
{
    public string error_message;
}

/// <summary>
/// WebSocket送信メッセージフォーマット
/// </summary>
[Serializable]
public class SendMessageFormat
{
    public string type;
    public string payload;
}

// ===== ゲームイベント =====

/// <summary>
/// ゲームイベントを管理する静的クラス
/// WebSocketClientからイベントを発火し、QuQu等のコンポーネントが購読する
/// </summary>
public static class GameEvents
{
    public static event Action<SpeechPayload> OnSpeech;
    public static event Action<GameStartPayload> OnGameStart;
    public static event Action<GameOverPayload> OnGameOver;
    public static event Action<PlacementFailurePayload> OnPlacementFailure;
    public static event Action<ErrorPayload> OnError;

    public static void FireSpeech(SpeechPayload payload) => OnSpeech?.Invoke(payload);
    public static void FireGameStart(GameStartPayload payload) => OnGameStart?.Invoke(payload);
    public static void FireGameOver(GameOverPayload payload) => OnGameOver?.Invoke(payload);
    public static void FirePlacementFailure(PlacementFailurePayload payload) => OnPlacementFailure?.Invoke(payload);
    public static void FireError(ErrorPayload payload) => OnError?.Invoke(payload);
}

// ===== グローバル状態 =====

public static class GlobalVariables
{
    /// <summary>
    /// セリフメッセージキュー (speech typeのペイロードをキューイング)
    /// </summary>
    public static List<SpeechPayload> SpeechQueue = new List<SpeechPayload>();

    /// <summary>
    /// 音声合成の状態 0:停止 1:音声合成中 2:音声出力中
    /// </summary>
    public static int VoiceState = 0;

    /// <summary>
    /// 現在の盤面 (9要素: "", "O", "X")
    /// </summary>
    public static string[] CurrentBoard = new string[9];

    /// <summary>
    /// ゲームが進行中かどうか
    /// </summary>
    public static bool IsGameActive = false;
}

public enum Emotion
{
    normal, // 0
    happy, // 1
    angry, // 2
    sad, // 3
    surprised, // 4
    shy, // 5
    excited, // 6
    smug, // 7
    calm, // 8
    waiting // 9
}

/// <summary>
/// QuQuのモーフ:
///  komaru, hohozome, koukakuage, bikkuri, okori, nikori, mayu_ue, mayu_sita,
/// mabataki, zitome, niramu, hitomi_small, hitomi_large, nagomi, ee, pero,
/// warai, niyari, wink_left, wink_right, heart, star, high_light_off
/// </summary>
public enum QuQuMorph
{
    komaru = 4,
    hohozome = 5,
    koukakuage = 7,
    bikkuri = 8,
    okori = 9,
    nikori = 10,
    mayu_ue = 11,
    mayu_sita = 12,
    mabataki = 13,
    zitome = 14,
    niramu = 15,
    hitomi_small = 16,
    hitomi_large = 17,
    nagomi = 19,
    ee = 21,
    pero = 22,
    warai = 43,
    niyari = 44,
    wink_left = 45,
    wink_right = 46,
    heart = 49,
    star = 50,
    high_light_off = 52,
}
