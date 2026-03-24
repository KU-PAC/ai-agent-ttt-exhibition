using System;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using System.Net.WebSockets;

public class WebSocketClient : MonoBehaviour
{
    [SerializeField] private bool DEBUG = false;
    [SerializeField] private string serverUrl = "ws://localhost:8000/ws/unity";
    private ClientWebSocket webSocket;
    private bool isConnecting = false;
    private bool isConnected = false;
    private bool isQuitting = false;

    // ===== デバッグ用 =====

    private void AddDebugMessages()
    {
        // speech メッセージのデバッグ
        var payload = new SpeechPayload
        {
            emotion = "happy",
            speech = "皆さん、今日も元気ですか？ 私は元気です！",
            board = new string[] { "", "", "", "", "", "", "", "", "" },
            board_state = ""
        };
        GlobalVariables.SpeechQueue.Add(payload);
    }

    // ===== ライフサイクル =====

    async void Start()
    {
        if (DEBUG)
        {
            AddDebugMessages();
            Debug.Log("Debug mode: Added test messages to queues");
            return;
        }

        await ConnectToServer();
    }

    // ===== WebSocket 接続管理 =====

    private async Task ConnectToServer()
    {
        if (isConnecting) return;
        isConnecting = true;
        webSocket = new ClientWebSocket();
        Uri serverUri = new Uri(serverUrl);
        try
        {
            await webSocket.ConnectAsync(serverUri, CancellationToken.None);
            Debug.Log("Connected to server");
            isConnected = true;
            StartReceiving();
        }
        catch (Exception e)
        {
            Debug.LogError($"WebSocket connection error: {e.Message}");
            Cleanup();
            await Task.Delay(5000);
            await ConnectToServer();
        }
        finally
        {
            isConnecting = false;
        }
    }

    private void Cleanup()
    {
        if (webSocket != null)
        {
            try
            {
                if (webSocket.State == WebSocketState.Open)
                {
                    webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Closing", CancellationToken.None).Wait();
                }
                webSocket.Dispose();
            }
            catch (Exception e)
            {
                Debug.LogError($"Error during cleanup: {e.Message}");
            }
            webSocket = null;
        }
        isConnected = false;
    }

    // ===== メッセージ送信 =====

    public async Task SendMessage(string type, string payloadJson = "{}")
    {
        if (webSocket == null || webSocket.State != WebSocketState.Open)
        {
            Debug.LogWarning("Cannot send message - WebSocket is not connected");
            return;
        }

        var messageObj = new SendMessageFormat
        {
            type = type,
            payload = payloadJson
        };
        string jsonMessage = JsonUtility.ToJson(messageObj);
        byte[] buffer = Encoding.UTF8.GetBytes(jsonMessage);
        await webSocket.SendAsync(new ArraySegment<byte>(buffer), WebSocketMessageType.Text, true, CancellationToken.None);
        Debug.Log($"Message sent: {jsonMessage}");
    }

    // ===== メッセージ受信 =====

    private async void StartReceiving()
    {
        if (webSocket == null || webSocket.State != WebSocketState.Open)
        {
            Debug.LogWarning("Cannot start receiving - WebSocket is not connected");
            return;
        }

        byte[] buffer = new byte[8192];
        while (webSocket != null && webSocket.State == WebSocketState.Open)
        {
            try
            {
                WebSocketReceiveResult result = await webSocket.ReceiveAsync(
                    new ArraySegment<byte>(buffer),
                    CancellationToken.None);

                if (result.MessageType == WebSocketMessageType.Close)
                {
                    Debug.Log("Server requested connection close");
                    await webSocket.CloseAsync(
                        WebSocketCloseStatus.NormalClosure,
                        "Closing",
                        CancellationToken.None);
                    break;
                }

                string jsonMessage = Encoding.UTF8.GetString(buffer, 0, result.Count);
                Debug.Log($"Raw message received: {jsonMessage}");
                DispatchMessage(jsonMessage);
            }
            catch (WebSocketException e)
            {
                Debug.LogError($"WebSocket error: {e.Message}");
                await HandleDisconnection();
                break;
            }
            catch (Exception e)
            {
                Debug.LogError($"Error receiving message: {e.Message}");
                await HandleDisconnection();
                break;
            }
        }
    }

