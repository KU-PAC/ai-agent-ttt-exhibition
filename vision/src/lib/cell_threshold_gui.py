from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

try:
    from lib.cell_recognition import (
        BLUE_H_MAX_FIXED,
        CELL_BLUE,
        CELL_EMPTY,
        CELL_RED,
        BoardCellGeometry,
        CellRecognitionConfig,
        CellRecognitionError,
        extract_cell_patch,
        load_cell_recognition_config,
        parse_board_cells_from_file,
        recognize_cell_state,
        save_cell_recognition_config,
    )
except ModuleNotFoundError:
    from cell_recognition import (  # type: ignore[import-not-found]
        BLUE_H_MAX_FIXED,
        CELL_BLUE,
        CELL_EMPTY,
        CELL_RED,
        BoardCellGeometry,
        CellRecognitionConfig,
        CellRecognitionError,
        extract_cell_patch,
        load_cell_recognition_config,
        parse_board_cells_from_file,
        recognize_cell_state,
        save_cell_recognition_config,
    )

CURRENT_FILE = Path(__file__).resolve()

UInt8Array = npt.NDArray[np.uint8]


@dataclass(slots=True)
class SliderBinding:
    key: str
    minimum: int
    maximum: int
    value: int
    slider: QSlider | None = None
    spinbox: QSpinBox | None = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Tune cell-recognition HSV thresholds with a PyQt GUI. "
            "Use Save Config button to persist settings."
        )
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=CURRENT_FILE.parent / "test" / "test_data" / "camera_frame_roi.jpg",
        help="Input image path.",
    )
    parser.add_argument(
        "--board-result",
        type=Path,
        default=CURRENT_FILE.parent
        / "test"
        / "test_data"
        / "08_board_recognition_result.txt",
        help="Optional board-recognition result text for per-cell preview.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CURRENT_FILE.parents[2]
        / "output"
        / "cell_recognition"
        / "cell_thresholds.txt",
        help="Threshold config text file path (key=value).",
    )
    return parser


def _build_bindings(config: CellRecognitionConfig) -> dict[str, SliderBinding]:
    return {
        "color_s_threshold": SliderBinding(
            "color_s_threshold", 0, 255, config.color_s_threshold
        ),
        "blue_h_min": SliderBinding(
            "blue_h_min",
            0,
            BLUE_H_MAX_FIXED,
            config.blue_h_min,
        ),
        "min_ratio_pct": SliderBinding(
            "min_ratio_pct", 0, 100, int(round(config.min_color_ratio * 100.0))
        ),
        "crop_margin_pct": SliderBinding(
            "crop_margin_pct", 0, 45, int(round(config.crop_margin_ratio * 100.0))
        ),
        "cell_warp_size": SliderBinding(
            "cell_warp_size", 3, 300, config.cell_warp_size
        ),
    }


def _load_initial_config(config_path: Path) -> CellRecognitionConfig:
    if config_path.exists():
        return load_cell_recognition_config(config_path)
    config = CellRecognitionConfig()
    save_cell_recognition_config(config_path, config)
    return config


def _numpy_bgr_to_qpixmap(image: UInt8Array) -> QPixmap:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    qimage = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


def _resize_for_panel(image: UInt8Array, side: int = 320) -> UInt8Array:
    return cv2.resize(image, (side, side), interpolation=cv2.INTER_AREA)


def _state_to_label(state: int) -> str:
    if state == CELL_RED:
        return "RED"
    if state == CELL_BLUE:
        return "BLUE"
    if state == CELL_EMPTY:
        return "EMPTY"
    return str(state)


