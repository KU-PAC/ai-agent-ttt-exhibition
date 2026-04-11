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
    [SerializeField] private string apiKey = "";
    [SerializeField] private string modelUuid = "e9339137-2ae3-4d41-9394-fb757a7e61e6";
    [SerializeField] private string speakerUuid = "41b7785f-35cc-4089-a360-dd8a63da5e75";
    [SerializeField] private float speakingRate = 1.0f;
    [SerializeField] private float pitch = 0f;
    [SerializeField] private float volume = 1.0f;
    private const string API_BASE_URL = "https://api.aivis-project.com/v1/tts/synthesize";

    [Header("テロップ設定")]
    [SerializeField] private float characterInterval = 0.1f;
    [SerializeField] private float displayDuration = 2f;

    protected List<PlayReactionPayload> ReactionQueue => GlobalVariables.ReactionQueue;

    private static readonly HttpClient client = new HttpClient();

    private void Start()
    {
        if (string.IsNullOrEmpty(apiKey))
        {
            try
            {
                string path = System.IO.Path.Combine(Application.dataPath, "../../.env");
                if (System.IO.File.Exists(path))
                {
                    foreach (string line in System.IO.File.ReadAllLines(path))
                    {
                        if (line.StartsWith("AIVIS_API_KEY="))
                        {
                            apiKey = line.Split('=')[1].Trim(' ', '"', '\'');
                            break;
                        }
                    }
                }
            }
            catch {}
        }

        if (audioSource == null)
        {
            audioSource = gameObject.AddComponent<AudioSource>();
        }

        if (telop == null)
        {
            telop = FindObjectOfType<Telop>();
        }

        GameEvents.OnSetState += HandleSetState;
        GameEvents.OnPlayReaction += HandlePlayReaction;
    }

    private void OnDestroy()
    {
        GameEvents.OnSetState -= HandleSetState;
        GameEvents.OnPlayReaction -= HandlePlayReaction;
    }

    private void Update()
    {
        if (ReactionQueue.Count > 0 && GlobalVariables.VoiceState == 0)
        {
            GlobalVariables.VoiceState = 1;
            var payload = ReactionQueue[0];
            ReactionQueue.RemoveAt(0);
            Text2VoiceAsync(
                payload.dialogue,
                payload.emotion
            ).Forget();
        }
    }

    private void HandleSetState(SetStatePayload payload)
    {
        Debug.Log($"set_state received: {payload.state}");
        switch (payload.state)
        {
            case "thinking":
                animator.SetBool("QuQuIsThinking", true);
                break;
            case "idle":
                animator.SetBool("QuQuIsThinking", false);
                animator.SetBool("QuQuIsSearching", false);
                ResetEmotion();
                break;
            case "human_turn":
                animator.SetBool("QuQuIsThinking", false);
                animator.SetBool("QuQuIsSearching", true);
                break;
            case "error":
                animator.SetBool("QuQuIsThinking", false);
                animator.SetBool("QuQuIsSearching", false);
                break;
        }
    }

    private void HandlePlayReaction(PlayReactionPayload payload)
    {
        Debug.Log($"play_reaction received: emotion={payload.emotion}, dialogue={payload.dialogue}");
        animator.SetBool("QuQuIsThinking", false);
    }

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

            var request = new HttpRequestMessage
            {
                Method = HttpMethod.Post,
                RequestUri = new Uri(API_BASE_URL)
            };

            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);

            var voiceRequest = new AivisSpeechRequest
            {
                model_uuid = modelUuid,
                text = text,
                speaking_rate = speakingRate,
                pitch = pitch,
                volume = volume
            };

            if (!string.IsNullOrEmpty(speakerUuid))
            {
                voiceRequest.speaker_uuid = speakerUuid;
            }

            var jsonContent = JsonUtility.ToJson(voiceRequest);
            request.Content = new StringContent(jsonContent, Encoding.UTF8, "application/json");

            GlobalVariables.VoiceState = 1;

            using (var response = await client.SendAsync(request))
            {
                response.EnsureSuccessStatusCode();
                var audioData = await response.Content.ReadAsByteArrayAsync();

                GlobalVariables.VoiceState = 2;

                if (audioData.Length < 44)
                {
                    throw new Exception($"不正なWAVデータです。データ長: {audioData.Length} bytes");
                }

                var audioClip = WavUtility.ToAudioClip(audioData);
                if (telop != null)
                {
                    Color textColor = Color.HSVToRGB(0.08f, 1.0f, 0.5f);
                    telop.Display(text, textColor, characterInterval, displayDuration).Forget();
                }
                if (audioClip != null)
                {
                    audioSource.clip = audioClip;
                    audioSource.volume = 1.0f;
                    audioSource.spatialBlend = 0f;
                    audioSource.Play();
                    await UniTask.WaitWhile(() => audioSource.isPlaying);
                }
                else
                {
                    throw new Exception("音声データの変換に失敗しました");
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
            ResetEmotion();
            GlobalVariables.VoiceState = 0;
        }
    }

    private void ApplyEmotion(string emotion)
    {
        switch (emotion)
        {
            case "normal":
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.normal);
                break;
            case "happy":
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.happy);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.warai, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.nikori, 100f);
                break;
            case "angry":
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.angry);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.okori, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.niramu, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.high_light_off, 100f);
                break;
            case "sad":
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.sad);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.komaru, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.mayu_sita, 60f);
                break;
            case "surprised":
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.surprised);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.bikkuri, 50f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.hitomi_small, 40f);
                break;
            case "shy":
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.shy);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.hohozome, 100f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.komaru, 70f);
                break;
            case "excited":
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.excited);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.star, 100f);
                break;
            case "smug":
                animator.SetInteger("QuQuEmotionIdx", (int)Emotion.smug);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.okori, 50f);
                faceMR.SetBlendShapeWeight((int)QuQuMorph.zitome, 80f);
                break;
            case "calm":
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
    }
}
