using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// 三目並べの盤面をUI上に表示するコンポーネント.
/// 3×3 のRawImageセルを使い、駒の種類に応じて色を変化させる.
/// GameEvents.OnSpeech / OnGameStart / OnGameOver を購読して自動更新する.
/// </summary>
public class GameBoardUI : MonoBehaviour
{
    [Header("セル設定 (左上から右下の順に 9 つ割り当て)")]
    [SerializeField] private RawImage[] cells = new RawImage[9];

    [Header("色設定")]
    [SerializeField] private Color emptyColor = new Color(0.3f, 0.3f, 0.3f, 0.3f);
    [SerializeField] private Color oColor = new Color(0.2f, 0.6f, 1.0f, 1.0f);   // 青系 (AI)
    [SerializeField] private Color xColor = new Color(1.0f, 0.3f, 0.3f, 1.0f);   // 赤系 (相手)

    private string[] lastBoard = new string[9];
    private Vector3[] originalScales = new Vector3[9];

    private void Start()
    {
        // イベント購読
        GameEvents.OnSpeech += OnSpeechReceived;
        GameEvents.OnGameStart += OnGameStart;
        GameEvents.OnGameOver += OnGameOver;

        // 元のスケールを保存
        for (int i = 0; i < 9; i++)
        {
            if (cells != null && i < cells.Length && cells[i] != null)
                originalScales[i] = cells[i].transform.localScale;
            else
                originalScales[i] = Vector3.one;
        }

        // 初期表示 (空盤面)
        ClearBoard();
    }

    private void OnDestroy()
    {
        GameEvents.OnSpeech -= OnSpeechReceived;
        GameEvents.OnGameStart -= OnGameStart;
        GameEvents.OnGameOver -= OnGameOver;
    }

    // ===== イベントハンドラ =====

    private void OnSpeechReceived(SpeechPayload payload)
    {
        if (payload.board != null && payload.board.Length == 9)
        {
            UpdateBoard(payload.board);
        }
    }

    private void OnGameStart(GameStartPayload payload)
    {
        if (payload.board != null && payload.board.Length == 9)
        {
            UpdateBoard(payload.board);
        }
        else
        {
            ClearBoard();
        }
    }

    private void OnGameOver(GameOverPayload payload)
    {
        if (payload.board != null && payload.board.Length == 9)
        {
            UpdateBoard(payload.board);
        }
    }

    // ===== 盤面更新 =====

    /// <summary>
    /// 盤面を更新する
    /// </summary>
    /// <param name="board">9要素の配列: "", "O", "X"</param>
    public void UpdateBoard(string[] board)
    {
        if (board == null || board.Length != 9) return;
        if (cells == null || cells.Length != 9) return;

        for (int i = 0; i < 9; i++)
        {
            if (cells[i] == null) continue;

            string mark = board[i];
            bool isNew = (mark != lastBoard[i]);

            if (string.IsNullOrEmpty(mark))
            {
                cells[i].color = emptyColor;
            }
            else if (mark == "O")
            {
                cells[i].color = oColor;
                if (isNew) AnimateCell(cells[i], i);
            }
            else if (mark == "X")
            {
                cells[i].color = xColor;
                if (isNew) AnimateCell(cells[i], i);
            }

            lastBoard[i] = mark ?? "";
        }
    }

    /// <summary>
    /// 盤面をクリアする
    /// </summary>
    public void ClearBoard()
    {
        for (int i = 0; i < 9; i++)
        {
            lastBoard[i] = "";
            if (cells != null && i < cells.Length && cells[i] != null)
            {
                cells[i].color = emptyColor;
                cells[i].transform.localScale = originalScales[i];
            }
        }
    }

    // ===== アニメーション =====

    /// <summary>
    /// セルに新しい駒が置かれた時のスケールアニメーション
    /// </summary>
    private void AnimateCell(RawImage cell, int index)
    {
        cell.transform.localScale = originalScales[index] * 0.5f;
        StartCoroutine(ScaleAnimation(cell.transform, originalScales[index]));
    }

    private System.Collections.IEnumerator ScaleAnimation(Transform target, Vector3 originalScale)
    {
        float duration = 0.3f;
        float elapsed = 0f;
        Vector3 startScale = target.localScale;
        Vector3 endScale = originalScale;

        while (elapsed < duration)
        {
            elapsed += Time.deltaTime;
            float t = elapsed / duration;
            // EaseOutBack カーブ
            float overshoot = 1.70158f;
            t = t - 1f;
            float eased = t * t * ((overshoot + 1f) * t + overshoot) + 1f;
            target.localScale = Vector3.LerpUnclamped(startScale, endScale, eased);
            yield return null;
        }

        target.localScale = originalScale;
    }
}
