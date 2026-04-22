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
    build_board_state_visualization,
    format_board_state_text,
    parse_board_cells_from_file,
    recognize_board_state_from_cells,
    recognize_board_state_from_files,
)


def _sample_image_path() -> Path:
    return CURRENT_FILE.parent / "test_data" / "camera_frame_roi.jpg"


def _board_result_path() -> Path:
    return CURRENT_FILE.parent / "test_data" / "08_board_recognition_result.txt"


def _artifact_output_dir() -> Path:
    return CURRENT_FILE.parents[3] / "output" / "cell_recognition"


def _write_cell_recognition_artifacts(
    frame: np.ndarray,
    cells,
    board_state: list[list[int]],
) -> None:
    output_dir = _artifact_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    vis = build_board_state_visualization(frame, cells, board_state)
    cv2.imwrite(str(output_dir / "09_cell_recognition_visualization.jpg"), vis)

    result_text = format_board_state_text(board_state)
    (output_dir / "10_cell_recognition_result.txt").write_text(
        result_text,
        encoding="utf-8",
    )


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
    frame = cv2.imread(str(_sample_image_path()))
    assert frame is not None
    cells = parse_board_cells_from_file(_board_result_path())

    board_state = recognize_board_state_from_cells(
        frame,
        cells,
        config=CellRecognitionConfig(
            min_color_ratio=0.15,
            crop_margin_ratio=0.10,
        ),
    )

    _write_cell_recognition_artifacts(frame, cells, board_state)

    result_path = _artifact_output_dir() / "10_cell_recognition_result.txt"
    vis_path = _artifact_output_dir() / "09_cell_recognition_visualization.jpg"
    assert result_path.exists()
    assert result_path.stat().st_size > 0
    assert vis_path.exists()
    assert vis_path.stat().st_size > 0

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


def test_recognize_board_state_from_files_api() -> None:
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
