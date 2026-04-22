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


@dataclass(frozen=True, slots=True)
class RoiRect:
    """Rectangle ROI in pixel coordinates."""

    x: int
    y: int
    width: int
    height: int


_V4L_BY_ID: Final[Path] = Path("/dev/v4l/by-id")
_SYS_VIDEO4LINUX: Final[Path] = Path("/sys/class/video4linux")
_ROI_KEYS: Final[tuple[str, ...]] = ("x", "y", "width", "height")


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


def load_roi_config(roi_config_path: str | Path) -> RoiRect:
    """Load ROI rectangle from a text file.

    File format:
      x=<int>
      y=<int>
      width=<int>
      height=<int>
    """
    config_path: Path = Path(roi_config_path)
    if not config_path.exists():
        msg: str = f"ROI config file was not found: {config_path}"
        raise CameraError(msg)

    values: dict[str, int] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line: str = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            msg = f"Invalid ROI config line: {line}"
            raise CameraError(msg)

        key, value = line.split("=", maxsplit=1)
        parsed_key: str = key.strip().lower()
        parsed_value: str = value.strip()
        if parsed_key not in _ROI_KEYS:
            msg = f"Unsupported ROI key: {parsed_key}"
            raise CameraError(msg)
        if not parsed_value.lstrip("-").isdigit():
            msg = f"ROI value must be integer: {line}"
            raise CameraError(msg)

        values[parsed_key] = int(parsed_value)

    missing: list[str] = [key for key in _ROI_KEYS if key not in values]
    if missing:
        msg = f"ROI config is missing required keys: {', '.join(missing)}"
        raise CameraError(msg)

    roi = RoiRect(
        x=values["x"],
        y=values["y"],
        width=values["width"],
        height=values["height"],
    )
    _validate_roi_shape(roi)
    return roi


def save_roi_config(roi_config_path: str | Path, roi: RoiRect) -> Path:
    """Write ROI rectangle values into a text config file."""
    _validate_roi_shape(roi)
    config_path: Path = Path(roi_config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join(
            [
                "# Camera ROI (pixels)",
                f"x={roi.x}",
                f"y={roi.y}",
                f"width={roi.width}",
                f"height={roi.height}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _validate_roi_shape(roi: RoiRect) -> None:
    """Validate ROI dimensions independent of frame size."""
    if roi.x < 0 or roi.y < 0:
        msg: str = f"ROI x/y must be >= 0. got x={roi.x}, y={roi.y}"
        raise CameraError(msg)
    if roi.width <= 0 or roi.height <= 0:
        msg = f"ROI width/height must be > 0. got w={roi.width}, h={roi.height}"
        raise CameraError(msg)


def _crop_frame_by_roi(frame: cv2.typing.MatLike, roi: RoiRect) -> cv2.typing.MatLike:
    """Crop frame by ROI and validate bounds against frame size."""
    _validate_roi_shape(roi)

    frame_height: int = int(frame.shape[0])
    frame_width: int = int(frame.shape[1])

    x_end: int = roi.x + roi.width
    y_end: int = roi.y + roi.height
    if x_end > frame_width or y_end > frame_height:
        msg: str = (
            "ROI exceeds frame bounds. "
            f"frame=({frame_width}x{frame_height}), "
            f"roi=(x={roi.x}, y={roi.y}, w={roi.width}, h={roi.height})"
        )
        raise CameraError(msg)

    return frame[roi.y : y_end, roi.x : x_end]


def _capture_frame(camera_index: int, warmup_frames: int = 5) -> cv2.typing.MatLike:
    """Capture one raw frame from the specified camera index."""
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
    finally:
        cap.release()

    return frame


def capture_one_frame(
    camera_index: int,
    output_path: str | Path,
    warmup_frames: int = 5,
    roi_config_path: str | Path | None = None,
) -> Path:
    """Capture a single frame from the specified camera and save it as an image."""
    output: Path = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    frame: cv2.typing.MatLike = _capture_frame(
        camera_index, warmup_frames=warmup_frames
    )
    if roi_config_path is not None:
        roi: RoiRect = load_roi_config(roi_config_path)
        frame = _crop_frame_by_roi(frame, roi)

    written: bool = cv2.imwrite(str(output), frame)
    if not written:
        msg: str = f"Failed to write image file: {output}"
        raise CameraError(msg)

    return output


def capture_one_frame_from_usb(
    output_path: str | Path,
    warmup_frames: int = 5,
    roi_config_path: str | Path | None = None,
) -> Path:
    """Capture one frame from external USB webcam and optionally apply ROI."""
    usb_camera: CameraDevice = require_usb_webcam()
    return capture_one_frame(
        usb_camera.index,
        output_path,
        warmup_frames=warmup_frames,
        roi_config_path=roi_config_path,
    )


def create_roi_config_with_gui(
    roi_config_path: str | Path,
    preview_image_path: str | Path,
    warmup_frames: int = 5,
) -> Path:
    """Capture full frame, let user draw ROI rectangle, and save config file."""
    usb_camera: CameraDevice = require_usb_webcam()
    frame: cv2.typing.MatLike = _capture_frame(usb_camera.index, warmup_frames)

    preview_path: Path = Path(preview_image_path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(preview_path), frame):
        msg: str = f"Failed to write preview image file: {preview_path}"
        raise CameraError(msg)

    window_name: str = "Select ROI"
    x: int
    y: int
    width: int
    height: int
    x, y, width, height = [
        int(v)
        for v in cv2.selectROI(
            window_name,
            frame,
            showCrosshair=True,
            fromCenter=False,
        )
    ]
    cv2.destroyWindow(window_name)

    roi: RoiRect = RoiRect(x=x, y=y, width=width, height=height)
    _validate_roi_shape(roi)
    _crop_frame_by_roi(frame, roi)
    return save_roi_config(roi_config_path, roi)
