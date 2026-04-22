from __future__ import annotations

import sys
from pathlib import Path

import pytest

CURRENT_FILE = Path(__file__).resolve()
PROJECT_SRC = CURRENT_FILE.parents[2]
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from lib.camera import CameraError, capture_one_frame, detect_usb_webcams


def _output_image_path() -> Path:
    return CURRENT_FILE.parents[3] / "output" / "camera_frame.jpg"


def test_capture_one_frame_from_usb_camera() -> None:
    devices = detect_usb_webcams()
    if not devices:
        pytest.skip("USB webcam was not detected. Connect a USB webcam and retry.")

    output: Path = _output_image_path()
    captured = capture_one_frame(devices[0].index, output)

    assert captured.exists()
    assert captured.stat().st_size > 0


def run_demo_capture() -> Path:
    devices = detect_usb_webcams()
    if not devices:
        msg = "USB webcam was not detected."
        raise CameraError(msg)

    output: Path = _output_image_path()
    return capture_one_frame(devices[0].index, output)


if __name__ == "__main__":
    try:
        saved = run_demo_capture()
    except CameraError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1) from exc

    print(f"[OK] Captured one frame: {saved}")
