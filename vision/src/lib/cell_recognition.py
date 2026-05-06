from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import cv2
import numpy as np
import numpy.typing as npt

UInt8Array = npt.NDArray[np.uint8]
FloatArray = npt.NDArray[np.float32]

CELL_EMPTY: Final[int] = 0
CELL_RED: Final[int] = 1
CELL_BLUE: Final[int] = 2
BOARD_SIZE: Final[int] = 3
PAIR_VALUE_COUNT: Final[int] = 2
CELL_CORNER_COUNT: Final[int] = 4
MIN_VALID_WARP_SIZE: Final[int] = 2
EXPECTED_CELL_COUNT: Final[int] = BOARD_SIZE * BOARD_SIZE
HSV_COMPONENT_COUNT: Final[int] = 3
BLUE_H_MAX_FIXED: Final[int] = 150


class CellRecognitionError(RuntimeError):
    """Raised when cell recognition fails due to invalid input or parse errors."""


@dataclass(frozen=True, slots=True)
class BoardCellGeometry:
    """Geometry of one board cell parsed from board recognition output."""

    row: int
    col: int
    center: FloatArray
    corners: FloatArray


@dataclass(frozen=True, slots=True)
class CellRecognitionConfig:
    """Color and ROI parameters for piece-state recognition."""

    color_s_threshold: int = 100
    blue_h_min: int = 100
    min_color_ratio: float = 0.15
    crop_margin_ratio: float = 0.10
    cell_warp_size: int = 100


CELL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*r(?P<row>[0-2])c(?P<col>[0-2]):\s*"
    r"center=\((?P<center>[^\)]+)\)\s*$"
)
CORNER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)"
)

CONFIG_KEY_RED_LOWER1: Final[str] = "red_lower1"
CONFIG_KEY_RED_UPPER1: Final[str] = "red_upper1"
CONFIG_KEY_RED_LOWER2: Final[str] = "red_lower2"
CONFIG_KEY_RED_UPPER2: Final[str] = "red_upper2"
CONFIG_KEY_BLUE_LOWER: Final[str] = "blue_lower"
CONFIG_KEY_BLUE_UPPER: Final[str] = "blue_upper"
CONFIG_KEY_COLOR_S_THRESHOLD: Final[str] = "color_s_threshold"
CONFIG_KEY_BLUE_H_MIN: Final[str] = "blue_h_min"
CONFIG_KEY_MIN_COLOR_RATIO: Final[str] = "min_color_ratio"
CONFIG_KEY_CROP_MARGIN_RATIO: Final[str] = "crop_margin_ratio"
CONFIG_KEY_CELL_WARP_SIZE: Final[str] = "cell_warp_size"

CONFIG_KEYS: Final[tuple[str, ...]] = (
    CONFIG_KEY_COLOR_S_THRESHOLD,
    CONFIG_KEY_BLUE_H_MIN,
    CONFIG_KEY_MIN_COLOR_RATIO,
    CONFIG_KEY_CROP_MARGIN_RATIO,
    CONFIG_KEY_CELL_WARP_SIZE,
)

LEGACY_CONFIG_KEYS: Final[tuple[str, ...]] = (
    CONFIG_KEY_RED_LOWER1,
    CONFIG_KEY_RED_UPPER1,
    CONFIG_KEY_RED_LOWER2,
    CONFIG_KEY_RED_UPPER2,
    CONFIG_KEY_BLUE_LOWER,
    CONFIG_KEY_BLUE_UPPER,
)


def _parse_pair(pair_text: str) -> FloatArray:
    values = [v.strip() for v in pair_text.split(",")]
    if len(values) != PAIR_VALUE_COUNT:
        msg = f"Invalid pair text: {pair_text!r}"
        raise CellRecognitionError(msg)
    return np.array([float(values[0]), float(values[1])], dtype=np.float32)


def _parse_hsv_triplet(value_text: str, key: str) -> tuple[int, int, int]:
    parts = [v.strip() for v in value_text.split(",")]
    if len(parts) != HSV_COMPONENT_COUNT:
        msg = f"{key} must have exactly 3 comma-separated integers."
        raise CellRecognitionError(msg)

    values = tuple(int(part) for part in parts)
    h, s, v = values
    if not (0 <= h <= 180 and 0 <= s <= 255 and 0 <= v <= 255):
        msg = f"{key} has out-of-range HSV values: {values}."
        raise CellRecognitionError(msg)
    return values


