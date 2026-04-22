from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float32]
UInt8Array = npt.NDArray[np.uint8]


class BoardRecognitionError(RuntimeError):
    """Raised when board detection or perspective correction fails."""


@dataclass(frozen=True, slots=True)
class BoardDetectionResult:
    """Result object containing detected corners and perspective-corrected image."""

    corners: FloatArray
    warped: UInt8Array


@dataclass(frozen=True, slots=True)
class BoardDetectionDebug:
    """Intermediate images from the board detection pipeline."""

    gray: UInt8Array
    binary: UInt8Array
    cleaned: UInt8Array
    contours_overlay: UInt8Array


DEFAULT_WARP_WIDTH: Final[int] = 300
DEFAULT_WARP_HEIGHT: Final[int] = 300
QUAD_VERTEX_COUNT: Final[int] = 4


def _order_corners(corners: FloatArray) -> FloatArray:
    """Sort 4 points into top-left, top-right, bottom-right, bottom-left order."""
    if corners.shape != (QUAD_VERTEX_COUNT, 2):
        msg: str = f"Expected (4,2) corners, got {corners.shape}."
        raise BoardRecognitionError(msg)

    sums: FloatArray = corners.sum(axis=1)
    diffs: FloatArray = np.diff(corners, axis=1).reshape(-1)

    ordered: FloatArray = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = corners[np.argmin(sums)]  # top-left
    ordered[2] = corners[np.argmax(sums)]  # bottom-right
    ordered[1] = corners[np.argmin(diffs)]  # top-right
    ordered[3] = corners[np.argmax(diffs)]  # bottom-left
    return ordered


def _is_valid_board_candidate(
    polygon: npt.NDArray[np.int32],
    frame_width: int,
    frame_height: int,
    min_area: float,
) -> bool:
    """Apply geometric filters to reject unlikely board polygons."""
    area: float = float(cv2.contourArea(polygon))
    if area < min_area:
        return False

    if not cv2.isContourConvex(polygon):
        return False

    corners: npt.NDArray[np.int32] = polygon.reshape(QUAD_VERTEX_COUNT, 2)
    margin: int = 4
    for point in corners:
        x: int = int(point[0])
        y: int = int(point[1])
        if x <= margin or y <= margin:
            return False
        if x >= frame_width - margin or y >= frame_height - margin:
            return False

    return True


def _largest_quadrilateral(
    contours: tuple[npt.NDArray[np.int32], ...] | list[npt.NDArray[np.int32]],
    frame_width: int,
    frame_height: int,
) -> FloatArray | None:
    """Find the largest valid 4-corner polygon in the contour list."""
    min_area: float = float(frame_width * frame_height) * 0.08
    max_area: float = float(frame_width * frame_height) * 0.95
    best_polygon: npt.NDArray[np.int32] | None = None
    best_area: float = 0.0

    for contour in contours:
        perimeter: float = float(cv2.arcLength(contour, True))
        if perimeter <= 0.0:
            continue

        polygon: npt.NDArray[np.int32] = cv2.approxPolyDP(
            contour,
            0.02 * perimeter,
            True,
        )
        if len(polygon) != QUAD_VERTEX_COUNT:
            continue

        if not _is_valid_board_candidate(polygon, frame_width, frame_height, min_area):
            continue

        area: float = float(cv2.contourArea(polygon))
        if area > max_area:
            continue
        if area > best_area:
            best_area = area
            best_polygon = polygon

    if best_polygon is None:
        return None

    corners: FloatArray = best_polygon.reshape(QUAD_VERTEX_COUNT, 2).astype(np.float32)
    return _order_corners(corners)


def _build_contours_overlay(
    frame: UInt8Array,
    contours: tuple[npt.NDArray[np.int32], ...] | list[npt.NDArray[np.int32]],
    corners: FloatArray | None,
) -> UInt8Array:
    """Build an image showing extracted contours and selected corners."""
    overlay: UInt8Array = frame.copy()
    cv2.drawContours(overlay, contours, -1, (0, 165, 255), 1)

    if corners is not None:
        poly: npt.NDArray[np.int32] = corners.astype(np.int32).reshape(
            QUAD_VERTEX_COUNT,
            1,
            2,
        )
        cv2.polylines(overlay, [poly], True, (0, 255, 0), 3)

    return overlay


def _extract_largest_connected_component(mask: UInt8Array) -> UInt8Array:
    """Keep only the largest foreground connected component in a binary mask."""
    num_labels: int
    labels: npt.NDArray[np.int32]
    stats: npt.NDArray[np.int32]
    _centroids: FloatArray
    num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask,
        connectivity=8,
    )
    if num_labels <= 1:
        return mask

    foreground_areas: npt.NDArray[np.int32] = stats[1:, cv2.CC_STAT_AREA]
    largest_label: int = int(np.argmax(foreground_areas)) + 1
    largest_mask: UInt8Array = np.zeros_like(mask)
    largest_mask[labels == largest_label] = 255
    return largest_mask


