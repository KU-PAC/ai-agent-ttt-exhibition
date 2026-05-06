#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MASTER_DIR/.." && pwd)"
VISION_DIR="$REPO_ROOT/vision"
ROBOT_DIR="$REPO_ROOT/robot"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
POLL_INTERVAL="${MASTER_POLL_INTERVAL:-1.5}"
VISION_MAX_RETRIES="${MASTER_VISION_MAX_RETRIES:-5}"

export MASTER_HOST="$HOST"
export MASTER_PORT="$PORT"
export MASTER_URL="ws://${HOST}:${PORT}"
export MASTER_POLL_INTERVAL="$POLL_INTERVAL"
export MASTER_VISION_MAX_RETRIES="$VISION_MAX_RETRIES"

MASTER_PID=""
VISION_PID=""
ROBOT_PID=""
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-30}"

wait_for_master_ready() {
  local elapsed=0
  while (( elapsed < STARTUP_TIMEOUT )); do
    if [[ -n "$MASTER_PID" ]] && ! kill -0 "$MASTER_PID" 2>/dev/null; then
      echo "[ERROR] Master process exited before becoming ready."
      return 1
    fi

    if ss -ltn "( sport = :$PORT )" 2>/dev/null | awk 'NR>1 {found=1} END {exit !found}'; then
      echo "[INFO] Master is ready on ws://${HOST}:${PORT}"
      return 0
    fi

    sleep 1
    ((elapsed += 1))
  done

  echo "[ERROR] Timed out waiting for master to listen on ${HOST}:${PORT}"
  return 1
}

cleanup() {
  stop_process_group() {
    local leader_pid="$1"
    if [[ -z "$leader_pid" ]]; then
      return 0
    fi

    # Terminate the whole process group to avoid orphaned child processes.
    kill -TERM -- "-$leader_pid" 2>/dev/null || true
    sleep 1
    kill -KILL -- "-$leader_pid" 2>/dev/null || true
  }

  for pid in "$ROBOT_PID" "$VISION_PID" "$MASTER_PID"; do
    stop_process_group "$pid"
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
echo "[INFO] MASTER_POLL_INTERVAL=$MASTER_POLL_INTERVAL"
echo "[INFO] MASTER_VISION_MAX_RETRIES=$MASTER_VISION_MAX_RETRIES"
echo "[INFO] Starting master module..."
setsid bash -c "cd \"$MASTER_DIR\" && exec uv run python -m master" &
MASTER_PID=$!

wait_for_master_ready

echo "[INFO] Starting vision module..."
setsid bash -c "cd \"$VISION_DIR\" && exec uv run python src/main.py" &
VISION_PID=$!

echo "[INFO] Starting robot module..."
setsid bash -c "cd \"$ROBOT_DIR\" && exec uv run python main.py" &
ROBOT_PID=$!

echo "[INFO] Starting control module..."
echo "[INFO] Modules started. Agent (Unity) is manual startup."
echo "[INFO] Control client started. Press Enter in this terminal to send start/reset alternately."
echo "[INFO] Press Ctrl+C to stop all modules."

cd "$MASTER_DIR"
uv run python scripts/control_client.py

