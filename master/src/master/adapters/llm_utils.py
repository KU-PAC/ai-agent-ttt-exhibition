from __future__ import annotations

import re

from master.domain.board import AI, HUMAN, Board
from master.domain.models import Emotion, Move

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

EMOTION_MAP: dict[str, Emotion] = {e.value: e for e in Emotion}

CELL_SYMBOLS = {0: "＿", HUMAN: "〇", AI: "✕"}


def extract_json(text: str) -> str:
    m = _CODE_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def parse_emotion(raw: str) -> Emotion:
    return EMOTION_MAP.get(raw.lower(), Emotion.NEUTRAL)


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
