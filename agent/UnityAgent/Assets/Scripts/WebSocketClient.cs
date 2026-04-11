using System;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using System.Net.WebSockets;

public class WebSocketClient : MonoBehaviour
{
    [SerializeField] private bool DEBUG = false;
    [SerializeField] private string serverUrl = "ws://localhost:8765/unity";
    private ClientWebSocket webSocket;
    private bool isConnecting = false;
    private bool isConnected = false;
    private bool isQuitting = false;

    private void AddDebugMessages()
    {
        var payload = new PlayReactionPayload
        {
            emotion = "happy",
            dialogue = "皆さん、今日も元気ですか？ 私は元気です！"
        };
        GlobalVariables.ReactionQueue.Add(payload);
    }

    async void Start()
    {
        if (DEBUG)
        {
            AddDebugMessages();
            return;
        }
        await ConnectToServer();
    }

    private async Task ConnectToServer()
    {
        if (isConnecting) return;
        isConnecting = true;

        while (!isQuitting)
        {
            Cleanup();
            webSocket = new ClientWebSocket();
            try
            {
                await webSocket.ConnectAsync(new Uri(serverUrl), CancellationToken.None);
                Debug.Log("Connected to Master server");
                isConnected = true;
                isConnecting = false;
                StartReceiving();
                return;
            }
            catch (Exception e)
            {
                Debug.LogWarning($"WebSocket connection failed: {e.Message} — retrying in 3s");
                Cleanup();
                await Task.Delay(3000);
            }
        }

        isConnecting = false;
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

    private void DispatchMessage(string jsonMessage)
    {
        try
        {
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
                case "set_state":
                    var statePayload = JsonUtility.FromJson<SetStatePayload>(payloadJson);
                    if (statePayload != null)
                    {
                        GlobalVariables.CurrentState = statePayload.state;
                        GameEvents.FireSetState(statePayload);
                    }
                    break;

                case "play_reaction":
                    var reactionPayload = JsonUtility.FromJson<PlayReactionPayload>(payloadJson);
                    if (reactionPayload != null)
                    {
                        GlobalVariables.ReactionQueue.Add(reactionPayload);
                        GameEvents.FirePlayReaction(reactionPayload);
                    }
                    break;

                case "board_update":
                    var boardPayload = JsonUtility.FromJson<BoardUpdatePayload>(payloadJson);
                    if (boardPayload != null && boardPayload.board != null && boardPayload.board.Length == 9)
                    {
                        GameEvents.FireBoardUpdate(boardPayload.board);
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

    private string ExtractJsonObjectField(string json, string fieldName)
    {
        string pattern = $"\"{fieldName}\"";
        int keyIndex = json.IndexOf(pattern);
        if (keyIndex < 0) return "{}";

        int colonIndex = json.IndexOf(':', keyIndex + pattern.Length);
        if (colonIndex < 0) return "{}";

        int braceStart = json.IndexOf('{', colonIndex + 1);
        if (braceStart < 0) return "{}";

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

    private async Task HandleDisconnection()
    {
        Cleanup();
        if (!isQuitting)
        {
            Debug.Log("Attempting to reconnect...");
            await Task.Delay(3000);
            await ConnectToServer();
        }
    }

    private void OnApplicationQuit()
    {
        isQuitting = true;
        Cleanup();
    }
}
