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
Float64Array = npt.NDArray[np.float64]


class BoardRecognitionError(RuntimeError):
    """Raised when board detection or perspective correction fails."""


@dataclass(frozen=True, slots=True)
class BoardDetectionResult:
    """Result object containing board geometry and corrected board image."""

    corners: FloatArray
    warped: UInt8Array
    cells: tuple["BoardCell", ...]


@dataclass(frozen=True, slots=True)
class BoardCell:
    """Single board square geometry in row-major order."""

    row: int
    col: int
    corners: FloatArray
    center: FloatArray


@dataclass(frozen=True, slots=True)
class BoardDetectionDebug:
    """Intermediate images from the board detection pipeline."""

    gray: UInt8Array
    binary: UInt8Array
    cleaned: UInt8Array
    line_support_mask: UInt8Array
    contours_overlay: UInt8Array
    vertex_directions_overlay: UInt8Array


DEFAULT_WARP_WIDTH: Final[int] = 300
DEFAULT_WARP_HEIGHT: Final[int] = 300
QUAD_VERTEX_COUNT: Final[int] = 4
GRID_LINE_COUNT: Final[int] = 4
MAX_OFFSET_CANDIDATE_LINES: Final[int] = 10
MAX_OFFSET_SET_CANDIDATES: Final[int] = 12


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


def _segment_lengths(segments: Int32Array) -> Float64Array:
    delta = segments[:, 2:4].astype(np.float64) - segments[:, 0:2].astype(np.float64)
    return np.hypot(delta[:, 0], delta[:, 1])


def _detect_line_segments(mask: UInt8Array) -> Int32Array:
    """Detect candidate board line segments from a binary mask."""
    frame_height: int
    frame_width: int
    frame_height, frame_width = mask.shape
    base: int = min(frame_width, frame_height)

    threshold: int = max(24, int(base * 0.07))
    min_line_length: int = max(20, int(base * 0.12))
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


def _build_line_support_mask(
    shape: tuple[int, int], segments: Int32Array
) -> UInt8Array:
    """Rasterize detected line segments to a mask used for ray support checks."""
    support_mask = np.zeros(shape, dtype=np.uint8)
    if len(segments) == 0:
        return support_mask

    height, width = shape
    base = min(height, width)

    line_thickness = max(1, int(round(base * 0.006)))
    for x1, y1, x2, y2 in segments.tolist():
        cv2.line(
            support_mask,
            (x1, y1),
            (x2, y2),
            255,
            line_thickness,
            cv2.LINE_AA,
        )

    kernel_size = max(3, int(round(base * 0.012)))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
    return cv2.dilate(support_mask, kernel, iterations=1)


def _select_support_segments(
    segments: Int32Array,
    family_mask_a: npt.NDArray[np.bool_],
    family_mask_b: npt.NDArray[np.bool_],
) -> Int32Array:
    """Select stable line segments for support-mask rasterization.

    The mask should favor long, dominant board-line segments and suppress
    short arc fragments from piece contours.
    """

    selected_families: list[Int32Array] = []
    for family_mask in (family_mask_a, family_mask_b):
        family_segments = segments[family_mask]
        if len(family_segments) == 0:
            continue

        lengths = _segment_lengths(family_segments)
        if len(family_segments) <= GRID_LINE_COUNT:
            selected_families.append(family_segments)
            continue

        percentile_floor = float(np.percentile(lengths, 55.0))
        relative_floor = float(np.max(lengths) * 0.35)
        length_floor = max(percentile_floor, relative_floor)
        keep = lengths >= length_floor

        # Keep at least 4 lines per family to preserve grid support.
        if int(np.count_nonzero(keep)) < GRID_LINE_COUNT:
            top_idx = np.argsort(lengths)[-GRID_LINE_COUNT:]
            keep = np.zeros(len(family_segments), dtype=bool)
            keep[top_idx] = True

        selected = family_segments[keep]
        if len(selected) > 24:
            selected_lengths = _segment_lengths(selected)
            top_idx = np.argsort(selected_lengths)[-24:]
            selected = selected[top_idx]

        selected_families.append(selected)

    if not selected_families:
        return segments

    selected_segments = np.concatenate(selected_families, axis=0).astype(np.int32)
    if len(selected_segments) < 8:
        return segments
    return selected_segments


