#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.ddev/.env"
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
# shellcheck disable=SC1090
source "$ENV_FILE"
STATE_DIR="$HOME/.coding-platform"
PID_FILE="$STATE_DIR/antigravity-bridge.pid"
LOG_FILE="$STATE_DIR/antigravity-bridge.log"
PORT="${ANTIGRAVITY_BRIDGE_PORT:-8792}"
mkdir -p "$STATE_DIR" "${CODING_WORKSPACES_ROOT}"

running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start() {
  command -v agy >/dev/null 2>&1 || { echo "agy is required on the WSL host." >&2; exit 1; }
  if running; then
    echo "Antigravity bridge already running (pid $(cat "$PID_FILE"))."
    return
  fi
  rm -f "$PID_FILE"
  nohup python3 "$ROOT/scripts/antigravity-bridge.py" \
    --host 0.0.0.0 \
    --port "$PORT" \
    --token "$ANTIGRAVITY_BRIDGE_TOKEN" \
    --workspaces "$CODING_WORKSPACES_ROOT" \
    --agy-bin "$(command -v agy)" \
    >>"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  for _ in $(seq 1 30); do
    if curl -fsS -H "Authorization: Bearer $ANTIGRAVITY_BRIDGE_TOKEN" "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      echo "Antigravity bridge started (pid $(cat "$PID_FILE"))."
      return
    fi
    sleep 0.2
  done
  echo "Antigravity bridge failed to become healthy. See $LOG_FILE" >&2
  exit 1
}

stop() {
  if running; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    for _ in $(seq 1 20); do running || break; sleep 0.1; done
  fi
  rm -f "$PID_FILE"
  echo "Antigravity bridge stopped."
}

status() {
  if running && curl -fsS -H "Authorization: Bearer $ANTIGRAVITY_BRIDGE_TOKEN" "http://127.0.0.1:$PORT/health"; then
    echo
    return 0
  fi
  echo '{"status":"down","service":"antigravity-host-bridge"}'
  return 1
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
