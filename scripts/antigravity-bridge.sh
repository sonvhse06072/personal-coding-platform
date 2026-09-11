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
AGY_SETTINGS="$HOME/.gemini/antigravity-cli/settings.json"
AGY_SETTINGS_BACKUP="$STATE_DIR/antigravity-settings.before-platform.json"
mkdir -p "$STATE_DIR" "${CODING_WORKSPACES_ROOT}" "$(dirname "$AGY_SETTINGS")"

running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

configure_safe_settings() {
  if [[ -f "$AGY_SETTINGS" && ! -f "$AGY_SETTINGS_BACKUP" ]]; then
    cp -a "$AGY_SETTINGS" "$AGY_SETTINGS_BACKUP"
  fi
  python3 - "$AGY_SETTINGS" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
except (json.JSONDecodeError, OSError) as exc:
    raise SystemExit(f"Cannot read Antigravity settings {path}: {exc}")
if not isinstance(data, dict):
    raise SystemExit(f"Antigravity settings must contain a JSON object: {path}")

# Official Antigravity CLI safety controls. Sandboxed terminal commands may run
# autonomously; anything needing to escape the sandbox is not auto-approved.
data["enableTerminalSandbox"] = True
data["toolPermission"] = "proceed-in-sandbox"
data["allowNonWorkspaceAccess"] = False
# Individual-plan privacy is user-controlled rather than an Enterprise contract.
# The platform therefore enforces the available data-collection opt-out locally.
data["enableTelemetry"] = False

path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(path)
print(f"Antigravity safe settings enforced: {path}")
PY
}

start() {
  command -v agy >/dev/null 2>&1 || { echo "agy is required on the WSL host." >&2; exit 1; }
  configure_safe_settings
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
    --settings "$AGY_SETTINGS" \
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