def _config_to_map(config: CellRecognitionConfig) -> dict[str, str]:
    return {
        CONFIG_KEY_COLOR_S_THRESHOLD: str(config.color_s_threshold),
        CONFIG_KEY_BLUE_H_MIN: str(config.blue_h_min),
        CONFIG_KEY_MIN_COLOR_RATIO: f"{config.min_color_ratio:.6f}",
        CONFIG_KEY_CROP_MARGIN_RATIO: f"{config.crop_margin_ratio:.6f}",
        CONFIG_KEY_CELL_WARP_SIZE: str(config.cell_warp_size),
    }


def _validate_config(config: CellRecognitionConfig) -> CellRecognitionConfig:
    if not (0 <= config.color_s_threshold <= 255):
        msg = f"{CONFIG_KEY_COLOR_S_THRESHOLD} must be within [0, 255]."
        raise CellRecognitionError(msg)
    if not (0 <= config.blue_h_min <= BLUE_H_MAX_FIXED):
        msg = f"{CONFIG_KEY_BLUE_H_MIN} must be within [0, {BLUE_H_MAX_FIXED}]."
        raise CellRecognitionError(msg)
    if not (0.0 <= config.min_color_ratio <= 1.0):
        msg = f"{CONFIG_KEY_MIN_COLOR_RATIO} must be within [0, 1]."
        raise CellRecognitionError(msg)
    if not (0.0 <= config.crop_margin_ratio < 0.5):
        msg = f"{CONFIG_KEY_CROP_MARGIN_RATIO} must be within [0, 0.5)."
        raise CellRecognitionError(msg)
    if config.cell_warp_size <= MIN_VALID_WARP_SIZE:
        msg = f"{CONFIG_KEY_CELL_WARP_SIZE} must be > {MIN_VALID_WARP_SIZE}."
        raise CellRecognitionError(msg)
    return config


def format_cell_recognition_config_text(config: CellRecognitionConfig) -> str:
    """Format cell-recognition thresholds/config to key=value text."""
    lines = ["# cell recognition thresholds", "# format: key=value"]
    config_map = _config_to_map(config)
    lines.extend(f"{key}={config_map[key]}" for key in CONFIG_KEYS)
    return "\n".join(lines) + "\n"


def parse_cell_recognition_config_text(text: str) -> CellRecognitionConfig:
    """Parse key=value text and build CellRecognitionConfig."""
    default_map = _config_to_map(CellRecognitionConfig())
    values: dict[str, str] = dict(default_map)
    legacy_values: dict[str, str] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            msg = f"Invalid config line (expected key=value): {raw_line!r}"
            raise CellRecognitionError(msg)

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key in values:
            values[key] = value
            continue
        if key in LEGACY_CONFIG_KEYS:
            legacy_values[key] = value
            continue
        msg = f"Unknown config key: {key}"
        raise CellRecognitionError(msg)

    if legacy_values:
        if CONFIG_KEY_BLUE_LOWER in legacy_values:
            blue_lower = _parse_hsv_triplet(
                legacy_values[CONFIG_KEY_BLUE_LOWER],
                CONFIG_KEY_BLUE_LOWER,
            )
            values[CONFIG_KEY_BLUE_H_MIN] = str(blue_lower[0])

            sat_candidates = [blue_lower[1]]
            if CONFIG_KEY_RED_LOWER1 in legacy_values:
                sat_candidates.append(
                    _parse_hsv_triplet(
                        legacy_values[CONFIG_KEY_RED_LOWER1],
                        CONFIG_KEY_RED_LOWER1,
                    )[1]
                )
            if CONFIG_KEY_RED_LOWER2 in legacy_values:
                sat_candidates.append(
                    _parse_hsv_triplet(
                        legacy_values[CONFIG_KEY_RED_LOWER2],
                        CONFIG_KEY_RED_LOWER2,
                    )[1]
                )
            values[CONFIG_KEY_COLOR_S_THRESHOLD] = str(max(sat_candidates))

    config = CellRecognitionConfig(
        color_s_threshold=int(values[CONFIG_KEY_COLOR_S_THRESHOLD]),
        blue_h_min=int(values[CONFIG_KEY_BLUE_H_MIN]),
        min_color_ratio=float(values[CONFIG_KEY_MIN_COLOR_RATIO]),
        crop_margin_ratio=float(values[CONFIG_KEY_CROP_MARGIN_RATIO]),
        cell_warp_size=int(values[CONFIG_KEY_CELL_WARP_SIZE]),
    )
    return _validate_config(config)