def _build_color_masks(
    source_patch: UInt8Array,
    config: CellRecognitionConfig,
) -> tuple[UInt8Array, UInt8Array]:
    hsv = cv2.cvtColor(source_patch, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    colored = sat >= config.color_s_threshold
    blue_region = np.logical_and(hue >= config.blue_h_min, hue <= BLUE_H_MAX_FIXED)
    blue_mask = np.where(np.logical_and(colored, blue_region), 255, 0).astype(np.uint8)
    red_mask = np.where(
        np.logical_and(colored, np.logical_not(blue_region)), 255, 0
    ).astype(np.uint8)
    return red_mask, blue_mask


def _tile_grid(images: list[UInt8Array], rows: int, cols: int) -> UInt8Array:
    if len(images) != rows * cols:
        msg = f"Expected {rows * cols} images, got {len(images)}."
        raise CellRecognitionError(msg)

    tiled_rows: list[UInt8Array] = []
    for row in range(rows):
        start = row * cols
        end = start + cols
        tiled_rows.append(np.hstack(images[start:end]))
    return np.vstack(tiled_rows)


class ThresholdTunerWindow(QMainWindow):
    def __init__(
        self,
        frame: UInt8Array,
        cells: tuple[BoardCellGeometry, ...] | None,
        config: CellRecognitionConfig,
        config_path: Path,
    ) -> None:
        super().__init__()
        self._frame = frame
        self._cells = cells
        self._config_path = config_path
        self._bindings = _build_bindings(config)

        self.setWindowTitle("Cell Threshold Tuner (PyQt6)")
        self.resize(1500, 940)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        controls_panel = self._build_controls_panel()
        preview_panel = self._build_preview_panel_widgets()

        main_layout.addWidget(controls_panel, 0)
        main_layout.addWidget(preview_panel, 1)

        self._refresh_preview()

    def _build_controls_panel(self) -> QWidget:
        wrapper = QWidget()
        outer_layout = QVBoxLayout(wrapper)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        scroll.setWidget(form_widget)

        for key, binding in self._bindings.items():
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setMinimum(binding.minimum)
            slider.setMaximum(binding.maximum)
            slider.setValue(binding.value)

            spin = QSpinBox()
            spin.setMinimum(binding.minimum)
            spin.setMaximum(binding.maximum)
            spin.setValue(binding.value)

            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            slider.valueChanged.connect(self._refresh_preview)

            row_layout.addWidget(slider, 1)
            row_layout.addWidget(spin, 0)
            form_layout.addRow(QLabel(key), row_widget)

            binding.slider = slider
            binding.spinbox = spin

        mode_text = (
            "9 cells monitored" if self._cells is not None else "full image mode"
        )
        form_layout.addRow(QLabel("monitor_mode"), QLabel(mode_text))

        self._status_label = QLabel("")
        form_layout.addRow(QLabel("status"), self._status_label)

        save_button = QPushButton("Save Config")
        save_button.clicked.connect(self._save_config)
        outer_layout.addWidget(save_button)
        return wrapper

    def _build_preview_panel_widgets(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)

        grid = QGridLayout()
        layout.addLayout(grid)

        self._source_label = QLabel()
        self._red_label = QLabel()
        self._blue_label = QLabel()
        self._overlay_label = QLabel()

        self._source_label.setMinimumSize(320, 320)
        self._red_label.setMinimumSize(320, 320)
        self._blue_label.setMinimumSize(320, 320)
        self._overlay_label.setMinimumSize(320, 320)

        group_source = self._wrap_image("Source", self._source_label)
        group_red = self._wrap_image("Red Mask", self._red_label)
        group_blue = self._wrap_image("Blue Mask", self._blue_label)
        group_overlay = self._wrap_image("Overlay", self._overlay_label)

        grid.addWidget(group_source, 0, 0)
        grid.addWidget(group_red, 0, 1)
        grid.addWidget(group_blue, 1, 0)
        grid.addWidget(group_overlay, 1, 1)

        self._metrics_label = QLabel("")
        layout.addWidget(self._metrics_label)
        return wrapper

    def _wrap_image(self, title: str, label: QLabel) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return box

    def _value(self, key: str) -> int:
        binding = self._bindings[key]
        if binding.spinbox is None:
            return binding.value
        return int(binding.spinbox.value())

    def _current_config(self) -> CellRecognitionConfig:
        return CellRecognitionConfig(
            color_s_threshold=self._value("color_s_threshold"),
            blue_h_min=self._value("blue_h_min"),
            min_color_ratio=float(self._value("min_ratio_pct")) / 100.0,
            crop_margin_ratio=min(float(self._value("crop_margin_pct")) / 100.0, 0.49),
            cell_warp_size=max(3, self._value("cell_warp_size")),
        )

    def _build_single_view(
        self,
        source_patch: UInt8Array,
        config: CellRecognitionConfig,
    ) -> tuple[UInt8Array, UInt8Array, UInt8Array, UInt8Array, str]:
        red_mask, blue_mask = _build_color_masks(source_patch, config)

        overlay = source_patch.copy()
        overlay[red_mask > 0] = (0, 0, 255)
        overlay[blue_mask > 0] = (255, 0, 0)

        source_view = _resize_for_panel(source_patch)
        red_view = cv2.cvtColor(_resize_for_panel(red_mask), cv2.COLOR_GRAY2BGR)
        blue_view = cv2.cvtColor(_resize_for_panel(blue_mask), cv2.COLOR_GRAY2BGR)
        overlay_view = _resize_for_panel(overlay)

        state = recognize_cell_state(source_patch, config)
        red_count = int(cv2.countNonZero(red_mask))
        blue_count = int(cv2.countNonZero(blue_mask))
        metrics = (
            f"state={_state_to_label(state)} red={red_count} blue={blue_count} "
            f"ratio={config.min_color_ratio:.2f} margin={config.crop_margin_ratio:.2f}"
        )
        return source_view, red_view, blue_view, overlay_view, metrics

    def _build_board_view(
        self,
        config: CellRecognitionConfig,
    ) -> tuple[UInt8Array, UInt8Array, UInt8Array, UInt8Array, str]:
        if self._cells is None:
            msg = "Board cells are not available."
            raise CellRecognitionError(msg)

        source_views: list[UInt8Array] = []
        red_views: list[UInt8Array] = []
        blue_views: list[UInt8Array] = []
        overlay_views: list[UInt8Array] = []

        board_state = [[CELL_EMPTY for _ in range(3)] for _ in range(3)]
        red_total = 0
        blue_total = 0

        for cell in self._cells:
            patch = extract_cell_patch(self._frame, cell.corners, config)
            red_mask, blue_mask = _build_color_masks(patch, config)
            state = recognize_cell_state(patch, config)
            board_state[cell.row][cell.col] = state

            red_count = int(cv2.countNonZero(red_mask))
            blue_count = int(cv2.countNonZero(blue_mask))
            red_total += red_count
            blue_total += blue_count

            patch_view = _resize_for_panel(patch, side=140)
            red_view = cv2.cvtColor(
                _resize_for_panel(red_mask, side=140), cv2.COLOR_GRAY2BGR
            )
            blue_view = cv2.cvtColor(
                _resize_for_panel(blue_mask, side=140),
                cv2.COLOR_GRAY2BGR,
            )

            overlay = patch.copy()
            overlay[red_mask > 0] = (0, 0, 255)
            overlay[blue_mask > 0] = (255, 0, 0)
            overlay_view = _resize_for_panel(overlay, side=140)

            label_text = f"r{cell.row}c{cell.col}:{_state_to_label(state)}"
            cv2.putText(
                patch_view,
                label_text,
                (6, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                overlay_view,
                label_text,
                (6, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            source_views.append(patch_view)
            red_views.append(red_view)
            blue_views.append(blue_view)
            overlay_views.append(overlay_view)

        source_grid = _tile_grid(source_views, rows=3, cols=3)
        red_grid = _tile_grid(red_views, rows=3, cols=3)
        blue_grid = _tile_grid(blue_views, rows=3, cols=3)
        overlay_grid = _tile_grid(overlay_views, rows=3, cols=3)

        board_text = "; ".join(f"row{idx}={row}" for idx, row in enumerate(board_state))
        metrics = (
            f"all-cells red_total={red_total} blue_total={blue_total} "
            f"ratio={config.min_color_ratio:.2f} margin={config.crop_margin_ratio:.2f} "
            f"{board_text}"
        )
        return source_grid, red_grid, blue_grid, overlay_grid, metrics

    def _set_preview(self, label: QLabel, image: UInt8Array) -> None:
        pixmap = _numpy_bgr_to_qpixmap(image)
        scaled = pixmap.scaled(
            430,
            430,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)

    def _refresh_preview(self) -> None:
        try:
            config = self._current_config()
            if self._cells is None:
                source_view, red_view, blue_view, overlay_view, metrics = (
                    self._build_single_view(self._frame, config)
                )
            else:
                source_view, red_view, blue_view, overlay_view, metrics = (
                    self._build_board_view(config)
                )

            self._set_preview(self._source_label, source_view)
            self._set_preview(self._red_label, red_view)
            self._set_preview(self._blue_label, blue_view)
            self._set_preview(self._overlay_label, overlay_view)

            self._metrics_label.setText(metrics)
            self._status_label.setText("OK")
        except CellRecognitionError as exc:
            self._status_label.setText(f"Error: {exc}")

    def _save_config(self) -> None:
        try:
            config = self._current_config()
            save_cell_recognition_config(self._config_path, config)
            self._status_label.setText(f"Saved: {self._config_path}")
        except CellRecognitionError as exc:
            self._status_label.setText(f"Save failed: {exc}")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    frame = cv2.imread(str(args.image))
    if frame is None:
        print(f"[ERROR] failed to load image: {args.image}")
        return 1

    cells: tuple[BoardCellGeometry, ...] | None = None
    if args.board_result.exists():
        try:
            cells = parse_board_cells_from_file(args.board_result)
        except CellRecognitionError as exc:
            print(f"[WARN] board-result parse failed: {exc}")

    try:
        config = _load_initial_config(args.config)
    except CellRecognitionError as exc:
        print(f"[ERROR] invalid config file: {exc}")
        return 1

    app = QApplication(sys.argv)
    window = ThresholdTunerWindow(
        frame=frame,
        cells=cells,
        config=config,
        config_path=args.config,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
