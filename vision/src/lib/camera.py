from __future__ import annotations

import math
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
_ROI_OPTIONAL_KEYS: Final[tuple[str, ...]] = ("frame_width", "frame_height")
_ROI_WINDOW_MAX_WIDTH: Final[int] = 1280
_ROI_WINDOW_MAX_HEIGHT: Final[int] = 720


@dataclass(frozen=True, slots=True)
class RoiConfig:
    """ROI rectangle and optional source frame size metadata."""

    roi: RoiRect
    frame_size: tuple[int, int] | None = None


@dataclass(slots=True)
class _RoiSelectionState:
    """State container for interactive ROI selection."""

    is_dragging: bool = False
    anchor: tuple[int, int] | None = None
    cursor: tuple[int, int] | None = None
    selected: tuple[tuple[int, int], tuple[int, int]] | None = None


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


def _parse_roi_config_file(roi_config_path: str | Path) -> dict[str, int]:
    """Parse ROI config file into integer values."""
    config_path: Path = Path(roi_config_path)
    if not config_path.exists():
        msg: str = f"ROI config file was not found: {config_path}"
        raise CameraError(msg)

    values: dict[str, int] = {}
    valid_keys: set[str] = {*_ROI_KEYS, *_ROI_OPTIONAL_KEYS}
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
        if parsed_key not in valid_keys:
            msg = f"Unsupported ROI key: {parsed_key}"
            raise CameraError(msg)
        if not parsed_value.lstrip("-").isdigit():
            msg = f"ROI value must be integer: {line}"
            raise CameraError(msg)

        values[parsed_key] = int(parsed_value)

    return values


def load_roi_config_with_metadata(roi_config_path: str | Path) -> RoiConfig:
    """Load ROI rectangle and optional source frame dimensions from file."""
    values = _parse_roi_config_file(roi_config_path)

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

    frame_size: tuple[int, int] | None = None
    if "frame_width" in values and "frame_height" in values:
        frame_width: int = values["frame_width"]
        frame_height: int = values["frame_height"]
        if frame_width <= 0 or frame_height <= 0:
            msg = (
                "ROI frame metadata must be positive. "
                f"got frame_width={frame_width}, frame_height={frame_height}"
            )
            raise CameraError(msg)
        frame_size = (frame_width, frame_height)

    return RoiConfig(roi=roi, frame_size=frame_size)


def load_roi_config(roi_config_path: str | Path) -> RoiRect:
    """Load ROI rectangle from a text file.

    File format:
      x=<int>
      y=<int>
      width=<int>
      height=<int>
    """
    return load_roi_config_with_metadata(roi_config_path).roi


