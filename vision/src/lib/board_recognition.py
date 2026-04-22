from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Final

import cv2
import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float32]
UInt8Array = npt.NDArray[np.uint8]
Int32Array = npt.NDArray[np.int32]


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
    vertex_directions_overlay: UInt8Array


DEFAULT_WARP_WIDTH: Final[int] = 300
DEFAULT_WARP_HEIGHT: Final[int] = 300
QUAD_VERTEX_COUNT: Final[int] = 4
GRID_LINE_COUNT: Final[int] = 4
DIRECTION_SWEEP_STEPS: Final[int] = 180
MAX_OFFSET_CANDIDATE_LINES: Final[int] = 7
MAX_OFFSET_SET_CANDIDATES: Final[int] = 10


def _order_corners(corners: FloatArray) -> FloatArray:
    """Sort 4 points into top-left, top-right, bottom-right, bottom-left order."""
    if corners.shape != (QUAD_VERTEX_COUNT, 2):
        msg: str = f"Expected (4,2) corners, got {corners.shape}."
        raise BoardRecognitionError(msg)

    sums: FloatArray = corners.sum(axis=1)
    diffs: FloatArray = np.diff(corners, axis=1).reshape(-1)

    ordered: FloatArray = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = corners[np.argmin(sums)]
    ordered[2] = corners[np.argmax(sums)]
    ordered[1] = corners[np.argmin(diffs)]
    ordered[3] = corners[np.argmax(diffs)]
    return ordered


def _extract_largest_connected_component(mask: UInt8Array) -> UInt8Array:
    """Keep only the largest foreground connected component in a binary mask."""
    num_labels: int
    labels: Int32Array
    stats: Int32Array
    _centroids: FloatArray
    num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask,
        connectivity=8,
    )
    if num_labels <= 1:
        return mask

    foreground_areas: Int32Array = stats[1:, cv2.CC_STAT_AREA]
    largest_label: int = int(np.argmax(foreground_areas)) + 1
    largest_mask: UInt8Array = np.zeros_like(mask)
    largest_mask[labels == largest_label] = 255
    return largest_mask


def _angle_distance(a: npt.NDArray[np.float64], b: float) -> npt.NDArray[np.float64]:
    """Distance between orientations modulo pi."""
    delta = np.abs(a - b)
    return np.minimum(delta, np.pi - delta)


def _segment_lengths(segments: Int32Array) -> npt.NDArray[np.float64]:
    delta = segments[:, 2:4].astype(np.float64) - segments[:, 0:2].astype(np.float64)
    return np.hypot(delta[:, 0], delta[:, 1])


def _detect_line_segments(mask: UInt8Array) -> Int32Array:
    """Detect candidate board line segments from a binary mask."""
    frame_height: int
    frame_width: int
    frame_height, frame_width = mask.shape
    base: int = min(frame_width, frame_height)

    threshold: int = max(30, int(base * 0.10))
    min_line_length: int = max(25, int(base * 0.15))
    max_line_gap: int = max(8, int(base * 0.04))

    lines = cv2.HoughLinesP(
        mask,
        rho=1,
        theta=np.pi / 180.0,
        threshold=threshold,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )
    if lines is None:
        return np.empty((0, 4), dtype=np.int32)
    return lines.reshape(-1, 4).astype(np.int32)


