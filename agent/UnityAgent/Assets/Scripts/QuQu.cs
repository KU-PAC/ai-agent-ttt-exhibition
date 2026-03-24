using UnityEngine;
using System.Collections.Generic;
using Cysharp.Threading.Tasks;
using System;
using System.Text;
using System.Net.Http;
using System.Net.Http.Headers;

public class QuQu : MonoBehaviour
{
    [Header("コンポーネント設定")]
    [SerializeField] private AudioSource audioSource;
    [SerializeField] private SkinnedMeshRenderer faceMR;
    [SerializeField] private Animator animator;
    [SerializeField] private Telop telop;

    [Header("Aivis Speech設定")]
    [SerializeField] private string apiKey = "";  // Aivis SpeechのAPIキー
    [SerializeField] private string modelUuid = "e9339137-2ae3-4d41-9394-fb757a7e61e6";
    [SerializeField] private string speakerUuid = "41b7785f-35cc-4089-a360-dd8a63da5e75";  // 空の場合はモデルのデフォルトスピーカーを使用
    [SerializeField] private float speakingRate = 1.0f;
    [SerializeField] private float pitch = 0f;
    [SerializeField] private float volume = 1.0f;
    private const string API_BASE_URL = "https://api.aivis-project.com/v1/tts/synthesize";

    [Header("テロップ設定")]
    [SerializeField] private float characterInterval = 0.1f;
    [SerializeField] private float displayDuration = 2f;

    // ===== 定型文セリフ (ゲームイベント用) =====
    [Header("ゲーム定型文")]
    [SerializeField] private string gameStartSpeech = "ゲーム開始ですね！頑張りましょう！";
    [SerializeField] private string gameWinSpeech = "やったー！勝ちました！";
    [SerializeField] private string gameLoseSpeech = "負けちゃいました…次は頑張ります！";
    [SerializeField] private string gameDrawSpeech = "引き分けですね！いい勝負でした！";
    [SerializeField] private string placementFailureSpeech = "あれ、うまく置けなかったみたい…もう一回やってみますね。";

    protected List<SpeechPayload> SpeechQueue => GlobalVariables.SpeechQueue;

    // HTTPクライアントの静的インスタンス
    private static readonly HttpClient client = new HttpClient();

    private void Start()
    {
        if (audioSource == null)
        {
            audioSource = gameObject.AddComponent<AudioSource>();
        }

        if (telop == null)
        {
            telop = FindObjectOfType<Telop>();
            if (telop == null)
            {
                Debug.LogError("Telop component not found in the scene!");
            }
        }

        // ゲームイベントを購読
        GameEvents.OnGameStart += HandleGameStart;
        GameEvents.OnGameOver += HandleGameOver;
        GameEvents.OnPlacementFailure += HandlePlacementFailure;
        GameEvents.OnError += HandleError;
    }

    private void OnDestroy()
    {
        // イベント購読解除
        GameEvents.OnGameStart -= HandleGameStart;
        GameEvents.OnGameOver -= HandleGameOver;
        GameEvents.OnPlacementFailure -= HandlePlacementFailure;
        GameEvents.OnError -= HandleError;
    }

    private void Update()
    {
        // セリフメッセージキューの処理
        if (SpeechQueue.Count > 0 && GlobalVariables.VoiceState == 0)
        {
            GlobalVariables.VoiceState = 1; // 音声合成中
            var payload = SpeechQueue[0];
            SpeechQueue.RemoveAt(0);
            Text2VoiceAsync(
                payload.speech,
                payload.emotion
            ).Forget();
        }
    }

    // ===== ゲームイベントハンドラ =====

    private void HandleGameStart(GameStartPayload payload)
    {
        Debug.Log("ゲーム開始イベント受信");
        // 待機アニメーションをセット
        animator.SetBool("QuQuIsThinking", false);
        animator.SetBool("QuQuIsSearching", false);
        // 定型文セリフをキューに追加
        EnqueueFixedSpeech(gameStartSpeech, "excited");
    }

