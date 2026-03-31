using UnityEngine;
using UnityEngine.UI;

public class GameBoardUI : MonoBehaviour
{
    [Header("セル設定 (左上から右下の順に 9 つ割り当て)")]
    [SerializeField] private RawImage[] cells = new RawImage[9];

    [Header("色設定")]
    [SerializeField] private Color emptyColor = new Color(0.3f, 0.3f, 0.3f, 0.3f);
    [SerializeField] private Color humanColor = new Color(0.2f, 0.6f, 1.0f, 1.0f);  // 青系: 人間(〇) = 1
    [SerializeField] private Color aiColor = new Color(1.0f, 0.3f, 0.3f, 1.0f);     // 赤系: AI(✕) = 2

    private int[] lastBoard = new int[9];
    private Vector3[] originalScales = new Vector3[9];

    private void Start()
    {
        for (int i = 0; i < 9; i++)
        {
            if (cells != null && i < cells.Length && cells[i] != null)
                originalScales[i] = cells[i].transform.localScale;
            else
                originalScales[i] = Vector3.one;
        }
        ClearBoard();
    }

    public void UpdateBoard(int[] board)
    {
        if (board == null || board.Length != 9) return;
        if (cells == null || cells.Length != 9) return;

        for (int i = 0; i < 9; i++)
        {
            if (cells[i] == null) continue;

            int cell = board[i];
            bool isNew = (cell != lastBoard[i]);

            switch (cell)
            {
                case 1: // Human(〇)
                    cells[i].color = humanColor;
                    if (isNew) AnimateCell(cells[i], i);
                    break;
                case 2: // AI(✕)
                    cells[i].color = aiColor;
                    if (isNew) AnimateCell(cells[i], i);
                    break;
                default: // 0 = empty
                    cells[i].color = emptyColor;
                    break;
            }

            lastBoard[i] = cell;
        }
    }

    public void ClearBoard()
    {
        for (int i = 0; i < 9; i++)
        {
            lastBoard[i] = 0;
            if (cells != null && i < cells.Length && cells[i] != null)
            {
                cells[i].color = emptyColor;
                cells[i].transform.localScale = originalScales[i];
            }
        }
    }

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
            float overshoot = 1.70158f;
            t = t - 1f;
            float eased = t * t * ((overshoot + 1f) * t + overshoot) + 1f;
            target.localScale = Vector3.LerpUnclamped(startScale, endScale, eased);
            yield return null;
        }

        target.localScale = originalScale;
    }
}
