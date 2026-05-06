#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROBOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
export MASTER_URL="ws://${HOST}:${PORT}"

cd "$ROBOT_DIR"

CLIENT_PID=""
cleanup() {
  if [[ -n "$CLIENT_PID" ]] && kill -0 "$CLIENT_PID" 2>/dev/null; then
    kill "$CLIENT_PID" 2>/dev/null || true
    wait "$CLIENT_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "[INFO] MASTER_URL=$MASTER_URL"
echo "[INFO] Starting robot client (main.py)..."
uv run python main.py &
CLIENT_PID=$!

# Give the client a moment to start reconnect loop.
sleep 1

echo "[INFO] Starting interactive test server (test_server.py)..."
echo "[INFO] Type 00-08 to send place_piece, 10 for reset, q to quit"
uv run python test_server.py --host "$HOST" --port "$PORT"
