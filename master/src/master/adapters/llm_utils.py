from __future__ import annotations

import re

from master.domain.board import AI, HUMAN, Board
from master.domain.game_rule import WIN_LINES, check_winner
from master.domain.models import Emotion, Move

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

EMOTION_MAP: dict[str, Emotion] = {e.value: e for e in Emotion}

CELL_SYMBOLS = {0: "＿", HUMAN: "〇", AI: "✕"}

LINE_NAMES: dict[tuple[int, int, int], str] = {
    (0, 1, 2): "上段の横ライン",
    (3, 4, 5): "中段の横ライン",
    (6, 7, 8): "下段の横ライン",
    (0, 3, 6): "左列の縦ライン",
    (1, 4, 7): "中列の縦ライン",
    (2, 5, 8): "右列の縦ライン",
    (0, 4, 8): "左上→右下の斜めライン",
    (2, 4, 6): "右上→左下の斜めライン",
}


def extract_json(text: str) -> str:
    m = _CODE_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def parse_emotion(raw: str) -> Emotion:
    return EMOTION_MAP.get(raw.lower(), Emotion.NORMAL)


def render_board(board: Board, highlight: int | None = None) -> str:
    rows = []
    for r in range(3):
        cells = []
        for c in range(3):
            idx = r * 3 + c
            sym = CELL_SYMBOLS.get(board.get(idx), "＿")
            if idx == highlight:
                sym = f"[{sym}]"
            else:
                sym = f" {sym} "
            cells.append(sym)
        rows.append("|".join(cells))
    return "\n".join(rows)


def render_history(move_history: list[Move]) -> str:
    if not move_history:
        return "（初手）"
    parts = []
    for i, m in enumerate(move_history, 1):
        who = "人間(〇)" if m.player == HUMAN else "AI(✕)"
        parts.append(f"{i}. {who} → マス{m.position}")
    return "\n".join(parts)


def analyze_move(board_before: Board, position: int, player: int) -> str:
    board_after = board_before.set(position, player)
    opponent = HUMAN if player == AI else AI
    notes: list[str] = []

    winner = check_winner(board_after)
    if winner == player:
        for line in WIN_LINES:
            a, b, c = line
            if board_after.get(a) == board_after.get(b) == board_after.get(c) == player:
                name = LINE_NAMES.get(line, "")
                notes.append(f"この手で{name}が揃い、あなたの勝ちです！")
        return "\n".join(notes)

    for line in WIN_LINES:
        a, b, c = line
        cells = [board_before.get(a), board_before.get(b), board_before.get(c)]
        if (
            cells.count(opponent) == 2
            and position in line
            and board_before.get(position) == 0
        ):
            name = LINE_NAMES.get(line, "")
            notes.append(f"相手の{name}のリーチをブロックしました。")

    for line in WIN_LINES:
        a, b, c = line
        after_cells = [board_after.get(a), board_after.get(b), board_after.get(c)]
        if after_cells.count(player) == 2 and after_cells.count(0) == 1:
            name = LINE_NAMES.get(line, "")
            notes.append(f"{name}でリーチを作りました。")

    if not notes:
        total = sum(1 for i in range(9) if board_before.get(i) != 0)
        if total <= 2:
            notes.append("序盤の一手です。")
        else:
            notes.append("特に大きな動きのない一手です。")

    return "\n".join(notes)
