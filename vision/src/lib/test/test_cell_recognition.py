from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

CURRENT_FILE = Path(__file__).resolve()
PROJECT_SRC = CURRENT_FILE.parents[2]
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from lib.cell_recognition import (
    CELL_EMPTY,
    CELL_RED,
    CellRecognitionConfig,
    parse_board_cells_from_file,
    recognize_board_state_from_cells,
    recognize_board_state_from_files,
)


def _sample_image_path() -> Path:
    return CURRENT_FILE.parent / "test_data" / "camera_frame_roi.jpg"


def _board_result_path() -> Path:
    return CURRENT_FILE.parent / "test_data" / "08_board_recognition_result.txt"


def test_parse_board_cells_from_file() -> None:
    cells = parse_board_cells_from_file(_board_result_path())

    assert len(cells) == 9
    assert [(cell.row, cell.col) for cell in cells] == [
        (row, col) for row in range(3) for col in range(3)
    ]

    first = cells[0]
    assert first.center.shape == (2,)
    assert first.corners.shape == (4, 2)


def test_recognize_board_state_from_files_sample_image() -> None:
    board_state = recognize_board_state_from_files(
        _sample_image_path(),
        _board_result_path(),
        config=CellRecognitionConfig(
            min_color_ratio=0.15,
            crop_margin_ratio=0.10,
        ),
    )

    assert board_state == [
        [CELL_EMPTY, CELL_EMPTY, CELL_EMPTY],
        [CELL_EMPTY, CELL_EMPTY, CELL_EMPTY],
        [CELL_EMPTY, CELL_EMPTY, CELL_EMPTY],
    ]


def test_recognize_board_state_from_cells_with_synthetic_red_piece() -> None:
    frame = cv2.imread(str(_sample_image_path()))
    assert frame is not None

    cells = parse_board_cells_from_file(_board_result_path())
    target = cells[4]

    polygon = np.round(target.corners).astype(np.int32)
    cv2.fillConvexPoly(frame, polygon, color=(0, 0, 255))

    board_state = recognize_board_state_from_cells(
        frame,
        cells,
        config=CellRecognitionConfig(
            min_color_ratio=0.10,
            crop_margin_ratio=0.10,
        ),
    )

    assert board_state[1][1] == CELL_RED