def _segment_to_line(segment: npt.NDArray[np.int32]) -> Float64Array:
    """Convert segment endpoints to normalized homogeneous line ax+by+c=0."""
    x1, y1, x2, y2 = [float(v) for v in segment.tolist()]
    p1 = np.array([x1, y1, 1.0], dtype=np.float64)
    p2 = np.array([x2, y2, 1.0], dtype=np.float64)
    line = np.cross(p1, p2)
    norm = float(np.hypot(line[0], line[1]))
    if norm <= 1e-9:
        return np.array([0.0, 0.0, 0.0], dtype=np.float64)
    return line / norm


def _build_family_lines(segments: Int32Array) -> tuple[Float64Array, Float64Array]:
    lines = np.array([_segment_to_line(seg) for seg in segments], dtype=np.float64)
    valid = np.linalg.norm(lines[:, :2], axis=1) > 1e-9
    return lines[valid], _segment_lengths(segments)[valid]


def _cluster_segment_families(
    segments: Int32Array,
) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_]]:
    """Split line segments into 2 directional families without orthogonality assumption."""
    if len(segments) < 8:
        msg: str = "Insufficient line segments for directional clustering."
        raise BoardRecognitionError(msg)

    dx = segments[:, 2].astype(np.float64) - segments[:, 0].astype(np.float64)
    dy = segments[:, 3].astype(np.float64) - segments[:, 1].astype(np.float64)
    lengths = np.hypot(dx, dy)
    valid = lengths > 1e-6
    if int(np.count_nonzero(valid)) < 8:
        msg = "Too few valid line segments for directional clustering."
        raise BoardRecognitionError(msg)

    dx = dx[valid]
    dy = dy[valid]
    lengths = lengths[valid]

    angles = np.mod(np.arctan2(dy, dx), np.pi)
    features = np.column_stack([np.cos(2.0 * angles), np.sin(2.0 * angles)]).astype(
        np.float32
    )

    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        1e-4,
    )
    _compactness, labels, _centers = cv2.kmeans(
        features,
        2,
        None,
        criteria,
        8,
        cv2.KMEANS_PP_CENTERS,
    )

    labels_flat = labels.reshape(-1)
    support0 = float(np.sum(lengths[labels_flat == 0]))
    support1 = float(np.sum(lengths[labels_flat == 1]))
    total = support0 + support1
    if total <= 0.0 or min(support0, support1) < total * 0.15:
        msg = "Directional clustering produced a degenerate split."
        raise BoardRecognitionError(msg)

    mask_a = np.zeros(len(segments), dtype=bool)
    valid_indices = np.where(valid)[0]
    mask_a[valid_indices[labels_flat == 0]] = True

    mask_b = np.zeros(len(segments), dtype=bool)
    mask_b[valid_indices[labels_flat == 1]] = True
    return mask_a, mask_b


def _fit_vanishing_point(lines: Float64Array, weights: Float64Array) -> Float64Array:
    """Estimate vanishing point by weighted least-squares from homogeneous lines."""
    if len(lines) < 2:
        msg: str = "Insufficient lines to estimate vanishing point."
        raise BoardRecognitionError(msg)

    sqrt_w = np.sqrt(np.maximum(weights, 1e-6)).reshape(-1, 1)
    a = lines[:, :2] * sqrt_w
    b = (-lines[:, 2:3]) * sqrt_w

    solution, residuals, rank, _ = np.linalg.lstsq(a, b, rcond=None)
    if rank < 2:
        msg = "Vanishing point estimation is numerically unstable."
        raise BoardRecognitionError(msg)

    vp_xy = solution.reshape(-1)
    vp = np.array([float(vp_xy[0]), float(vp_xy[1]), 1.0], dtype=np.float64)

    if residuals.size > 0:
        mse = float(residuals[0] / max(len(lines), 1))
        if not np.isfinite(mse):
            msg = "Vanishing point fit residual is not finite."
            raise BoardRecognitionError(msg)

    return vp


def _line_intersection(line_a: Float64Array, line_b: Float64Array) -> Float64Array:
    point = np.cross(line_a, line_b)
    if abs(float(point[2])) < 1e-8:
        msg = "Line intersection is at infinity and cannot be used for grid vertices."
        raise BoardRecognitionError(msg)
    return np.array([point[0] / point[2], point[1] / point[2]], dtype=np.float64)