def save_roi_config(
    roi_config_path: str | Path,
    roi: RoiRect,
    frame_size: tuple[int, int] | None = None,
) -> Path:
    """Write ROI rectangle values into a text config file."""
    _validate_roi_shape(roi)
    lines: list[str] = [
        "# Camera ROI (pixels)",
        f"x={roi.x}",
        f"y={roi.y}",
        f"width={roi.width}",
        f"height={roi.height}",
    ]
    if frame_size is not None:
        frame_width, frame_height = frame_size
        if frame_width <= 0 or frame_height <= 0:
            msg = (
                "frame_size must be positive when provided. "
                f"got frame_width={frame_width}, frame_height={frame_height}"
            )
            raise CameraError(msg)
        lines.extend(
            [
                f"frame_width={frame_width}",
                f"frame_height={frame_height}",
            ]
        )

    config_path: Path = Path(roi_config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "\n".join([*lines, ""]),
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


def _scale_roi_to_frame(
    roi: RoiRect,
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> RoiRect:
    """Scale ROI from source frame size to target frame size."""
    source_width, source_height = source_size
    target_width, target_height = target_size
    if source_width <= 0 or source_height <= 0:
        msg = (
            "source_size must be positive. "
            f"got width={source_width}, height={source_height}"
        )
        raise CameraError(msg)
    if target_width <= 0 or target_height <= 0:
        msg = (
            "target_size must be positive. "
            f"got width={target_width}, height={target_height}"
        )
        raise CameraError(msg)

    return _map_display_rect_to_frame(
        start_point=(roi.x, roi.y),
        end_point=(roi.x + roi.width, roi.y + roi.height),
        preview_size=source_size,
        frame_size=target_size,
    )


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


def _fit_preview_size(
    frame_width: int,
    frame_height: int,
    max_width: int = _ROI_WINDOW_MAX_WIDTH,
    max_height: int = _ROI_WINDOW_MAX_HEIGHT,
) -> tuple[int, int]:
    """Return preview size that keeps aspect ratio and fits the given bounds."""
    if frame_width <= 0 or frame_height <= 0:
        msg = (
            "Frame dimensions must be positive. "
            f"got width={frame_width}, height={frame_height}"
        )
        raise CameraError(msg)

    scale: float = min(max_width / frame_width, max_height / frame_height, 1.0)
    preview_width: int = max(1, int(round(frame_width * scale)))
    preview_height: int = max(1, int(round(frame_height * scale)))
    return preview_width, preview_height


def _map_display_rect_to_frame(
    start_point: tuple[int, int],
    end_point: tuple[int, int],
    preview_size: tuple[int, int],
    frame_size: tuple[int, int],
) -> RoiRect:
    """Map drag rectangle from preview coordinates to original frame coordinates."""
    preview_width, preview_height = preview_size
    frame_width, frame_height = frame_size
    if preview_width <= 0 or preview_height <= 0:
        msg = (
            "Preview dimensions must be positive. "
            f"got width={preview_width}, height={preview_height}"
        )
        raise CameraError(msg)

    left: int = min(start_point[0], end_point[0])
    right: int = max(start_point[0], end_point[0])
    top: int = min(start_point[1], end_point[1])
    bottom: int = max(start_point[1], end_point[1])

    scale_x: float = frame_width / preview_width
    scale_y: float = frame_height / preview_height

    x: int = int(math.floor(left * scale_x))
    y: int = int(math.floor(top * scale_y))
    x_end: int = int(math.ceil(right * scale_x))
    y_end: int = int(math.ceil(bottom * scale_y))

    x = max(0, min(x, frame_width - 1))
    y = max(0, min(y, frame_height - 1))
    x_end = max(x + 1, min(x_end, frame_width))
    y_end = max(y + 1, min(y_end, frame_height))

    roi = RoiRect(x=x, y=y, width=x_end - x, height=y_end - y)
    _validate_roi_shape(roi)
    return roi


def _draw_roi_overlay(
    preview: cv2.typing.MatLike,
    state: _RoiSelectionState,
) -> cv2.typing.MatLike:
    """Render the preview frame with current ROI selection overlay."""
    overlay = preview.copy()
    points = state.selected
    if state.is_dragging and state.anchor is not None and state.cursor is not None:
        points = (state.anchor, state.cursor)
    if points is not None:
        start, end = points
        x0: int = min(start[0], end[0])
        y0: int = min(start[1], end[1])
        x1: int = max(start[0], end[0])
        y1: int = max(start[1], end[1])
        cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 255, 0), 2)
    cv2.putText(
        overlay,
        "Drag: ROI  Enter: save  R: reset  Esc/Q: cancel",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return overlay


def _handle_roi_mouse_event(
    event: int,
    x: int,
    y: int,
    state: _RoiSelectionState,
    preview_size: tuple[int, int],
) -> None:
    """Update ROI selection state according to one mouse event."""
    preview_width, preview_height = preview_size
    clamped_x: int = max(0, min(x, preview_width - 1))
    clamped_y: int = max(0, min(y, preview_height - 1))
    point: tuple[int, int] = (clamped_x, clamped_y)

    if event == cv2.EVENT_LBUTTONDOWN:
        state.is_dragging = True
        state.anchor = point
        state.cursor = point
        return
    if event == cv2.EVENT_MOUSEMOVE and state.is_dragging:
        state.cursor = point
        return
    if event == cv2.EVENT_LBUTTONUP and state.is_dragging:
        state.is_dragging = False
        state.cursor = point
        if state.anchor is not None and state.cursor is not None:
            state.selected = (state.anchor, state.cursor)


def _select_roi_loop(
    window_name: str,
    preview: cv2.typing.MatLike,
    state: _RoiSelectionState,
    preview_size: tuple[int, int],
    frame_size: tuple[int, int],
) -> RoiRect:
    """Drive key handling loop and return selected ROI rectangle."""
    while True:
        cv2.imshow(window_name, _draw_roi_overlay(preview, state))
        key: int = cv2.waitKey(10) & 0xFF

        if key in (27, ord("q")):
            msg = "ROI selection was canceled by user."
            raise CameraError(msg)

        if key in (ord("r"), ord("R"), ord("c"), ord("C")):
            state.is_dragging = False
            state.anchor = None
            state.cursor = None
            state.selected = None
            continue

        if key in (13, 10):
            if state.selected is None:
                continue
            start, end = state.selected
            return _map_display_rect_to_frame(
                start,
                end,
                preview_size=preview_size,
                frame_size=frame_size,
            )


def _select_roi_on_preview(frame: cv2.typing.MatLike) -> RoiRect:
    """Select ROI with explicit preview-to-frame mapping to avoid GUI scale mismatch."""
    frame_height: int = int(frame.shape[0])
    frame_width: int = int(frame.shape[1])
    preview_width, preview_height = _fit_preview_size(frame_width, frame_height)
    if (preview_width, preview_height) == (frame_width, frame_height):
        preview = frame.copy()
    else:
        preview = cv2.resize(
            frame,
            (preview_width, preview_height),
            interpolation=cv2.INTER_AREA,
        )

    window_name: str = "Select ROI"
    state = _RoiSelectionState()

    def _on_mouse(event: int, x: int, y: int, flags: int, userdata: object) -> None:
        del flags, userdata
        _handle_roi_mouse_event(
            event,
            x,
            y,
            state=state,
            preview_size=(preview_width, preview_height),
        )

    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(window_name, _on_mouse)

    try:
        return _select_roi_loop(
            window_name,
            preview,
            state,
            preview_size=(preview_width, preview_height),
            frame_size=(frame_width, frame_height),
        )
    finally:
        cv2.destroyWindow(window_name)


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
        roi_config: RoiConfig = load_roi_config_with_metadata(roi_config_path)
        roi: RoiRect = roi_config.roi
        current_frame_size: tuple[int, int] = (
            int(frame.shape[1]),
            int(frame.shape[0]),
        )
        if (
            roi_config.frame_size is not None
            and roi_config.frame_size != current_frame_size
        ):
            roi = _scale_roi_to_frame(
                roi,
                source_size=roi_config.frame_size,
                target_size=current_frame_size,
            )
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

    roi: RoiRect = _select_roi_on_preview(frame)
    _validate_roi_shape(roi)
    _crop_frame_by_roi(frame, roi)
    frame_size: tuple[int, int] = (int(frame.shape[1]), int(frame.shape[0]))
    return save_roi_config(roi_config_path, roi, frame_size=frame_size)