def load_cell_recognition_config(file_path: str | Path) -> CellRecognitionConfig:
    """Load thresholds/config from a key=value text file."""
    path = Path(file_path)
    return parse_cell_recognition_config_text(path.read_text(encoding="utf-8"))


def save_cell_recognition_config(
    file_path: str | Path,
    config: CellRecognitionConfig,
) -> Path:
    """Save thresholds/config to a key=value text file."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_cell_recognition_config_text(config), encoding="utf-8")
    return path


def _order_corners(corners: FloatArray) -> FloatArray:
    if corners.shape != (4, 2):
        msg = f"Expected corners shape (4, 2), got {corners.shape}."
        raise CellRecognitionError(msg)

    sums: FloatArray = corners.sum(axis=1)
    diffs: FloatArray = np.diff(corners, axis=1).reshape(-1)

    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = corners[np.argmin(sums)]
    ordered[2] = corners[np.argmax(sums)]
    ordered[1] = corners[np.argmin(diffs)]
    ordered[3] = corners[np.argmax(diffs)]
    return ordered


def parse_board_cells_from_text(text: str) -> tuple[BoardCellGeometry, ...]:
    """Parse row/col/corner geometry from board recognition result text."""
    lines = text.splitlines()
    parsed: list[BoardCellGeometry] = []

    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        match = CELL_PATTERN.match(line)
        if match is None:
            line_index += 1
            continue

        if line_index + 1 >= len(lines):
            msg = "Missing corners line after cell header."
            raise CellRecognitionError(msg)

        row = int(match.group("row"))
        col = int(match.group("col"))
        center = _parse_pair(match.group("center"))

        corners_line = lines[line_index + 1].strip()
        if not corners_line.startswith("corners="):
            msg = f"Invalid corners line: {corners_line!r}"
            raise CellRecognitionError(msg)

        corner_matches = CORNER_PATTERN.findall(corners_line)
        if len(corner_matches) != CELL_CORNER_COUNT:
            msg = f"Expected 4 corners, got {len(corner_matches)}."
            raise CellRecognitionError(msg)

        corners = np.array(
            [[float(x), float(y)] for x, y in corner_matches],
            dtype=np.float32,
        )
        parsed.append(
            BoardCellGeometry(
                row=row,
                col=col,
                center=center,
                corners=_order_corners(corners),
            )
        )
        line_index += 2

    if len(parsed) != EXPECTED_CELL_COUNT:
        msg = f"Expected 9 cells in board result text, got {len(parsed)}."
        raise CellRecognitionError(msg)

    ordered = tuple(sorted(parsed, key=lambda cell: (cell.row, cell.col)))
    expected_positions = [
        (row, col) for row in range(BOARD_SIZE) for col in range(BOARD_SIZE)
    ]
    positions = [(cell.row, cell.col) for cell in ordered]
    if positions != expected_positions:
        msg = "Parsed cells are not a complete 3x3 board."
        raise CellRecognitionError(msg)

    return ordered


def parse_board_cells_from_file(file_path: str | Path) -> tuple[BoardCellGeometry, ...]:
    """Load and parse board cell geometry from a text artifact file."""
    path = Path(file_path)
    return parse_board_cells_from_text(path.read_text(encoding="utf-8"))


def _extract_cell_patch(
    frame: UInt8Array,
    corners: FloatArray,
    config: CellRecognitionConfig,
) -> UInt8Array:
    ordered = _order_corners(corners)
    size = int(config.cell_warp_size)
    if size <= MIN_VALID_WARP_SIZE:
        msg = f"cell_warp_size must be > 2, got {size}."
        raise CellRecognitionError(msg)

    destination = np.array(
        [
            [0.0, 0.0],
            [float(size - 1), 0.0],
            [float(size - 1), float(size - 1)],
            [0.0, float(size - 1)],
        ],
        dtype=np.float32,
    )

    transform = cv2.getPerspectiveTransform(ordered, destination)
    patch = cv2.warpPerspective(frame, transform, (size, size))

    margin = int(round(size * config.crop_margin_ratio))
    if margin * 2 >= size:
        msg = "crop_margin_ratio is too large for the selected cell_warp_size."
        raise CellRecognitionError(msg)
    return patch[margin : size - margin, margin : size - margin]


def extract_cell_patch(
    frame: UInt8Array,
    corners: FloatArray,
    config: CellRecognitionConfig | None = None,
) -> UInt8Array:
    """Public wrapper to extract perspective-corrected cell patch."""
    cfg = config or CellRecognitionConfig()
    return _extract_cell_patch(frame, corners, cfg)


def recognize_cell_state(
    cell_patch: UInt8Array,
    config: CellRecognitionConfig | None = None,
) -> int:
    """Classify one cell patch to 0=empty, 1=red, 2=blue."""
    cfg = config or CellRecognitionConfig()
    _validate_config(cfg)
    hsv = cv2.cvtColor(cell_patch, cv2.COLOR_BGR2HSV)

    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    colored = sat >= cfg.color_s_threshold
    blue_region = np.logical_and(hue >= cfg.blue_h_min, hue <= BLUE_H_MAX_FIXED)
    blue_mask = np.where(np.logical_and(colored, blue_region), 255, 0).astype(np.uint8)
    red_mask = np.where(
        np.logical_and(colored, np.logical_not(blue_region)), 255, 0
    ).astype(np.uint8)

    red_count = int(cv2.countNonZero(red_mask))
    blue_count = int(cv2.countNonZero(blue_mask))

    area = cell_patch.shape[0] * cell_patch.shape[1]
    threshold = int(round(float(area) * cfg.min_color_ratio))

    red_detected = red_count > threshold
    blue_detected = blue_count > threshold

    if red_detected and blue_detected:
        return CELL_RED if red_count >= blue_count else CELL_BLUE
    if red_detected:
        return CELL_RED
    if blue_detected:
        return CELL_BLUE
    return CELL_EMPTY


def recognize_board_state_from_cells(
    frame: UInt8Array,
    cells: tuple[BoardCellGeometry, ...],
    config: CellRecognitionConfig | None = None,
) -> list[list[int]]:
    """Recognize a 3x3 board state from frame and per-cell geometry."""
    cfg = config or CellRecognitionConfig()
    if len(cells) != EXPECTED_CELL_COUNT:
        msg = f"Expected 9 cells, got {len(cells)}."
        raise CellRecognitionError(msg)

    board_state = [[CELL_EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
    for cell in cells:
        patch = _extract_cell_patch(frame, cell.corners, cfg)
        board_state[cell.row][cell.col] = recognize_cell_state(patch, cfg)
    return board_state


def recognize_board_state_from_files(
    frame_image_path: str | Path,
    board_result_text_path: str | Path,
    config: CellRecognitionConfig | None = None,
    config_file_path: str | Path | None = None,
) -> list[list[int]]:
    """Convenience API for offline tests using saved image and geometry text."""
    frame_path = Path(frame_image_path)
    frame = cv2.imread(str(frame_path))
    if frame is None:
        msg = f"Failed to load frame image: {frame_path}"
        raise CellRecognitionError(msg)

    cells = parse_board_cells_from_file(board_result_text_path)
    resolved_config = config
    if resolved_config is None and config_file_path is not None:
        resolved_config = load_cell_recognition_config(config_file_path)
    return recognize_board_state_from_cells(frame, cells, config=resolved_config)


def format_board_state_text(board_state: list[list[int]]) -> str:
    """Format board state as a simple artifact text."""
    lines: list[str] = ["cell_recognition_result", "", "board_state:"]
    for row_idx, row in enumerate(board_state):
        row_text = ", ".join(str(v) for v in row)
        lines.append(f"  row{row_idx}: [{row_text}]")
    return "\n".join(lines) + "\n"


def build_board_state_visualization(
    frame: UInt8Array,
    cells: tuple[BoardCellGeometry, ...],
    board_state: list[list[int]],
) -> UInt8Array:
    """Draw cell polygons and recognized states on the source frame."""
    overlay: UInt8Array = frame.copy()
    state_colors: dict[int, tuple[int, int, int]] = {
        CELL_EMPTY: (180, 180, 180),
        CELL_RED: (0, 0, 255),
        CELL_BLUE: (255, 0, 0),
    }
    state_labels: dict[int, str] = {
        CELL_EMPTY: "EMPTY",
        CELL_RED: "RED",
        CELL_BLUE: "BLUE",
    }

    for cell in cells:
        state = int(board_state[cell.row][cell.col])
        color = state_colors.get(state, (255, 255, 255))
        label = state_labels.get(state, str(state))

        polygon = np.round(cell.corners).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(overlay, [polygon], True, color, 2, cv2.LINE_AA)

        center_x = int(round(float(cell.center[0])))
        center_y = int(round(float(cell.center[1])))
        cv2.circle(overlay, (center_x, center_y), 3, color, -1, cv2.LINE_AA)
        cv2.putText(
            overlay,
            f"r{cell.row}c{cell.col}:{label}",
            (center_x - 40, center_y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.40,
            color,
            1,
            cv2.LINE_AA,
        )

    return overlay