    /// <summary>
    /// 受信した {type, payload} メッセージを type に応じて振り分ける
    /// </summary>
    private void DispatchMessage(string jsonMessage)
    {
        try
        {
            // まず type を取得するためにパース
            // JsonUtility はネストした JSON オブジェクトを文字列として扱えないため、
            // 手動で type と payload を抽出する
            string msgType = ExtractJsonStringField(jsonMessage, "type");
            string payloadJson = ExtractJsonObjectField(jsonMessage, "payload");

            if (string.IsNullOrEmpty(msgType))
            {
                Debug.LogWarning($"Unknown message format (no type): {jsonMessage}");
                return;
            }

            Debug.Log($"Dispatching message: type={msgType}");

            switch (msgType)
            {
                case "speech":
                    var speechPayload = JsonUtility.FromJson<SpeechPayload>(payloadJson);
                    if (speechPayload != null)
                    {
                        // 盤面を更新
                        if (speechPayload.board != null && speechPayload.board.Length == 9)
                        {
                            Array.Copy(speechPayload.board, GlobalVariables.CurrentBoard, 9);
                        }
                        GlobalVariables.SpeechQueue.Add(speechPayload);
                        GameEvents.FireSpeech(speechPayload);
                    }
                    break;

                case "game_start":
                    var startPayload = JsonUtility.FromJson<GameStartPayload>(payloadJson);
                    if (startPayload != null)
                    {
                        GlobalVariables.IsGameActive = true;
                        if (startPayload.board != null && startPayload.board.Length == 9)
                        {
                            Array.Copy(startPayload.board, GlobalVariables.CurrentBoard, 9);
                        }
                        GameEvents.FireGameStart(startPayload);
                    }
                    break;

                case "game_over":
                    var overPayload = JsonUtility.FromJson<GameOverPayload>(payloadJson);
                    if (overPayload != null)
                    {
                        GlobalVariables.IsGameActive = false;
                        if (overPayload.board != null && overPayload.board.Length == 9)
                        {
                            Array.Copy(overPayload.board, GlobalVariables.CurrentBoard, 9);
                        }
                        GameEvents.FireGameOver(overPayload);
                    }
                    break;

                case "placement_failure":
                    var failPayload = JsonUtility.FromJson<PlacementFailurePayload>(payloadJson);
                    if (failPayload != null)
                    {
                        GameEvents.FirePlacementFailure(failPayload);
                    }
                    break;

                case "error":
                    var errorPayload = JsonUtility.FromJson<ErrorPayload>(payloadJson);
                    if (errorPayload != null)
                    {
                        GameEvents.FireError(errorPayload);
                    }
                    break;

                default:
                    Debug.LogWarning($"Unknown message type: {msgType}");
                    break;
            }
        }
        catch (Exception e)
        {
            Debug.LogError($"Error dispatching message: {e.Message}\n{e.StackTrace}");
        }
    }

    // ===== JSON ヘルパー =====
    // JsonUtility はネストオブジェクトをフラットにしか扱えないため、
    // 手動で簡易パースを行う

    /// <summary>
    /// JSON文字列から指定したキーの文字列値を抽出する (簡易パーサー)
    /// </summary>
    private string ExtractJsonStringField(string json, string fieldName)
    {
        string pattern = $"\"{fieldName}\"";
        int keyIndex = json.IndexOf(pattern);
        if (keyIndex < 0) return null;

        int colonIndex = json.IndexOf(':', keyIndex + pattern.Length);
        if (colonIndex < 0) return null;

        int startQuote = json.IndexOf('"', colonIndex + 1);
        if (startQuote < 0) return null;

        int endQuote = json.IndexOf('"', startQuote + 1);
        if (endQuote < 0) return null;

        return json.Substring(startQuote + 1, endQuote - startQuote - 1);
    }

    /// <summary>
    /// JSON文字列から指定したキーのオブジェクト値を抽出する (簡易パーサー)
    /// ネストされた {} を正しくカウントして抽出する
    /// </summary>
    private string ExtractJsonObjectField(string json, string fieldName)
    {
        string pattern = $"\"{fieldName}\"";
        int keyIndex = json.IndexOf(pattern);
        if (keyIndex < 0) return "{}";

        int colonIndex = json.IndexOf(':', keyIndex + pattern.Length);
        if (colonIndex < 0) return "{}";

        // コロンの後の最初の '{' を見つける
        int braceStart = json.IndexOf('{', colonIndex + 1);
        if (braceStart < 0) return "{}";

        // 対応する '}' を見つける (ネスト対応)
        int depth = 0;
        bool inString = false;
        bool escaped = false;
        for (int i = braceStart; i < json.Length; i++)
        {
            char c = json[i];
            if (escaped)
            {
                escaped = false;
                continue;
            }
            if (c == '\\')
            {
                escaped = true;
                continue;
            }
            if (c == '"')
            {
                inString = !inString;
                continue;
            }
            if (!inString)
            {
                if (c == '{') depth++;
                else if (c == '}')
                {
                    depth--;
                    if (depth == 0)
                    {
                        return json.Substring(braceStart, i - braceStart + 1);
                    }
                }
            }
        }

        return "{}";
    }

    // ===== 切断ハンドリング =====

    private async Task HandleDisconnection()
    {
        Cleanup();
        if (!isQuitting)
        {
            Debug.Log("Attempting to reconnect...");
            await Task.Delay(3000);
            await ConnectToServer();
        }
        else
        {
            Debug.Log("Application is quitting - skipping reconnection");
        }
    }

    private void OnApplicationQuit()
    {
        Debug.Log("Application quitting - cleaning up WebSocket connection");
        isQuitting = true;
        Cleanup();
    }
}