def _fit_primary_directions(
    segments: Int32Array,
) -> tuple[float, npt.NDArray[np.bool_], npt.NDArray[np.bool_]]:
    """Fit two orthogonal dominant directions from detected line segments."""
    if len(segments) < 6:
        msg: str = "Insufficient line segments for grid direction estimation."
        raise BoardRecognitionError(msg)

    lengths = _segment_lengths(segments)
    angles = np.mod(
        np.arctan2(
            segments[:, 3].astype(np.float64) - segments[:, 1].astype(np.float64),
            segments[:, 2].astype(np.float64) - segments[:, 0].astype(np.float64),
        ),
        np.pi,
    )

    total_length: float = float(np.sum(lengths))
    if total_length <= 0.0:
        msg = "Failed to estimate grid directions due to zero-length segments."
        raise BoardRecognitionError(msg)

    best_alpha: float | None = None
    best_score: float = float("inf")
    best_mask_a: npt.NDArray[np.bool_] | None = None

    for i in range(DIRECTION_SWEEP_STEPS + 1):
        alpha = (np.pi / 2.0) * (i / DIRECTION_SWEEP_STEPS)
        dist_a = _angle_distance(angles, alpha)
        dist_b = _angle_distance(angles, alpha + (np.pi / 2.0))
        mask_a = dist_a <= dist_b

        support_a = float(np.sum(lengths[mask_a]))
        support_b = float(np.sum(lengths[~mask_a]))
        if min(support_a, support_b) < total_length * 0.20:
            continue

        assignment_error = np.where(mask_a, dist_a, dist_b)
        imbalance_penalty = abs(support_a - support_b) / total_length
        score = float(np.sum(lengths * assignment_error)) + imbalance_penalty

        if score < best_score:
            best_score = score
            best_alpha = alpha
            best_mask_a = mask_a

    if best_alpha is None or best_mask_a is None:
        msg = "Failed to split line segments into two orthogonal groups."
        raise BoardRecognitionError(msg)

    return best_alpha, best_mask_a, ~best_mask_a


def _segment_midpoints(segments: Int32Array) -> npt.NDArray[np.float64]:
    endpoints = segments.astype(np.float64).reshape(-1, 2, 2)
    return np.mean(endpoints, axis=1)


