from __future__ import annotations

import argparse
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
PROJECT_SRC = CURRENT_FILE.parents[1]
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from lib.camera import CameraError, create_roi_config_with_gui


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture full camera image, select ROI, and save ROI config.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CURRENT_FILE.parents[2] / "output" / "camera_roi.txt",
        help="Output ROI config text path.",
    )
    parser.add_argument(
        "--preview",
        type=Path,
        default=CURRENT_FILE.parents[2] / "output" / "camera_full_preview.jpg",
        help="Output full-frame preview image path.",
    )
    parser.add_argument(
        "--warmup-frames",
        type=int,
        default=5,
        help="Number of warmup frames before capture.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        saved = create_roi_config_with_gui(
            roi_config_path=args.config,
            preview_image_path=args.preview,
            warmup_frames=args.warmup_frames,
        )
    except CameraError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"[OK] ROI config saved: {saved}")
    print(f"[OK] Full-frame preview saved: {args.preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
