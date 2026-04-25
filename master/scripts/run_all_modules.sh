#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MASTER_DIR/.." && pwd)"
VISION_DIR="$REPO_ROOT/vision"
ROBOT_DIR="$REPO_ROOT/robot"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"

export MASTER_HOST="$HOST"
export MASTER_PORT="$PORT"
export MASTER_URL="ws://${HOST}:${PORT}"

MASTER_PID=""
VISION_PID=""
ROBOT_PID=""

cleanup() {
  for pid in "$ROBOT_PID" "$VISION_PID" "$MASTER_PID"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  for pid in "$ROBOT_PID" "$VISION_PID" "$MASTER_PID"; do
    if [[ -n "$pid" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

echo "[INFO] HOST=$HOST"
echo "[INFO] PORT=$PORT"
echo "[INFO] MASTER_URL=$MASTER_URL"
echo "[INFO] Starting master module..."
(
  cd "$MASTER_DIR"
  uv run python -m master
) &
MASTER_PID=$!

sleep 1

echo "[INFO] Starting vision module..."
(
  cd "$VISION_DIR"
  uv run python src/main.py
) &
VISION_PID=$!

echo "[INFO] Starting robot module..."
(
  cd "$ROBOT_DIR"
  uv run python main.py
) &
ROBOT_PID=$!

echo "[INFO] Modules started. Agent (Unity) is manual startup."
echo "[INFO] Press Ctrl+C to stop all modules."

wait "$MASTER_PID" "$VISION_PID" "$ROBOT_PID"