def _line_through_points(p1: Float64Array, p2: Float64Array) -> Float64Array:
    line = np.cross(
        np.array([p1[0], p1[1], 1.0], dtype=np.float64),
        np.array([p2[0], p2[1], 1.0], dtype=np.float64),
    )
    norm = float(np.hypot(line[0], line[1]))
    if norm <= 1e-9:
        msg: str = "Failed to build reference line for line-family ordering."
        raise BoardRecognitionError(msg)
    return line / norm


def _project_line_parameter(
    line: Float64Array,
    reference_line: Float64Array,
    ref_origin: Float64Array,
    ref_dir: Float64Array,
) -> float | None:
    try:
        point = _line_intersection(line, reference_line)
    except BoardRecognitionError:
        return None
    return float(np.dot(point - ref_origin, ref_dir))


def _merge_parameterized_lines(
    params: Float64Array,
    lines: Float64Array,
    weights: Float64Array,
    tolerance: float,
) -> tuple[Float64Array, Float64Array, Float64Array]:
    """Merge close family-line candidates in 1D parameter space."""
    if len(params) == 0:
        return (
            np.empty(0, dtype=np.float64),
            np.empty((0, 3), dtype=np.float64),
            np.empty(0, dtype=np.float64),
        )

    order = np.argsort(params)
    p_sorted = params[order]
    l_sorted = lines[order]
    w_sorted = weights[order]

    merged_params: list[float] = []
    merged_lines: list[Float64Array] = []
    merged_weights: list[float] = []

    block_idx: list[int] = [0]
    for idx in range(1, len(p_sorted)):
        if abs(float(p_sorted[idx] - p_sorted[block_idx[-1]])) <= tolerance:
            block_idx.append(idx)
            continue

        block_w = w_sorted[block_idx]
        block_p = p_sorted[block_idx]
        representative = block_idx[int(np.argmax(block_w))]

        merged_params.append(float(np.average(block_p, weights=block_w)))
        merged_lines.append(l_sorted[representative].copy())
        merged_weights.append(float(np.sum(block_w)))

        block_idx = [idx]

    block_w = w_sorted[block_idx]
    block_p = p_sorted[block_idx]
    representative = block_idx[int(np.argmax(block_w))]
    merged_params.append(float(np.average(block_p, weights=block_w)))
    merged_lines.append(l_sorted[representative].copy())
    merged_weights.append(float(np.sum(block_w)))

    return (
        np.array(merged_params, dtype=np.float64),
        np.array(merged_lines, dtype=np.float64),
        np.array(merged_weights, dtype=np.float64),
    )


def _enumerate_four_line_sets(
    params: Float64Array,
    lines: Float64Array,
    weights: Float64Array,
) -> list[Float64Array]:
    """Enumerate top line quadruples with regular spacing in parameter space."""
    if len(params) < GRID_LINE_COUNT:
        msg = "Failed to find enough ordered grid-line candidates."
        raise BoardRecognitionError(msg)

    if len(params) > MAX_OFFSET_CANDIDATE_LINES:
        top = np.argsort(weights)[-MAX_OFFSET_CANDIDATE_LINES:]
        params = params[top]
        lines = lines[top]
        weights = weights[top]

    order = np.argsort(params)
    params = params[order]
    lines = lines[order]
    weights = weights[order]

    scored: list[tuple[float, Float64Array]] = []
    for idx_tuple in combinations(range(len(params)), GRID_LINE_COUNT):
        idx = np.array(idx_tuple, dtype=np.int32)
        p = params[idx]
        local_w = weights[idx]

        spacing = np.diff(p)
        mean_spacing = float(np.mean(spacing))
        if mean_spacing <= 1.0:
            continue

        regularity = float(np.std(spacing)) / (mean_spacing + 1e-6)
        span = float(p[-1] - p[0])
        score = float(np.sum(local_w)) + (0.1 * span) - (6.0 * regularity)
        scored.append((score, lines[idx]))

    if not scored:
        msg = "Failed to form 4-line grid candidates from line family."
        raise BoardRecognitionError(msg)

    scored.sort(key=lambda item: item[0], reverse=True)
    return [line_set for _, line_set in scored[:MAX_OFFSET_SET_CANDIDATES]]


