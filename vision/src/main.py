from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import cv2
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from lib.board_recognition import (
    BoardDetectionResult,
    BoardRecognitionError,
    detect_and_rectify_board,
)
from lib.camera import CameraError, capture_one_frame_from_usb
from lib.cell_recognition import (
    CellRecognitionConfig,
    CellRecognitionError,
    load_cell_recognition_config,
    recognize_board_state_from_cells,
)

REQUEST_TYPE = "request_board_state"
RESPONSE_TYPE = "board_state_response"
WS_PATH = "/vision"


class VisionRuntimeError(RuntimeError):
    """Raised when the vision runtime cannot produce a board state."""


@dataclass(frozen=True, slots=True)
class VisionConfig:
    """Runtime configuration for the vision websocket client."""

    master_host: str = "0.0.0.0"
    master_port: int = 8765
    reconnect_delay_sec: float = 1.0
    warmup_frames: int = 5
    roi_config_path: Path = Path("output/camera_roi.txt")
    cell_config_path: Path = Path("output/cell_thresholds.txt")
    capture_output_path: Path = Path("output/runtime/camera_frame_roi_runtime.jpg")

    @property
    def uri(self) -> str:
        return f"ws://{self.master_host}:{self.master_port}{WS_PATH}"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"Environment variable {name} must be int, got {raw!r}."
        raise VisionRuntimeError(msg) from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        msg = f"Environment variable {name} must be float, got {raw!r}."
        raise VisionRuntimeError(msg) from exc


def load_config_from_env() -> VisionConfig:
    """Build runtime configuration from environment variables."""
    return VisionConfig(
        master_host=os.getenv("MASTER_HOST", "0.0.0.0"),
        master_port=_env_int("MASTER_PORT", 8765),
        reconnect_delay_sec=_env_float("VISION_RECONNECT_DELAY", 1.0),
        warmup_frames=_env_int("VISION_WARMUP_FRAMES", 5),
        roi_config_path=Path(os.getenv("VISION_ROI_PATH", "output/camera_roi.txt")),
        cell_config_path=Path(
            os.getenv("VISION_CELL_CONFIG_PATH", "output/cell_thresholds.txt")
        ),
        capture_output_path=Path(
            os.getenv(
                "VISION_CAPTURE_PATH",
                "output/runtime/camera_frame_roi_runtime.jpg",
            )
        ),
    )


def _load_cell_config(path: Path) -> CellRecognitionConfig:
    if path.exists():
        return load_cell_recognition_config(path)
    return CellRecognitionConfig()


def _flatten_board(board: list[list[int]]) -> list[int]:
    flat = [int(cell) for row in board for cell in row]
    if len(flat) != 9:
        msg = f"Recognized board length must be 9, got {len(flat)}."
        raise VisionRuntimeError(msg)
    return flat


def recognize_current_board(config: VisionConfig) -> list[int]:
    """Capture one ROI frame and return row-major board state as length-9 list."""
    roi_path: Path | None = (
        config.roi_config_path if config.roi_config_path.exists() else None
    )
    capture_path = capture_one_frame_from_usb(
        output_path=config.capture_output_path,
        warmup_frames=config.warmup_frames,
        roi_config_path=roi_path,
    )
    frame = cv2.imread(str(capture_path))
    if frame is None:
        msg = f"Failed to read captured frame: {capture_path}"
        raise VisionRuntimeError(msg)

    detection: BoardDetectionResult = detect_and_rectify_board(frame)
    cell_config = _load_cell_config(config.cell_config_path)
    board_2d = recognize_board_state_from_cells(
        frame,
        detection.cells,
        config=cell_config,
    )
    return _flatten_board(board_2d)


async def _handle_request(websocket, config: VisionConfig) -> None:
    async for raw_message in websocket:
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            logging.warning("Received non-JSON message: %s", raw_message)
            continue

        if not isinstance(message, dict):
            logging.warning("Received non-object message: %r", message)
            continue

        message_type = message.get("type")
        if message_type != REQUEST_TYPE:
            logging.info("Ignore unsupported message type: %r", message_type)
            continue

        started = perf_counter()
        try:
            board = recognize_current_board(config)
        except (
            CameraError,
            BoardRecognitionError,
            CellRecognitionError,
            VisionRuntimeError,
        ) as exc:
            logging.warning("Board recognition failed: %s", exc)
            continue

        response = {
            "type": RESPONSE_TYPE,
            "payload": {
                "board": board,
            },
        }
        await websocket.send(json.dumps(response, ensure_ascii=False))
        elapsed_ms = (perf_counter() - started) * 1000.0
        logging.info("Sent board_state_response in %.1f ms: %s", elapsed_ms, board)


async def run_vision_client(config: VisionConfig) -> None:
    """Keep reconnecting to master websocket server and serve requests."""
    while True:
        try:
            logging.info("Connecting to %s", config.uri)
            async with connect(config.uri) as websocket:
                logging.info("Connected to master server")
                await _handle_request(websocket, config)
        except ConnectionClosed as exc:
            logging.warning("Connection closed: %s", exc)
        except OSError as exc:
            logging.warning("Connection failed: %s", exc)

        await asyncio.sleep(config.reconnect_delay_sec)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [vision] %(message)s",
    )
    config = load_config_from_env()
    config.capture_output_path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(run_vision_client(config))


if __name__ == "__main__":
    main()
