#!/usr/bin/env bash
#
# Master + HW Simulator launch script
#
# Usage:
#   bash master/simulator/hw/start.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MASTER_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

MASTER_PORT=8765
HW_PORT=8001
MASTER_PID=""
HW_PID=""

cleanup() {
    [ -n "$HW_PID" ]     && kill "$HW_PID" 2>/dev/null || true
    [ -n "$MASTER_PID" ] && kill "$MASTER_PID" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup EXIT

lsof -ti:$MASTER_PORT | xargs kill -9 2>/dev/null || true
lsof -ti:$HW_PORT     | xargs kill -9 2>/dev/null || true
sleep 1

cd "$MASTER_DIR"

uv run python -m master.main > /tmp/master.log 2>&1 &
MASTER_PID=$!
sleep 3

if ! kill -0 "$MASTER_PID" 2>/dev/null; then
    echo "ERROR: Master failed to start"
    tail -5 /tmp/master.log
    exit 1
fi

uv run uvicorn simulator.hw.main:app --port $HW_PORT > /tmp/hw_sim.log 2>&1 &
HW_PID=$!
sleep 3

if ! kill -0 "$HW_PID" 2>/dev/null; then
    echo "ERROR: HW Simulator failed to start"
    tail -5 /tmp/hw_sim.log
    exit 1
fi

echo "Master:    ws://localhost:$MASTER_PORT"
echo "Simulator: http://localhost:$HW_PORT"

if command -v open &>/dev/null; then
    open "http://localhost:$HW_PORT"
elif command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:$HW_PORT"
fi

tail -f /tmp/master.log /tmp/hw_sim.log 2>/dev/null