def _merge_rho_candidates(
    rhos: npt.NDArray[np.float64],
    weights: npt.NDArray[np.float64],
    tolerance: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Merge nearby line offsets to remove duplicate Hough detections."""
    if len(rhos) == 0:
        return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)

    order = np.argsort(rhos)
    sorted_rhos = rhos[order]
    sorted_weights = weights[order]

    merged_rhos: list[float] = []
    merged_weights: list[float] = []

    current_values: list[float] = [float(sorted_rhos[0])]
    current_weights: list[float] = [float(sorted_weights[0])]

    for rho, weight in zip(sorted_rhos[1:], sorted_weights[1:], strict=False):
        if abs(float(rho) - current_values[-1]) <= tolerance:
            current_values.append(float(rho))
            current_weights.append(float(weight))
            continue

        block_weights = np.array(current_weights, dtype=np.float64)
        block_values = np.array(current_values, dtype=np.float64)
        merged_rhos.append(float(np.average(block_values, weights=block_weights)))
        merged_weights.append(float(np.sum(block_weights)))

        current_values = [float(rho)]
        current_weights = [float(weight)]

    block_weights = np.array(current_weights, dtype=np.float64)
    block_values = np.array(current_values, dtype=np.float64)
    merged_rhos.append(float(np.average(block_values, weights=block_weights)))
    merged_weights.append(float(np.sum(block_weights)))

    return np.array(merged_rhos, dtype=np.float64), np.array(
        merged_weights, dtype=np.float64
    )


def _enumerate_regular_offset_sets(
    candidates: npt.NDArray[np.float64],
    weights: npt.NDArray[np.float64],
) -> list[npt.NDArray[np.float64]]:
    """Enumerate top regular 4-offset sets from line candidates."""
    if len(candidates) < GRID_LINE_COUNT:
        msg = "Failed to find enough grid lines in one direction."
        raise BoardRecognitionError(msg)

    if len(candidates) > MAX_OFFSET_CANDIDATE_LINES:
        top_indices = np.argsort(weights)[-MAX_OFFSET_CANDIDATE_LINES:]
        candidates = candidates[top_indices]
        weights = weights[top_indices]

    order = np.argsort(candidates)
    candidates = candidates[order]
    weights = weights[order]

    scored_sets: list[tuple[float, npt.NDArray[np.float64]]] = []

    for idx_tuple in combinations(range(len(candidates)), GRID_LINE_COUNT):
        idx = np.array(idx_tuple, dtype=np.int32)
        offsets = candidates[idx]
        local_weights = weights[idx]

        spacing = np.diff(offsets)
        mean_spacing = float(np.mean(spacing))
        if mean_spacing <= 1.0:
            continue

        spacing_std = float(np.std(spacing))
        regularity = spacing_std / (mean_spacing + 1e-6)
        span = float(offsets[-1] - offsets[0])
        score = float(np.sum(local_weights)) + (0.15 * span) - (8.0 * regularity)
        scored_sets.append((score, offsets.astype(np.float64)))

    if not scored_sets:
        msg = "Failed to select a stable 4-line grid family."
        raise BoardRecognitionError(msg)

    scored_sets.sort(key=lambda item: item[0], reverse=True)
    return [offsets for _, offsets in scored_sets[:MAX_OFFSET_SET_CANDIDATES]]


def _fit_grid_family_offsets(
    segments: Int32Array,
    direction: float,
    tolerance: float,
) -> list[npt.NDArray[np.float64]]:
    """Estimate top 4-line offset sets for one grid direction."""
    if len(segments) < GRID_LINE_COUNT:
        msg = "Insufficient line support for one grid direction."
        raise BoardRecognitionError(msg)

    normal = np.array([-np.sin(direction), np.cos(direction)], dtype=np.float64)
    midpoints = _segment_midpoints(segments)
    rhos = midpoints @ normal
    weights = _segment_lengths(segments)

    merged_rhos, merged_weights = _merge_rho_candidates(
        rhos, weights, tolerance=tolerance
    )
    return _enumerate_regular_offset_sets(merged_rhos, merged_weights)


def _intersect_lines(
    normal_a: npt.NDArray[np.float64],
    rho_a: float,
    normal_b: npt.NDArray[np.float64],
    rho_b: float,
) -> npt.NDArray[np.float64]:
    matrix = np.array(
        [
            [normal_a[0], normal_a[1]],
            [normal_b[0], normal_b[1]],
        ],
        dtype=np.float64,
    )
    determinant = float(np.linalg.det(matrix))
    if abs(determinant) < 1e-6:
        msg = "Grid lines are near-parallel and intersections are unstable."
        raise BoardRecognitionError(msg)

    rhs = np.array([rho_a, rho_b], dtype=np.float64)
    return np.linalg.solve(matrix, rhs)


def _build_grid_points(
    offsets_a: npt.NDArray[np.float64],
    direction_a: float,
    offsets_b: npt.NDArray[np.float64],
    direction_b: float,
) -> npt.NDArray[np.float64]:
    normal_a = np.array([-np.sin(direction_a), np.cos(direction_a)], dtype=np.float64)
    normal_b = np.array([-np.sin(direction_b), np.cos(direction_b)], dtype=np.float64)

    points = np.zeros((GRID_LINE_COUNT, GRID_LINE_COUNT, 2), dtype=np.float64)
    for i, rho_a in enumerate(offsets_a):
        for j, rho_b in enumerate(offsets_b):
            points[i, j] = _intersect_lines(
                normal_a, float(rho_a), normal_b, float(rho_b)
            )
    return points


def _grid_outer_corners(grid_points: npt.NDArray[np.float64]) -> FloatArray:
    raw_corners = np.array(
        [
            grid_points[0, 0],
            grid_points[-1, 0],
            grid_points[-1, -1],
            grid_points[0, -1],
        ],
        dtype=np.float32,
    )
    return _order_corners(raw_corners)


def _build_grid_overlay(
    frame: UInt8Array,
    segments: Int32Array,
    grid_points: npt.NDArray[np.float64],
) -> UInt8Array:
    overlay: UInt8Array = frame.copy()

    for line in segments:
        x1, y1, x2, y2 = line.tolist()
        cv2.line(overlay, (x1, y1), (x2, y2), (0, 165, 255), 1, cv2.LINE_AA)

    for i in range(GRID_LINE_COUNT):
        row_points = grid_points[i]
        row_poly = np.round(row_points).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(overlay, [row_poly], False, (0, 255, 0), 2, cv2.LINE_AA)

    for j in range(GRID_LINE_COUNT):
        col_points = grid_points[:, j]
        col_poly = np.round(col_points).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(overlay, [col_poly], False, (0, 255, 0), 2, cv2.LINE_AA)

    for point in grid_points.reshape(-1, 2):
        px, py = int(round(float(point[0]))), int(round(float(point[1])))
        cv2.circle(overlay, (px, py), 4, (0, 0, 255), -1, cv2.LINE_AA)

    return overlay


def _expected_vertex_direction_count(row: int, col: int) -> int:
    """Expected number of line directions connected at a grid vertex."""
    edge_hits: int = int(row in (0, GRID_LINE_COUNT - 1)) + int(
        col in (0, GRID_LINE_COUNT - 1)
    )
    if edge_hits == 2:
        return 2
    if edge_hits == 1:
        return 3
    return 4


def _ray_has_line_support(
    mask: UInt8Array,
    origin: npt.NDArray[np.float64],
    direction: npt.NDArray[np.float64],
    max_distance: float,
    step: float,
) -> bool:
    """Check whether a ray from a vertex is supported by foreground pixels."""
    height: int
    width: int
    height, width = mask.shape
    run_length: int = 0
    max_run_length: int = 0
    hit_count: int = 0
    sample_count: int = 0

    distance: float = step * 2.0
    while distance <= max_distance:
        sample_count += 1
        x = float(origin[0] + direction[0] * distance)
        y = float(origin[1] + direction[1] * distance)
        xi: int = int(round(x))
        yi: int = int(round(y))

        if xi < 1 or yi < 1 or xi >= width - 1 or yi >= height - 1:
            break

        patch = mask[yi - 1 : yi + 2, xi - 1 : xi + 2]
        has_foreground: bool = bool(np.any(patch > 0))
        if has_foreground:
            run_length += 1
            hit_count += 1
            if run_length > max_run_length:
                max_run_length = run_length
        else:
            run_length = 0

        distance += step

    if sample_count == 0:
        return False

    return (max_run_length >= 2) or (hit_count >= max(3, sample_count // 3))


def _grid_spacing_metrics(
    grid_points: npt.NDArray[np.float64],
) -> tuple[float, float, float]:
    """Compute grid spacing stats for probing line support and regularity."""
    diff_row = grid_points[1:, :, :] - grid_points[:-1, :, :]
    diff_col = grid_points[:, 1:, :] - grid_points[:, :-1, :]

    row_lengths = np.linalg.norm(diff_row, axis=2)
    col_lengths = np.linalg.norm(diff_col, axis=2)

    mean_row = float(np.mean(row_lengths))
    mean_col = float(np.mean(col_lengths))

    all_lengths = np.concatenate([row_lengths.reshape(-1), col_lengths.reshape(-1)])
    mean_spacing = float(np.mean(all_lengths))
    std_spacing = float(np.std(all_lengths))
    regularity = std_spacing / (mean_spacing + 1e-6)
    return mean_row, mean_col, regularity


def _compute_vertex_direction_support(
    mask: UInt8Array,
    grid_points: npt.NDArray[np.float64],
    direction_a: float,
    direction_b: float,
) -> tuple[npt.NDArray[np.int32], npt.NDArray[np.bool_]]:
    """Count how many line directions reach each grid vertex."""
    mean_row, mean_col, _ = _grid_spacing_metrics(grid_points)
    probe_distance: float = 0.45 * min(mean_row, mean_col)
    probe_step: float = max(1.0, 0.08 * probe_distance)

    vec_a = np.array([np.cos(direction_a), np.sin(direction_a)], dtype=np.float64)
    vec_b = np.array([np.cos(direction_b), np.sin(direction_b)], dtype=np.float64)

    support_flags = np.zeros((GRID_LINE_COUNT, GRID_LINE_COUNT, 4), dtype=bool)
    counts = np.zeros((GRID_LINE_COUNT, GRID_LINE_COUNT), dtype=np.int32)

    for row in range(GRID_LINE_COUNT):
        for col in range(GRID_LINE_COUNT):
            origin = grid_points[row, col]
            ray_dirs = (vec_a, -vec_a, vec_b, -vec_b)
            for idx, ray_dir in enumerate(ray_dirs):
                support_flags[row, col, idx] = _ray_has_line_support(
                    mask,
                    origin,
                    ray_dir,
                    max_distance=probe_distance,
                    step=probe_step,
                )
            counts[row, col] = int(np.count_nonzero(support_flags[row, col]))

    return counts, support_flags


def _score_grid_candidate(
    mask: UInt8Array,
    frame_area: float,
    grid_points: npt.NDArray[np.float64],
    direction_a: float,
    direction_b: float,
) -> tuple[float, FloatArray, npt.NDArray[np.int32], npt.NDArray[np.bool_]]:
    """Score a grid candidate using area, regularity, and vertex direction counts."""
    corners = _grid_outer_corners(grid_points)
    area = float(cv2.contourArea(corners.astype(np.float32)))
    if area < frame_area * 0.05 or area > frame_area * 0.98:
        return (
            -float("inf"),
            corners,
            np.zeros((GRID_LINE_COUNT, GRID_LINE_COUNT), dtype=np.int32),
            np.zeros((GRID_LINE_COUNT, GRID_LINE_COUNT, 4), dtype=bool),
        )

    _, _, regularity = _grid_spacing_metrics(grid_points)
    counts, flags = _compute_vertex_direction_support(
        mask, grid_points, direction_a, direction_b
    )

    direction_error: float = 0.0
    support_total: int = 0
    for row in range(GRID_LINE_COUNT):
        for col in range(GRID_LINE_COUNT):
            expected = _expected_vertex_direction_count(row, col)
            observed = int(counts[row, col])
            direction_error += abs(expected - observed)
            support_total += observed

    area_ratio = area / frame_area
    score = (
        (4.0 * support_total)
        - (15.0 * direction_error)
        - (140.0 * regularity)
        - (10.0 * abs(area_ratio - 0.35))
    )
    return score, corners, counts, flags


def _build_vertex_direction_overlay(
    frame: UInt8Array,
    grid_points: npt.NDArray[np.float64],
    counts: npt.NDArray[np.int32],
    support_flags: npt.NDArray[np.bool_],
    direction_a: float,
    direction_b: float,
) -> UInt8Array:
    """Visualize per-vertex incoming line directions and counted degree."""
    overlay: UInt8Array = frame.copy()
    vec_a = np.array([np.cos(direction_a), np.sin(direction_a)], dtype=np.float64)
    vec_b = np.array([np.cos(direction_b), np.sin(direction_b)], dtype=np.float64)

    mean_row, mean_col, _ = _grid_spacing_metrics(grid_points)
    ray_len: float = max(6.0, 0.22 * min(mean_row, mean_col))

    for row in range(GRID_LINE_COUNT):
        row_poly = np.round(grid_points[row]).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(overlay, [row_poly], False, (60, 200, 60), 1, cv2.LINE_AA)

    for col in range(GRID_LINE_COUNT):
        col_poly = np.round(grid_points[:, col]).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(overlay, [col_poly], False, (60, 200, 60), 1, cv2.LINE_AA)

    for row in range(GRID_LINE_COUNT):
        for col in range(GRID_LINE_COUNT):
            point = grid_points[row, col]
            px = int(round(float(point[0])))
            py = int(round(float(point[1])))

            directions = (vec_a, -vec_a, vec_b, -vec_b)
            for idx, ray in enumerate(directions):
                ex = int(round(float(point[0] + ray[0] * ray_len)))
                ey = int(round(float(point[1] + ray[1] * ray_len)))
                color = (
                    (0, 220, 0) if bool(support_flags[row, col, idx]) else (0, 0, 255)
                )
                cv2.line(overlay, (px, py), (ex, ey), color, 2, cv2.LINE_AA)

            expected = _expected_vertex_direction_count(row, col)
            observed = int(counts[row, col])
            ok = observed == expected
            marker_color = (0, 220, 0) if ok else (0, 0, 255)

            cv2.circle(overlay, (px, py), 4, marker_color, -1, cv2.LINE_AA)
            cv2.putText(
                overlay,
                f"{observed}/{expected}",
                (px + 6, py - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                marker_color,
                1,
                cv2.LINE_AA,
            )

    return overlay


def detect_board_corners(frame: UInt8Array) -> FloatArray:
    """Detect board corners as a 4-point polygon from an input frame."""
    corners, _ = detect_board_corners_with_debug(frame)
    return corners


def detect_board_corners_with_debug(
    frame: UInt8Array,
) -> tuple[FloatArray, BoardDetectionDebug]:
    """Detect board corners via direct 3x3 grid reconstruction."""
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

    segments = _detect_line_segments(cleaned)
    if len(segments) < 8:
        msg: str = "Failed to detect enough board line segments."
        raise BoardRecognitionError(msg)

    direction_a, mask_a, mask_b = _fit_primary_directions(segments)
    direction_b: float = float((direction_a + (np.pi / 2.0)) % np.pi)

    frame_height: int
    frame_width: int
    frame_height, frame_width = frame.shape[:2]
    diagonal: float = float(np.hypot(frame_width, frame_height))
    rho_tolerance: float = max(4.0, 0.015 * diagonal)

    frame_area = float(frame_width * frame_height)
    offset_sets_a = _fit_grid_family_offsets(
        segments[mask_a], direction_a, rho_tolerance
    )
    offset_sets_b = _fit_grid_family_offsets(
        segments[mask_b], direction_b, rho_tolerance
    )

    best_score: float = -float("inf")
    best_grid_points: npt.NDArray[np.float64] | None = None
    best_corners: FloatArray | None = None
    best_counts: npt.NDArray[np.int32] | None = None
    best_flags: npt.NDArray[np.bool_] | None = None

    for offsets_a in offset_sets_a:
        for offsets_b in offset_sets_b:
            candidate_grid = _build_grid_points(
                offsets_a,
                direction_a,
                offsets_b,
                direction_b,
            )
            score, candidate_corners, candidate_counts, candidate_flags = (
                _score_grid_candidate(
                    cleaned,
                    frame_area,
                    candidate_grid,
                    direction_a,
                    direction_b,
                )
            )
            if score > best_score:
                best_score = score
                best_grid_points = candidate_grid
                best_corners = candidate_corners
                best_counts = candidate_counts
                best_flags = candidate_flags

    if (
        best_grid_points is None
        or best_corners is None
        or best_counts is None
        or best_flags is None
        or best_score == -float("inf")
    ):
        msg = "Failed to select a reliable 3x3 grid candidate."
        raise BoardRecognitionError(msg)

    corners = best_corners
    overlay: UInt8Array = _build_grid_overlay(frame, segments, best_grid_points)
    directions_overlay: UInt8Array = _build_vertex_direction_overlay(
        frame,
        best_grid_points,
        best_counts,
        best_flags,
        direction_a,
        direction_b,
    )
    debug = BoardDetectionDebug(
        gray=gray,
        binary=binary,
        cleaned=cleaned,
        contours_overlay=overlay,
        vertex_directions_overlay=directions_overlay,
    )
    return corners, debug


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
    poly: Int32Array = corners.astype(np.int32).reshape(
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
