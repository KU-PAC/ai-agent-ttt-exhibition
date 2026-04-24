#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VISION_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-18765}"
export MASTER_HOST="$HOST"
export MASTER_PORT="$PORT"

cd "$VISION_DIR"

if ! uv run python - "$HOST" "$PORT" <<'PY'
from __future__ import annotations

import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
  sock.bind((host, port))
except OSError:
  raise SystemExit(1)
finally:
  sock.close()
PY
then
  echo "[ERROR] Port ${HOST}:${PORT} is already in use."
  echo "[ERROR] Stop the existing server, or run with another port (e.g. PORT=18766 bash scripts/run_vision_test.sh)."
  exit 1
fi

CLIENT_PID=""
cleanup() {
  if [[ -n "$CLIENT_PID" ]] && kill -0 "$CLIENT_PID" 2>/dev/null; then
    kill "$CLIENT_PID" 2>/dev/null || true
    wait "$CLIENT_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "[INFO] MASTER_HOST=$MASTER_HOST"
echo "[INFO] MASTER_PORT=$MASTER_PORT"
echo "[INFO] Starting vision client (src/main.py)..."
uv run python src/main.py &
CLIENT_PID=$!

# Give the client a moment to connect.
sleep 1

echo "[INFO] Starting interactive test server (test_server.py)..."
echo "[INFO] Press Enter to request board state, q to quit"
uv run python test_server.py --host "$HOST" --port "$PORT"
