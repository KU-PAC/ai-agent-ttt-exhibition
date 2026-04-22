from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

CURRENT_FILE = Path(__file__).resolve()
PROJECT_SRC = CURRENT_FILE.parents[2]
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from lib.camera import (
    CameraError,
    RoiRect,
    _crop_frame_by_roi,
    capture_one_frame_from_usb,
    detect_usb_webcams,
    load_roi_config,
    save_roi_config,
)


def _output_full_image_path() -> Path:
    return CURRENT_FILE.parents[3] / "output" / "camera_frame_full.jpg"


def _output_roi_image_path() -> Path:
    return CURRENT_FILE.parents[3] / "output" / "camera_frame_roi.jpg"


def _roi_config_path() -> Path:
    return CURRENT_FILE.parent / "test_data" / "camera_roi.txt"


def test_capture_full_and_roi_from_usb_camera() -> None:
    if not detect_usb_webcams():
        pytest.skip(
            "External USB webcam was not detected. "
            "Built-in camera is intentionally rejected."
        )

    full_output: Path = _output_full_image_path()
    roi_output: Path = _output_roi_image_path()
    roi_config: Path = _roi_config_path()

    full_captured = capture_one_frame_from_usb(full_output)
    roi_captured = capture_one_frame_from_usb(roi_output, roi_config_path=roi_config)

    assert full_captured.exists()
    assert full_captured.stat().st_size > 0
    assert roi_captured.exists()
    assert roi_captured.stat().st_size > 0

    full_image = cv2.imread(str(full_captured))
    roi_image = cv2.imread(str(roi_captured))
    assert full_image is not None
    assert roi_image is not None

    roi = load_roi_config(roi_config)
    assert roi_image.shape[1] == roi.width
    assert roi_image.shape[0] == roi.height
    assert roi_image.shape[1] <= full_image.shape[1]
    assert roi_image.shape[0] <= full_image.shape[0]


def test_roi_config_roundtrip(tmp_path: Path) -> None:
    roi_path: Path = tmp_path / "camera_roi.txt"
    source_roi = RoiRect(x=10, y=20, width=30, height=40)

    saved = save_roi_config(roi_path, source_roi)
    loaded = load_roi_config(saved)

    assert loaded == source_roi


def test_crop_frame_by_roi_returns_expected_shape() -> None:
    frame = np.zeros((100, 150, 3), dtype=np.uint8)
    roi = RoiRect(x=15, y=10, width=50, height=25)

    cropped = _crop_frame_by_roi(frame, roi)

    assert cropped.shape == (25, 50, 3)


def test_crop_frame_by_roi_rejects_out_of_bounds() -> None:
    frame = np.zeros((60, 80, 3), dtype=np.uint8)
    roi = RoiRect(x=50, y=40, width=40, height=30)

    with pytest.raises(CameraError):
        _crop_frame_by_roi(frame, roi)


def test_load_roi_config_rejects_missing_fields(tmp_path: Path) -> None:
    roi_path: Path = tmp_path / "camera_roi_invalid.txt"
    roi_path.write_text("x=1\ny=2\nwidth=100\n", encoding="utf-8")

    with pytest.raises(CameraError):
        load_roi_config(roi_path)


def run_demo_capture() -> tuple[Path, Path]:
    full_output: Path = _output_full_image_path()
    roi_output: Path = _output_roi_image_path()
    roi_config: Path = _roi_config_path()

    full_saved = capture_one_frame_from_usb(full_output)
    roi_saved = capture_one_frame_from_usb(roi_output, roi_config_path=roi_config)
    return full_saved, roi_saved


if __name__ == "__main__":
    try:
        full_saved, roi_saved = run_demo_capture()
    except CameraError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1) from exc

    print(f"[OK] Captured full frame: {full_saved}")
    print(f"[OK] Captured ROI frame: {roi_saved}")