    private void HandleGameOver(GameOverPayload payload)
    {
        Debug.Log($"ゲーム終了イベント受信: winner={payload.winner}");
        string speech;
        string emotion;

        switch (payload.winner)
        {
            case "O": // AIの勝ち
                speech = gameWinSpeech;
                emotion = "happy";
                break;
            case "X": // 相手の勝ち
                speech = gameLoseSpeech;
                emotion = "sad";
                break;
            default: // 引き分け
                speech = gameDrawSpeech;
                emotion = "calm";
                break;
        }

        // game_over の emotion / speech がある場合はそちらを優先
        if (!string.IsNullOrEmpty(payload.speech))
        {
            speech = payload.speech;
        }
        if (!string.IsNullOrEmpty(payload.emotion))
        {
            emotion = payload.emotion;
        }

        EnqueueFixedSpeech(speech, emotion);
    }

    private void HandlePlacementFailure(PlacementFailurePayload payload)
    {
        Debug.Log($"配置失敗イベント受信: position={payload.position}, error={payload.error_message}");
        EnqueueFixedSpeech(placementFailureSpeech, "surprised");
    }

    private void HandleError(ErrorPayload payload)
    {
        Debug.LogError($"エラーイベント受信: {payload.error_message}");
        EnqueueFixedSpeech("何かエラーが起きたみたいです…", "sad");
    }

    /// <summary>
    /// 定型文セリフをSpeechQueueに追加する
    /// </summary>
    private void EnqueueFixedSpeech(string speech, string emotion)
    {
        var payload = new SpeechPayload
        {
            speech = speech,
            emotion = emotion,
            board = GlobalVariables.CurrentBoard,
            board_state = ""
        };
        SpeechQueue.Add(payload);
    }

    // ===== Aivis Speech 音声合成 =====

    [Serializable]
    private class AivisSpeechRequest
    {
        public string model_uuid;
        public string speaker_uuid;
        public string text;
        public bool use_ssml = true;
        public bool use_volume_normalizer = true;
        public string language = "ja";
        public float speaking_rate = 1.0f;
        public float emotional_intensity = 1.0f;
        public float tempo_dynamics = 1.0f;
        public float pitch = 0f;
        public float volume = 1.0f;
        public float leading_silence_seconds = 0.0f;
        public float trailing_silence_seconds = 0.1f;
        public float line_break_silence_seconds = 0.4f;
        public string output_format = "wav";
    }