def detect_board_corners(frame: UInt8Array) -> FloatArray:
    """Detect board corners as a 4-point polygon from an input frame."""
    corners, _ = detect_board_corners_with_debug(frame)
    return corners


def detect_board_corners_with_debug(
    frame: UInt8Array,
) -> tuple[FloatArray, BoardDetectionDebug]:
    """Detect board corners and return lightweight intermediate state images."""
    gray: UInt8Array = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred: UInt8Array = cv2.GaussianBlur(gray, (5, 5), 0)

    binary: UInt8Array = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        25,
        8,
    )
    cleaned: UInt8Array = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        np.ones((5, 5), dtype=np.uint8),
        iterations=1,
    )
    cleaned = _extract_largest_connected_component(cleaned)

    contours, _ = cv2.findContours(cleaned, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    frame_height: int
    frame_width: int
    frame_height, frame_width = frame.shape[:2]

    corners: FloatArray | None = _largest_quadrilateral(
        contours,
        frame_width,
        frame_height,
    )
    contours_overlay: UInt8Array = _build_contours_overlay(frame, contours, corners)
    if corners is not None:
        debug: BoardDetectionDebug = BoardDetectionDebug(
            gray=gray,
            binary=binary,
            cleaned=cleaned,
            contours_overlay=contours_overlay,
        )
        return corners, debug

    # Fallback: fit a rectangle to the largest contour in difficult frames.
    if not contours:
        msg: str = "Failed to detect board contour with 4 corners."
        raise BoardRecognitionError(msg)

    largest_contour: npt.NDArray[np.int32] = max(contours, key=cv2.contourArea)
    if (
        float(cv2.contourArea(largest_contour))
        < float(frame_width * frame_height) * 0.05
    ):
        msg = "Failed to detect a sufficiently large board contour."
        raise BoardRecognitionError(msg)

    rect = cv2.minAreaRect(largest_contour)
    box: FloatArray = cv2.boxPoints(rect).astype(np.float32)
    fallback_corners: FloatArray = _order_corners(box)
    fallback_overlay: UInt8Array = _build_contours_overlay(
        frame,
        contours,
        fallback_corners,
    )
    debug = BoardDetectionDebug(
        gray=gray,
        binary=binary,
        cleaned=cleaned,
        contours_overlay=fallback_overlay,
    )
    return fallback_corners, debug


def rectify_board_image(
    frame: UInt8Array,
    corners: FloatArray,
    width: int = DEFAULT_WARP_WIDTH,
    height: int = DEFAULT_WARP_HEIGHT,
) -> UInt8Array:
    """Apply perspective transform to create a top-down board image."""
    ordered: FloatArray = _order_corners(corners)
    destination: FloatArray = np.array(
        [
            [0.0, 0.0],
            [float(width - 1), 0.0],
            [float(width - 1), float(height - 1)],
            [0.0, float(height - 1)],
        ],
        dtype=np.float32,
    )

    transform: FloatArray = cv2.getPerspectiveTransform(ordered, destination)
    warped: UInt8Array = cv2.warpPerspective(frame, transform, (width, height))
    return warped


def detect_and_rectify_board(
    frame: UInt8Array,
    width: int = DEFAULT_WARP_WIDTH,
    height: int = DEFAULT_WARP_HEIGHT,
) -> BoardDetectionResult:
    """Detect board corners and return a perspective-corrected board image."""
    corners: FloatArray = detect_board_corners(frame)
    warped: UInt8Array = rectify_board_image(frame, corners, width=width, height=height)
    return BoardDetectionResult(corners=corners, warped=warped)


def detect_and_rectify_board_with_debug(
    frame: UInt8Array,
    width: int = DEFAULT_WARP_WIDTH,
    height: int = DEFAULT_WARP_HEIGHT,
) -> tuple[BoardDetectionResult, BoardDetectionDebug]:
    """Detect board and return both corrected image and pipeline debug images."""
    corners, debug = detect_board_corners_with_debug(frame)
    warped: UInt8Array = rectify_board_image(frame, corners, width=width, height=height)
    return BoardDetectionResult(corners=corners, warped=warped), debug


def build_detection_visualization(
    frame: UInt8Array,
    corners: FloatArray,
    warped: UInt8Array,
) -> UInt8Array:
    """Create a side-by-side visualization of detection and corrected board image."""
    overlay: UInt8Array = frame.copy()
    poly: npt.NDArray[np.int32] = corners.astype(np.int32).reshape(
        QUAD_VERTEX_COUNT,
        1,
        2,
    )
    cv2.polylines(overlay, [poly], True, (0, 255, 0), 3)

    for idx, point in enumerate(corners.astype(np.int32)):
        cv2.circle(overlay, (int(point[0]), int(point[1])), 6, (0, 0, 255), -1)
        cv2.putText(
            overlay,
            str(idx),
            (int(point[0]) + 6, int(point[1]) - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

    target_height: int = warped.shape[0]
    resized_overlay: UInt8Array = cv2.resize(
        overlay,
        (int(overlay.shape[1] * target_height / overlay.shape[0]), target_height),
    )
    return np.hstack([resized_overlay, warped])
