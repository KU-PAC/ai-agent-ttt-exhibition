from __future__ import annotations

import sys
from pathlib import Path

import pytest

CURRENT_FILE = Path(__file__).resolve()
PROJECT_SRC = CURRENT_FILE.parents[2]
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from lib.camera import CameraError, capture_one_frame_from_usb, detect_usb_webcams


def _output_image_path() -> Path:
    return CURRENT_FILE.parents[3] / "output" / "camera_frame.jpg"


def test_capture_one_frame_from_usb_camera() -> None:
    if not detect_usb_webcams():
        pytest.skip(
            "External USB webcam was not detected. "
            "Built-in camera is intentionally rejected."
        )

    output: Path = _output_image_path()
    captured = capture_one_frame_from_usb(output)

    assert captured.exists()
    assert captured.stat().st_size > 0


def run_demo_capture() -> Path:
    output: Path = _output_image_path()
    return capture_one_frame_from_usb(output)


if __name__ == "__main__":
    try:
        saved = run_demo_capture()
    except CameraError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1) from exc

    print(f"[OK] Captured one frame: {saved}")