    private async UniTask Text2VoiceAsync(string text, string emotion)
    {
        try
        {
            if (string.IsNullOrEmpty(apiKey))
            {
                Debug.LogError("Aivis SpeechのAPIキーが設定されていません");
                return;
            }

            ApplyEmotion(emotion);

            // リクエストの構築
            var request = new HttpRequestMessage
            {
                Method = HttpMethod.Post,
                RequestUri = new Uri(API_BASE_URL)
            };

            // ヘッダーの設定 (Bearer認証)
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);

            // リクエストボディの構築
            var voiceRequest = new AivisSpeechRequest
            {
                model_uuid = modelUuid,
                text = text,
                speaking_rate = speakingRate,
                pitch = pitch,
                volume = volume
            };

            // speakerUuidが指定されている場合のみセット
            if (!string.IsNullOrEmpty(speakerUuid))
            {
                voiceRequest.speaker_uuid = speakerUuid;
            }

            var jsonContent = JsonUtility.ToJson(voiceRequest);
            request.Content = new StringContent(jsonContent, Encoding.UTF8, "application/json");

            Debug.Log($"Aivis Speech APIリクエスト送信: text={text}");

            // 音声生成リクエストの送信
            GlobalVariables.VoiceState = 1; // 音声合成中

            using (var response = await client.SendAsync(request))
            {
                response.EnsureSuccessStatusCode();

                // Aivis Speechはレスポンスボディに直接音声データを返す
                var audioData = await response.Content.ReadAsByteArrayAsync();

                try
                {
                    // 音声データの取得と再生
                    GlobalVariables.VoiceState = 2; // 音声出力中

                    // WAVデータの解析
                    Debug.Log($"音声データの長さ: {audioData.Length} bytes");
                    if (audioData.Length < 44)
                    {
                        throw new Exception($"不正なWAVデータです。データ長: {audioData.Length} bytes");
                    }

                    var audioClip = WavUtility.ToAudioClip(audioData);
                    // テロップ表示
                    if (telop != null)
                    {
                        Color textColor = Color.HSVToRGB(0.08f, 1.0f, 0.5f);
                        telop.Display(text, textColor, characterInterval, displayDuration).Forget();
                    }
                    if (audioClip != null)
                    {
                        Debug.Log($"AudioClipの設定: 長さ={audioClip.length}秒, チャンネル数={audioClip.channels}, 周波数={audioClip.frequency}Hz");
                        audioSource.clip = audioClip;
                        audioSource.volume = 1.0f;
                        audioSource.spatialBlend = 0f; // 2Dサウンドとして再生
                        audioSource.Play();
                        Debug.Log("音声の再生を開始しました");

                        // 音声の長さだけ待機
                        await UniTask.WaitWhile(() => audioSource.isPlaying);
                    }
                    else
                    {
                        throw new Exception("音声データの変換に失敗しました");
                    }
                }
                catch (Exception e)
                {
                    Debug.LogError($"音声データの処理中にエラーが発生しました: {e.Message}\nStackTrace: {e.StackTrace}");
                    throw;
                }
            }
        }
        catch (HttpRequestException e)
        {
            Debug.LogError($"Aivis Speech APIリクエストエラー: {e.Message}");
        }
        catch (Exception e)
        {
            Debug.LogError($"Text2Voiceエラー: {e.Message}");
        }
        finally
        {
            Debug.Log("音声出力が終了しました");
            ResetEmotion();
            GlobalVariables.VoiceState = 0;
        }
    }

    // ===== 表情制御 =====

    private void ApplyEmotion(string emotion)
    {
        switch (emotion)
        {
            case "normal":
                Debug.Log("QuQuEmotionIdx: normal");
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.normal);
                break;
            case "happy":
                Debug.Log("QuQuEmotionIdx: happy");
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.happy);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.warai, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.nikori, 100f);
                break;
            case "angry":
                Debug.Log("QuQuEmotionIdx: angry");
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.angry);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.okori, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.niramu, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.high_light_off, 100f);
                break;
            case "sad":
                Debug.Log("QuQuEmotionIdx: sad");
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.sad);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.komaru, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.mayu_sita, 60f);
                break;
            case "surprised":
                Debug.Log("QuQuEmotionIdx: surprised");
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.surprised);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.bikkuri, 50f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.hitomi_small, 40f);
                break;
            case "shy":
                Debug.Log("QuQuEmotionIdx: shy");
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.shy);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.hohozome, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.komaru, 70f);
                break;
            case "excited":
                Debug.Log("QuQuEmotionIdx: excited");
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.excited);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.star, 100f);
                break;
            case "smug":
                Debug.Log("QuQuEmotionIdx: smug");
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.smug);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.okori, 50f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.zitome, 80f);
                break;
            case "calm":
                Debug.Log("QuQuEmotionIdx: calm");
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.calm);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.nagomi, 15f);
                break;
        }
    }

    private void ResetEmotion()
    {
        faceMR.SetBlendShapeWeight((int)QuQuMorph.warai, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.nikori, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.okori, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.niramu, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.high_light_off, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.komaru, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.mayu_sita, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.bikkuri, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.hitomi_small, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.hohozome, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.star, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.zitome, 0f);
        faceMR.SetBlendShapeWeight((int)QuQuMorph.nagomi, 0f);
        animator.SetTrigger("QuQuFinishTalk");
        Debug.Log("QuQuの発話が終了しました");
    }
}
