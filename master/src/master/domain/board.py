from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Board"]

BOARD_SIZE = 9


@dataclass(frozen=True)
class Board:
    cells: tuple[int, ...] = tuple(0 for _ in range(BOARD_SIZE))

    def __post_init__(self) -> None:
        if len(self.cells) != BOARD_SIZE:
            raise ValueError(f"Board must have exactly {BOARD_SIZE} cells")

    @staticmethod
    def initial() -> Board:
        return Board()

    @staticmethod
    def from_list(cells: list[int]) -> Board:
        return Board(cells=tuple(cells))

    def get(self, index: int) -> int:
        return self.cells[index]

    def set(self, index: int, player: int) -> Board:
        if not (0 <= index < BOARD_SIZE):
            raise IndexError(f"Index {index} out of range [0, {BOARD_SIZE})")
        cells = list(self.cells)
        cells[index] = player
        return Board(cells=tuple(cells))

    def empty_cells(self) -> list[int]:
        return [i for i, v in enumerate(self.cells) if v == 0]

    def to_list(self) -> list[int]:
        return list(self.cells)
