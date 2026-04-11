from __future__ import annotations

CELL_SYMBOLS = {0: "＿", 1: "〇", 2: "✕"}


def render_board(cells: list[int]) -> str:
    rows = []
    for r in range(3):
        parts = []
        for c in range(3):
            idx = r * 3 + c
            sym = CELL_SYMBOLS.get(cells[idx], "＿")
            parts.append(f" {sym} ")
        rows.append("|".join(parts))
    separator = "----+----+----"
    return f"\n{separator}\n".join(rows)


def render_index_guide() -> str:
    rows = []
    for r in range(3):
        parts = [f" {r * 3 + c}  " for c in range(3)]
        rows.append("|".join(parts))
    separator = "----+----+----"
    return f"\n{separator}\n".join(rows)


def prompt_human_move(cells: list[int]) -> int:
    empty = [i for i, v in enumerate(cells) if v == 0]
    while True:
        try:
            raw = input(f"\nあなたの番です ({','.join(map(str, empty))}): ")
            pos = int(raw.strip())
            if pos in empty:
                return pos
            print(f"  マス{pos}は空いていません。")
        except (ValueError, EOFError):
            print("  0-8の数字を入力してください。")
