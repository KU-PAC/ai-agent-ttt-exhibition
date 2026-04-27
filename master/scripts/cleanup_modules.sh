#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MASTER_DIR/.." && pwd)"
VISION_DIR="$REPO_ROOT/vision"
ROBOT_DIR="$REPO_ROOT/robot"

PORT="${PORT:-8765}"
GRACE_SECONDS="${GRACE_SECONDS:-2}"
DRY_RUN="${DRY_RUN:-0}"

log() {
  echo "[CLEANUP] $*"
}

is_target_process() {
  local pid="$1"
  local cmdline
  local cwd

  cmdline="$(tr '\0' ' ' </proc/"$pid"/cmdline 2>/dev/null || true)"
  cwd="$(readlink /proc/"$pid"/cwd 2>/dev/null || true)"

  # Match the known module launch commands from this repository.
  case "$cmdline" in
    *"uv run python -m master"*|*"python -m master"*)
      [[ "$cwd" == "$MASTER_DIR" ]] && return 0
      ;;
    *"uv run python src/main.py"*|*"python src/main.py"*)
      [[ "$cwd" == "$VISION_DIR" ]] && return 0
      ;;
    *"uv run python main.py"*|*"python main.py"*)
      [[ "$cwd" == "$ROBOT_DIR" ]] && return 0
      ;;
  esac

  return 1
}

collect_target_pgids() {
  declare -A pgids=()
  local pid
  local pgid

  while read -r pid; do
    [[ -n "$pid" ]] || continue
    [[ -d /proc/"$pid" ]] || continue

    if is_target_process "$pid"; then
      pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
      [[ -n "$pgid" ]] && pgids["$pgid"]=1
    fi
  done < <(ps -eo pid=)

  # Also include any process listening on the target port.
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
    [[ -n "$pgid" ]] && pgids["$pgid"]=1
  done < <(
    ss -ltnp 2>/dev/null \
      | awk -v port=":$PORT" '$4 ~ port {print $NF}' \
      | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
      | sort -u
  )

  for pgid in "${!pgids[@]}"; do
    echo "$pgid"
  done
}

terminate_groups() {
  local signal="$1"
  shift
  local pgid

  for pgid in "$@"; do
    if [[ "$DRY_RUN" == "1" ]]; then
      log "DRY_RUN: kill -$signal -- -$pgid"
      continue
    fi
    kill "-$signal" -- "-$pgid" 2>/dev/null || true
  done
}

main() {
  mapfile -t target_pgids < <(collect_target_pgids | sort -u)

  if (( ${#target_pgids[@]} == 0 )); then
    log "No target process groups found."
    exit 0
  fi

  log "Target process groups: ${target_pgids[*]}"
  terminate_groups TERM "${target_pgids[@]}"

  if [[ "$DRY_RUN" == "1" ]]; then
    exit 0
  fi

  sleep "$GRACE_SECONDS"

  mapfile -t remaining_pgids < <(
    for pgid in "${target_pgids[@]}"; do
      if ps -eo pgid= | awk '{gsub(/^[ \t]+|[ \t]+$/, "", $0); if ($0 == target) found=1} END {exit !found}' target="$pgid"; then
        echo "$pgid"
      fi
    done | sort -u
  )

  if (( ${#remaining_pgids[@]} > 0 )); then
    log "Still running after TERM; sending KILL to groups: ${remaining_pgids[*]}"
    terminate_groups KILL "${remaining_pgids[@]}"
  fi

  if ss -ltnp 2>/dev/null | grep -q ":$PORT"; then
    log "Port $PORT is still in use after cleanup."
    exit 1
  fi

  log "Cleanup completed. Port $PORT is free."
}

main "$@"
