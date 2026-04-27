from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

CURRENT_FILE = Path(__file__).resolve()
PROJECT_SRC = CURRENT_FILE.parents[2]
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from lib.board_recognition import (
    BoardRecognitionError,
    build_detection_visualization,
    detect_and_rectify_board_with_debug,
)


def _sample_image_path() -> Path:
    return CURRENT_FILE.parent / "test_data" / "camera_frame_roi.jpg"


def _output_image_path() -> Path:
    return (
        CURRENT_FILE.parents[3] / "output" / "camera_frame_roi_board_visualization.jpg"
    )


def _debug_output_dir() -> Path:
    return CURRENT_FILE.parents[3] / "output" / "camera_frame_roi_debug"


def _format_board_result_text(result) -> str:
    lines: list[str] = []
    lines.append("board_recognition_result")
    lines.append("")

    lines.append("corners:")
    for idx, corner in enumerate(result.corners):
        x = float(corner[0])
        y = float(corner[1])
        lines.append(f"  {idx}: x={x:.3f}, y={y:.3f}")

    lines.append("")
    lines.append(f"cells_count: {len(result.cells)}")
    lines.append("cells:")
    for cell in result.cells:
        center_x = float(cell.center[0])
        center_y = float(cell.center[1])
        corner_text = ", ".join(
            f"({float(pt[0]):.3f},{float(pt[1]):.3f})" for pt in cell.corners
        )
        lines.append(
            f"  r{cell.row}c{cell.col}: center=({center_x:.3f},{center_y:.3f})"
        )
        lines.append(f"    corners={corner_text}")

    return "\n".join(lines) + "\n"


def _write_debug_artifacts(frame, result, debug) -> None:
    output_dir: Path = _debug_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(str(output_dir / "01_gray.jpg"), debug.gray)
    cv2.imwrite(str(output_dir / "02_binary.jpg"), debug.binary)
    cv2.imwrite(str(output_dir / "03_cleaned.jpg"), debug.cleaned)
    cv2.imwrite(str(output_dir / "04_line_support_mask.jpg"), debug.line_support_mask)
    cv2.imwrite(str(output_dir / "04_contours_overlay.jpg"), debug.contours_overlay)
    cv2.imwrite(
        str(output_dir / "05_vertex_directions_overlay.jpg"),
        debug.vertex_directions_overlay,
    )
    cv2.imwrite(str(output_dir / "06_warped.jpg"), result.warped)

    detection_vis = build_detection_visualization(frame, result.corners, result.warped)
    cv2.imwrite(str(output_dir / "07_detection_visualization.jpg"), detection_vis)

    result_text = _format_board_result_text(result)
    (output_dir / "08_board_recognition_result.txt").write_text(
        result_text,
        encoding="utf-8",
    )


def _write_partial_debug_artifacts(
    frame: np.ndarray,
    error: BoardRecognitionError,
) -> None:
    output_dir: Path = _debug_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    debug_image_paths: list[tuple[str, str]] = [
        ("gray", "01_gray.jpg"),
        ("binary", "02_binary.jpg"),
        ("cleaned", "03_cleaned.jpg"),
        ("line_support_mask", "04_line_support_mask.jpg"),
        ("contours_overlay", "04_contours_overlay.jpg"),
        ("vertex_directions_overlay", "05_vertex_directions_overlay.jpg"),
    ]

    saved_files: list[str] = []
    for key, filename in debug_image_paths:
        image = error.debug_images.get(key)
        if image is None:
            continue
        if cv2.imwrite(str(output_dir / filename), image):
            saved_files.append(filename)

    cv2.imwrite(str(output_dir / "00_input_frame.jpg"), frame)

    lines = [
        "board_recognition_failure",
        "",
        f"error: {error}",
        "saved_debug_images:",
    ]
    if saved_files:
        lines.extend(f"  - {name}" for name in saved_files)
    else:
        lines.append("  - (none)")

    (output_dir / "08_board_recognition_failure.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def test_detect_and_rectify_board_with_sample_image() -> None:
    image_path: Path = _sample_image_path()
    frame = cv2.imread(str(image_path))

    assert frame is not None

    try:
        result, debug = detect_and_rectify_board_with_debug(frame)
    except BoardRecognitionError as exc:
        _write_partial_debug_artifacts(frame, exc)
        raise

    assert result.warped.shape[0] == 300
    assert result.warped.shape[1] == 300
    assert result.corners.shape == (4, 2)
    assert len(result.cells) == 9

    first_cell = result.cells[0]
    assert first_cell.row == 0
    assert first_cell.col == 0
    assert first_cell.corners.shape == (4, 2)
    assert first_cell.center.shape == (2,)

    contour_area = float(cv2.contourArea(result.corners.astype(np.float32)))
    assert contour_area > 10_000.0

    _write_debug_artifacts(frame, result, debug)
    result_text_path = _debug_output_dir() / "08_board_recognition_result.txt"
    assert result_text_path.exists()
    assert result_text_path.stat().st_size > 0

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

    result, debug = detect_and_rectify_board_with_debug(frame)
    _write_debug_artifacts(frame, result, debug)
    visualization = build_detection_visualization(frame, result.corners, result.warped)

    output_path = _output_image_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(output_path), visualization)
    if not ok:
        raise SystemExit("[ERROR] failed to save visualization")

    print(f"[OK] saved board visualization: {output_path}")
