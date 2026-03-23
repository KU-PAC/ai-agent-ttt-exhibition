using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Raw Imageに表示する画像を一定間隔で切り替えるコンポーネント
/// </summary>
public class ImageSwitcher : MonoBehaviour
{
    [SerializeField]
    private Texture[] images;  // 切り替える画像の配列

    [SerializeField]
    private float switchInterval = 2.0f;  // 画像を切り替える間隔（秒）

    private RawImage rawImage;  // アタッチされているRaw Imageコンポーネント
    private float timer;  // 経過時間
    private int currentIndex;  // 現在表示している画像のインデックス

    private void Start()
    {
        // アタッチされているRaw Imageコンポーネントを取得
        rawImage = GetComponent<RawImage>();
        if (rawImage == null)
        {
            Debug.LogError("Raw Imageコンポーネントが見つかりません");
            return;
        }

        // 画像配列が空でないことを確認
        if (images == null || images.Length == 0)
        {
            Debug.LogError("画像が設定されていません");
            return;
        }

        // 初期画像を設定
        rawImage.texture = images[0];
    }

    private void Update()
    {
        // タイマーを更新
        timer += Time.deltaTime;

        // 設定された間隔を超えたら画像を切り替え
        if (timer >= switchInterval)
        {
            // 次の画像のインデックスを計算
            currentIndex = (currentIndex + 1) % images.Length;
            // Raw Imageの画像を更新
            rawImage.texture = images[currentIndex];
            // タイマーをリセット
            timer = 0f;
        }
    }
}
