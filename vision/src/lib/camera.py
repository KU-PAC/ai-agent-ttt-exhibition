from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import cv2


class CameraError(RuntimeError):
    """Raised when camera detection or frame capture fails."""


@dataclass(frozen=True, slots=True)
class CameraDevice:
    """Represents a single camera device exposed on Linux."""

    index: int
    device_path: Path
    by_id_path: Path | None


_V4L_BY_ID: Final[Path] = Path("/dev/v4l/by-id")
_SYS_VIDEO4LINUX: Final[Path] = Path("/sys/class/video4linux")


def _extract_video_index(device_path: Path) -> int | None:
    """Extract an integer camera index from a path like '/dev/video2'."""
    name: str = device_path.name
    if not name.startswith("video"):
        return None
    suffix: str = name.removeprefix("video")
    if not suffix.isdigit():
        return None
    return int(suffix)


def _is_removable_video_node(device_path: Path) -> bool:
    """Return True only when the node belongs to a removable camera device."""
    video_dir: Path = _SYS_VIDEO4LINUX / device_path.name
    candidate_paths: tuple[Path, ...] = (
        video_dir / "device" / "../removable",
        video_dir / "device" / "removable",
    )

    for candidate in candidate_paths:
        try:
            value: str = (
                candidate.resolve(strict=True).read_text(encoding="utf-8").strip()
            )
        except OSError:
            continue

        # Linux reports "removable" for external devices and "fixed" for built-ins.
        if value.lower() == "removable":
            return True

    return False


def detect_usb_webcams() -> list[CameraDevice]:
    """Detect USB-connected webcams from '/dev/v4l/by-id' symlinks."""
    if not _V4L_BY_ID.exists():
        return []

    devices: dict[int, CameraDevice] = {}
    for entry in sorted(_V4L_BY_ID.iterdir()):
        if "usb" not in entry.name.lower() or "-index0" not in entry.name:
            continue

        try:
            resolved: Path = entry.resolve(strict=True)
        except OSError:
            continue

        index: int | None = _extract_video_index(resolved)
        if index is None:
            continue

        if not _is_removable_video_node(resolved):
            continue

        devices[index] = CameraDevice(
            index=index, device_path=resolved, by_id_path=entry
        )

    return [devices[i] for i in sorted(devices)]


def require_usb_webcam() -> CameraDevice:
    """Return the first detected external USB webcam, or raise CameraError."""
    devices: list[CameraDevice] = detect_usb_webcams()
    if devices:
        return devices[0]

    msg: str = (
        "No external USB webcam was detected. "
        "Built-in cameras are not allowed for this operation."
    )
    raise CameraError(msg)


def capture_one_frame(
    camera_index: int,
    output_path: str | Path,
    warmup_frames: int = 5,
) -> Path:
    """Capture a single frame from the specified camera and save it as an image."""
    output: Path = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        cap.release()
        msg: str = f"Failed to open camera index {camera_index}."
        raise CameraError(msg)

    try:
        for _ in range(max(warmup_frames, 0)):
            cap.read()

        ok: bool
        frame: cv2.typing.MatLike
        ok, frame = cap.read()
        if not ok:
            msg = f"Failed to capture frame from camera index {camera_index}."
            raise CameraError(msg)

        written: bool = cv2.imwrite(str(output), frame)
        if not written:
            msg = f"Failed to write image file: {output}"
            raise CameraError(msg)
    finally:
        cap.release()

    return output


def capture_one_frame_from_usb(output_path: str | Path, warmup_frames: int = 5) -> Path:
    """Capture one frame from the detected external USB webcam only."""
    usb_camera: CameraDevice = require_usb_webcam()
    return capture_one_frame(usb_camera.index, output_path, warmup_frames=warmup_frames)