def _build_line_family_candidates(
    family_lines: Float64Array,
    family_weights: Float64Array,
    opposite_vp: Float64Array,
    frame_center: Float64Array,
    tolerance: float,
) -> list[Float64Array]:
    """Create ordered 4-line candidates for one vanishing-point family."""
    if len(family_lines) < GRID_LINE_COUNT:
        msg = "Insufficient line support for one grid direction."
        raise BoardRecognitionError(msg)

    vp_xy = opposite_vp[:2]
    center_to_vp = vp_xy - frame_center
    if float(np.hypot(center_to_vp[0], center_to_vp[1])) < 1e-6:
        center_to_vp = np.array([1.0, 0.0], dtype=np.float64)

    reference_line = _line_through_points(frame_center, frame_center + center_to_vp)
    ref_dir = np.array([-reference_line[1], reference_line[0]], dtype=np.float64)
    ref_norm = float(np.hypot(ref_dir[0], ref_dir[1]))
    ref_dir = ref_dir / max(ref_norm, 1e-9)

    params: list[float] = []
    selected_lines: list[Float64Array] = []
    selected_weights: list[float] = []

    for line, weight in zip(family_lines, family_weights, strict=False):
        parameter = _project_line_parameter(line, reference_line, frame_center, ref_dir)
        if parameter is None:
            continue
        params.append(parameter)
        selected_lines.append(line)
        selected_weights.append(float(weight))

    if len(params) < GRID_LINE_COUNT:
        msg = "Failed to parameterize enough lines in one family."
        raise BoardRecognitionError(msg)

    merged_params, merged_lines, merged_weights = _merge_parameterized_lines(
        np.array(params, dtype=np.float64),
        np.array(selected_lines, dtype=np.float64),
        np.array(selected_weights, dtype=np.float64),
        tolerance=tolerance,
    )
    return _enumerate_four_line_sets(merged_params, merged_lines, merged_weights)


def _build_grid_points(lines_a: Float64Array, lines_b: Float64Array) -> Float64Array:
    points = np.zeros((GRID_LINE_COUNT, GRID_LINE_COUNT, 2), dtype=np.float64)
    for i in range(GRID_LINE_COUNT):
        for j in range(GRID_LINE_COUNT):
            points[i, j] = _line_intersection(lines_a[i], lines_b[j])
    return points


def _grid_outer_corners(grid_points: Float64Array) -> FloatArray:
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


def _canonicalize_grid_points(grid_points: Float64Array) -> Float64Array:
    """Orient a 4x4 vertex grid to top-left -> bottom-right row-major form."""
    if grid_points.shape != (GRID_LINE_COUNT, GRID_LINE_COUNT, 2):
        msg = f"Unexpected grid shape: {grid_points.shape}."
        raise BoardRecognitionError(msg)

    transposed = np.transpose(grid_points, (1, 0, 2))
    candidates = [
        grid_points,
        np.flip(grid_points, axis=0),
        np.flip(grid_points, axis=1),
        np.flip(np.flip(grid_points, axis=0), axis=1),
        transposed,
        np.flip(transposed, axis=0),
        np.flip(transposed, axis=1),
        np.flip(np.flip(transposed, axis=0), axis=1),
    ]

    best_error: float = float("inf")
    best_grid: Float64Array | None = None
    for candidate in candidates:
        corners_seq = np.array(
            [
                candidate[0, 0],
                candidate[0, -1],
                candidate[-1, -1],
                candidate[-1, 0],
            ],
            dtype=np.float32,
        )
        ordered = _order_corners(corners_seq)
        error = float(np.sum(np.linalg.norm(corners_seq - ordered, axis=1)))
        if error < best_error:
            best_error = error
            best_grid = candidate

    if best_grid is None:
        msg = "Failed to orient board grid points."
        raise BoardRecognitionError(msg)

    return np.array(best_grid, dtype=np.float64)


def _build_board_cells(grid_points: Float64Array) -> tuple[BoardCell, ...]:
    """Build row-major 3x3 square geometry from a 4x4 vertex grid."""
    canonical = _canonicalize_grid_points(grid_points)
    cells: list[BoardCell] = []

    for row in range(GRID_LINE_COUNT - 1):
        for col in range(GRID_LINE_COUNT - 1):
            corners = np.array(
                [
                    canonical[row, col],
                    canonical[row, col + 1],
                    canonical[row + 1, col + 1],
                    canonical[row + 1, col],
                ],
                dtype=np.float32,
            )
            center = np.mean(corners, axis=0).astype(np.float32)
            cells.append(BoardCell(row=row, col=col, corners=corners, center=center))

    return tuple(cells)


