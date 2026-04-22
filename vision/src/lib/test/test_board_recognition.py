from __future__ import annotations

import sys
from pathlib import Path

import cv2

CURRENT_FILE = Path(__file__).resolve()
PROJECT_SRC = CURRENT_FILE.parents[2]
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from lib.board_recognition import (
    build_detection_visualization,
    detect_and_rectify_board,
)


def _sample_image_path() -> Path:
    return CURRENT_FILE.parent / "test_data" / "data_01.jpg"


def _output_image_path() -> Path:
    return CURRENT_FILE.parents[3] / "output" / "board_data_01_visualization.jpg"


def test_detect_and_rectify_board_with_sample_image() -> None:
    image_path: Path = _sample_image_path()
    frame = cv2.imread(str(image_path))

    assert frame is not None

    result = detect_and_rectify_board(frame)

    assert result.warped.shape[0] == 300
    assert result.warped.shape[1] == 300
    assert result.corners.shape == (4, 2)

    visualization = build_detection_visualization(frame, result.corners, result.warped)

    output_path: Path = _output_image_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    saved: bool = cv2.imwrite(str(output_path), visualization)
    assert saved
    assert output_path.exists()
    assert output_path.stat().st_size > 0


if __name__ == "__main__":
    frame = cv2.imread(str(_sample_image_path()))
    if frame is None:
        raise SystemExit("[ERROR] failed to load sample image")

    result = detect_and_rectify_board(frame)
    visualization = build_detection_visualization(frame, result.corners, result.warped)

    output_path = _output_image_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(output_path), visualization)
    if not ok:
        raise SystemExit("[ERROR] failed to save visualization")

    print(f"[OK] saved board visualization: {output_path}")
