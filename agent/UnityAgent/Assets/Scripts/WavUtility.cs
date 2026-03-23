using UnityEngine;
using System;

public static class WavUtility
{
    public static AudioClip ToAudioClip(byte[] wavData)
    {
        try
        {
            if (wavData == null || wavData.Length < 12)
            {
                Debug.LogError($"無効なWAVデータです: {(wavData == null ? "null" : $"length={wavData.Length}")}");
                return null;
            }

            // RIFFヘッダーの確認
            string riffHeader = System.Text.Encoding.ASCII.GetString(wavData, 0, 4);
            string waveFormat = System.Text.Encoding.ASCII.GetString(wavData, 8, 4);
            Debug.Log($"WAVヘッダー: RIFF='{riffHeader}', Format='{waveFormat}'");

            if (riffHeader != "RIFF" || waveFormat != "WAVE")
            {
                Debug.LogError($"有効なWAVファイルではありません (RIFF='{riffHeader}', Format='{waveFormat}')");
                // 先頭バイトをダンプしてデバッグ
                string hexDump = "";
                for (int h = 0; h < Math.Min(64, wavData.Length); h++)
                    hexDump += wavData[h].ToString("X2") + " ";
                Debug.LogError($"先頭64バイト: {hexDump}");
                return null;
            }

            // チャンクベースでパース
            int channels = 0;
            int sampleRate = 0;
            int bitsPerSample = 0;
            int dataOffset = -1;
            int dataSize = 0;

            int pos = 12; // "RIFF" + size + "WAVE" の後から開始
            while (pos < wavData.Length - 8)
            {
                string chunkId = System.Text.Encoding.ASCII.GetString(wavData, pos, 4);
                int chunkSize = BitConverter.ToInt32(wavData, pos + 4);
                Debug.Log($"チャンク発見: id='{chunkId}', size={chunkSize}, offset={pos}");

                if (chunkId == "fmt ")
                {
                    channels = BitConverter.ToInt16(wavData, pos + 10);
                    sampleRate = BitConverter.ToInt32(wavData, pos + 12);
                    bitsPerSample = BitConverter.ToInt16(wavData, pos + 22);
                    Debug.Log($"fmtチャンク解析: ch={channels}, rate={sampleRate}, bits={bitsPerSample}");
                }
                else if (chunkId == "data")
                {
                    dataOffset = pos + 8;
                    dataSize = chunkSize;

                    // dataSizeが0または不正な場合、残りのバイト数をデータサイズとして使う
                    if (dataSize <= 0 || dataOffset + dataSize > wavData.Length)
                    {
                        int remaining = wavData.Length - dataOffset;
                        Debug.LogWarning($"dataチャンクサイズ補正: {dataSize} -> {remaining}");
                        dataSize = remaining;
                    }
                    break; // dataチャンクが見つかったらループ終了
                }

                // 次のチャンクへ (チャンクヘッダー8バイト + チャンクデータ)
                // チャンクサイズが奇数の場合、パディングバイトがある
                pos += 8 + chunkSize;
                if (chunkSize % 2 != 0) pos += 1; // パディング
            }

            if (dataOffset < 0)
            {
                Debug.LogError("dataチャンクが見つかりません");
                return null;
            }

            if (channels <= 0 || sampleRate <= 0 || bitsPerSample <= 0)
            {
                Debug.LogError($"不正なフォーマット情報: ch={channels}, rate={sampleRate}, bits={bitsPerSample}");
                return null;
            }

            int bytesPerSample = bitsPerSample / 8;
            int samplesPerChannel = dataSize / bytesPerSample / channels;
            Debug.Log($"データ解析: dataOffset={dataOffset}, dataSize={dataSize}, samplesPerChannel={samplesPerChannel}");

            if (samplesPerChannel <= 0)
            {
                Debug.LogError($"サンプル数が0です: dataSize={dataSize}, bytesPerSample={bytesPerSample}, channels={channels}");
                return null;
            }

            // AudioClipを作成
            var audioClip = AudioClip.Create("voice", samplesPerChannel, channels, sampleRate, false);

            // 音声データをfloat配列に変換
            var audioData = new float[samplesPerChannel * channels];

            for (int i = 0; i < samplesPerChannel * channels; i++)
            {
                int byteIndex = dataOffset + i * bytesPerSample;
                if (byteIndex + bytesPerSample > wavData.Length) break;

                switch (bitsPerSample)
                {
                    case 32:
                        float sample32 = BitConverter.ToSingle(wavData, byteIndex);
                        audioData[i] = Mathf.Clamp(sample32, -1f, 1f);
                        break;
                    case 16:
                        short sample16 = BitConverter.ToInt16(wavData, byteIndex);
                        audioData[i] = sample16 / 32768f;
                        break;
                    case 8:
                        audioData[i] = (wavData[byteIndex] - 128) / 128f;
                        break;
                    default:
                        Debug.LogError($"未対応のビット深度です: {bitsPerSample}bit");
                        return null;
                }
            }

            audioClip.SetData(audioData, 0);
            Debug.Log($"AudioClip作成成功: 長さ={audioClip.length}秒");
            return audioClip;
        }
        catch (Exception e)
        {
            Debug.LogError($"WAVデータの変換中にエラーが発生しました: {e.Message}\n{e.StackTrace}");
            return null;
        }
    }
}