def _build_grid_overlay(
    frame: UInt8Array,
    segments: Int32Array,
    grid_points: Float64Array,
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
    origin: Float64Array,
    direction: Float64Array,
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


def _grid_spacing_metrics(grid_points: Float64Array) -> tuple[float, float, float]:
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


def _normalized_direction(
    from_point: Float64Array, to_point: Float64Array
) -> Float64Array:
    vec = to_point - from_point
    norm = float(np.hypot(vec[0], vec[1]))
    if norm <= 1e-6:
        return np.array([1.0, 0.0], dtype=np.float64)
    return vec / norm


def _compute_vertex_direction_support(
    mask: UInt8Array,
    grid_points: Float64Array,
    vp_a: Float64Array,
    vp_b: Float64Array,
) -> tuple[Int32Array, npt.NDArray[np.bool_]]:
    """Count how many line directions reach each grid vertex using local VP rays."""
    mean_row, mean_col, _ = _grid_spacing_metrics(grid_points)
    probe_distance: float = 0.45 * min(mean_row, mean_col)
    probe_step: float = max(1.0, 0.08 * probe_distance)

    support_flags = np.zeros((GRID_LINE_COUNT, GRID_LINE_COUNT, 4), dtype=bool)
    counts = np.zeros((GRID_LINE_COUNT, GRID_LINE_COUNT), dtype=np.int32)

    for row in range(GRID_LINE_COUNT):
        for col in range(GRID_LINE_COUNT):
            origin = grid_points[row, col]
            dir_a = _normalized_direction(origin, vp_a[:2])
            dir_b = _normalized_direction(origin, vp_b[:2])
            ray_dirs = (dir_a, -dir_a, dir_b, -dir_b)
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
    grid_points: Float64Array,
    vp_a: Float64Array,
    vp_b: Float64Array,
) -> tuple[float, FloatArray, Int32Array, npt.NDArray[np.bool_]]:
    """Score candidate grid by geometry and per-vertex direction support."""
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
    counts, flags = _compute_vertex_direction_support(mask, grid_points, vp_a, vp_b)

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
        - (8.0 * abs(area_ratio - 0.35))
    )
    return score, corners, counts, flags


def _draw_vanishing_point(
    overlay: UInt8Array,
    vp: Float64Array,
    color: tuple[int, int, int],
) -> None:
    x = int(round(float(vp[0])))
    y = int(round(float(vp[1])))
    height, width = overlay.shape[:2]

    inside = 0 <= x < width and 0 <= y < height
    if inside:
        cv2.circle(overlay, (x, y), 8, color, 2, cv2.LINE_AA)
        return

    cx = width * 0.5
    cy = height * 0.5
    dx = float(vp[0] - cx)
    dy = float(vp[1] - cy)
    norm = float(np.hypot(dx, dy))
    if norm <= 1e-6:
        return

    scale = min(width, height) * 0.45 / norm
    ex = int(round(cx + dx * scale))
    ey = int(round(cy + dy * scale))
    cv2.circle(overlay, (ex, ey), 6, color, 2, cv2.LINE_AA)
    cv2.line(
        overlay,
        (int(round(cx)), int(round(cy))),
        (ex, ey),
        color,
        1,
        cv2.LINE_AA,
    )


def _build_vertex_direction_overlay(
    frame: UInt8Array,
    grid_points: Float64Array,
    counts: Int32Array,
    support_flags: npt.NDArray[np.bool_],
    vp_a: Float64Array,
    vp_b: Float64Array,
) -> UInt8Array:
    """Visualize per-vertex incoming line directions and counted degree."""
    overlay: UInt8Array = frame.copy()

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

            dir_a = _normalized_direction(point, vp_a[:2])
            dir_b = _normalized_direction(point, vp_b[:2])
            directions = (dir_a, -dir_a, dir_b, -dir_b)
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

    _draw_vanishing_point(overlay, vp_a, (255, 120, 0))
    _draw_vanishing_point(overlay, vp_b, (255, 120, 0))
    return overlay


def detect_board_corners(frame: UInt8Array) -> FloatArray:
    """Detect board corners as a 4-point polygon from an input frame."""
    corners, _ = detect_board_corners_with_debug(frame)
    return corners


def _detect_board_geometry_with_debug(
    frame: UInt8Array,
) -> tuple[FloatArray, Float64Array, BoardDetectionDebug]:
    """Detect board corners and full grid vertices with debug artifacts."""
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

    raw_mask_a, raw_mask_b = _cluster_segment_families(segments)

    support_segments = _select_support_segments(segments, raw_mask_a, raw_mask_b)
    line_support_mask = _build_line_support_mask(cleaned.shape, support_segments)

    mask_a, mask_b = _cluster_segment_families(support_segments)
    lines_a, weights_a = _build_family_lines(support_segments[mask_a])
    lines_b, weights_b = _build_family_lines(support_segments[mask_b])

    if len(lines_a) < GRID_LINE_COUNT or len(lines_b) < GRID_LINE_COUNT:
        msg = "Insufficient reliable lines after directional clustering."
        raise BoardRecognitionError(msg)

    vp_a = _fit_vanishing_point(lines_a, weights_a)
    vp_b = _fit_vanishing_point(lines_b, weights_b)

    frame_height: int
    frame_width: int
    frame_height, frame_width = frame.shape[:2]
    frame_area = float(frame_width * frame_height)
    frame_center = np.array([frame_width * 0.5, frame_height * 0.5], dtype=np.float64)

    diagonal: float = float(np.hypot(frame_width, frame_height))
    family_tolerance: float = max(4.0, 0.02 * diagonal)

    line_sets_a = _build_line_family_candidates(
        lines_a,
        weights_a,
        opposite_vp=vp_b,
        frame_center=frame_center,
        tolerance=family_tolerance,
    )
    line_sets_b = _build_line_family_candidates(
        lines_b,
        weights_b,
        opposite_vp=vp_a,
        frame_center=frame_center,
        tolerance=family_tolerance,
    )

    best_score: float = -float("inf")
    best_grid_points: Float64Array | None = None
    best_corners: FloatArray | None = None
    best_counts: Int32Array | None = None
    best_flags: npt.NDArray[np.bool_] | None = None

    for lines4_a in line_sets_a:
        for lines4_b in line_sets_b:
            try:
                candidate_grid = _build_grid_points(lines4_a, lines4_b)
            except BoardRecognitionError:
                continue

            score, candidate_corners, candidate_counts, candidate_flags = (
                _score_grid_candidate(
                    line_support_mask,
                    frame_area,
                    candidate_grid,
                    vp_a,
                    vp_b,
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

    overlay: UInt8Array = _build_grid_overlay(frame, segments, best_grid_points)
    directions_overlay: UInt8Array = _build_vertex_direction_overlay(
        frame,
        best_grid_points,
        best_counts,
        best_flags,
        vp_a,
        vp_b,
    )
    debug = BoardDetectionDebug(
        gray=gray,
        binary=binary,
        cleaned=cleaned,
        line_support_mask=line_support_mask,
        contours_overlay=overlay,
        vertex_directions_overlay=directions_overlay,
    )
    return best_corners, best_grid_points, debug


def detect_board_corners_with_debug(
    frame: UInt8Array,
) -> tuple[FloatArray, BoardDetectionDebug]:
    """Detect board corners via VP-aware 3x3 grid reconstruction."""
    corners, _grid_points, debug = _detect_board_geometry_with_debug(frame)
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
    corners, grid_points, _debug = _detect_board_geometry_with_debug(frame)
    warped: UInt8Array = rectify_board_image(frame, corners, width=width, height=height)
    cells = _build_board_cells(grid_points)
    return BoardDetectionResult(corners=corners, warped=warped, cells=cells)


def detect_and_rectify_board_with_debug(
    frame: UInt8Array,
    width: int = DEFAULT_WARP_WIDTH,
    height: int = DEFAULT_WARP_HEIGHT,
) -> tuple[BoardDetectionResult, BoardDetectionDebug]:
    """Detect board and return both corrected image and pipeline debug images."""
    corners, grid_points, debug = _detect_board_geometry_with_debug(frame)
    warped: UInt8Array = rectify_board_image(frame, corners, width=width, height=height)
    cells = _build_board_cells(grid_points)
    return BoardDetectionResult(corners=corners, warped=warped, cells=cells), debug


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
