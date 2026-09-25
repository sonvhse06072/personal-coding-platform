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
AGY_WRAPPER="$ROOT/scripts/agy-workspace-wrapper.sh"
AGY_QUOTA_SINK_SOURCE="$ROOT/scripts/antigravity-quota-sink.py"
AGY_QUOTA_SINK="$STATE_DIR/antigravity-quota-sink.py"
AGY_QUOTA_SNAPSHOT="$STATE_DIR/antigravity-quota.json"
BRIDGE_LAUNCHER="$ROOT/scripts/antigravity-bridge-launcher.py"
mkdir -p "$STATE_DIR" "${CODING_WORKSPACES_ROOT}" "$(dirname "$AGY_SETTINGS")"

running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

bridge_curl() {
  # Send the bearer header over stdin so it never appears in curl's argv, and
  # scrub the inherited environment copy from the curl process itself.
  printf 'Authorization: Bearer %s\n' "$ANTIGRAVITY_BRIDGE_TOKEN" \
    | env -u ANTIGRAVITY_BRIDGE_TOKEN curl -fsS -H @- "$@"
}

configure_safe_settings() {
  if [[ -f "$AGY_SETTINGS" && ! -f "$AGY_SETTINGS_BACKUP" ]]; then
    cp -a "$AGY_SETTINGS" "$AGY_SETTINGS_BACKUP"
  fi
  python3 - "$AGY_SETTINGS" "$AGY_QUOTA_SINK" "$AGY_QUOTA_SINK_SOURCE" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
sink = str(Path(sys.argv[2]).resolve())
legacy_sink = str(Path(sys.argv[3]).resolve())
try:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
except (json.JSONDecodeError, OSError) as exc:
    raise SystemExit(f"Cannot read Antigravity settings {path}: {exc}")
if not isinstance(data, dict):
    raise SystemExit(f"Antigravity settings must contain a JSON object: {path}")

# Official Antigravity CLI safety controls. Terminal commands remain sandboxed,
# code artifacts may be written headlessly, and non-workspace traversal is off.
data["enableTerminalSandbox"] = True
data["toolPermission"] = "proceed-in-sandbox"
data["artifactReviewPolicy"] = "always-proceed"
data["allowNonWorkspaceAccess"] = False
# Individual-plan privacy is user-controlled rather than an Enterprise contract.
data["enableTelemetry"] = False

permissions = data.setdefault("permissions", {})
if not isinstance(permissions, dict):
    permissions = {}
    data["permissions"] = permissions

# The bridge owns file permissions while it is running. Relative rules such as
# read_file(.) proved unreliable in headless isolated clones. Remove persistent
# file rules so no stale Ask/Deny can shadow the exact absolute per-run rules that
# antigravity-bridge.py injects for one job workspace at a time.
def is_file_rule(rule):
    return isinstance(rule, str) and (
        rule.startswith("read_file(") or rule.startswith("write_file(")
    )

allow = permissions.get("allow") or []
if not isinstance(allow, list):
    allow = []
allow = [
    rule for rule in allow
    if not is_file_rule(rule) and rule != "unsandboxed(*)"
]
required_allow = [
    "unsandboxed(git status)",
    "unsandboxed(git diff)",
    "unsandboxed(git log)",
    "unsandboxed(git show)",
    "unsandboxed(git ls-files)",
    "unsandboxed(git grep)",
    "unsandboxed(git rev-parse)",
]
for rule in required_allow:
    if rule not in allow:
        allow.append(rule)
permissions["allow"] = allow

ask = permissions.get("ask") or []
if not isinstance(ask, list):
    ask = []
permissions["ask"] = [rule for rule in ask if not is_file_rule(rule)]

deny = permissions.get("deny") or []
if not isinstance(deny, list):
    deny = []
# Remove stale file denies as well; the bridge injects an absolute .git deny for
# the exact active workspace together with the exact workspace allow rule.
deny = [rule for rule in deny if not is_file_rule(rule)]
required_deny = [
    "command(ddev)",
    "command(docker)",
    "command(sudo)",
    "unsandboxed(ddev)",
    "unsandboxed(docker)",
    "unsandboxed(sudo)",
    "unsandboxed(git push)",
    "unsandboxed(git fetch)",
    "unsandboxed(git pull)",
    "unsandboxed(git commit)",
    "unsandboxed(git checkout)",
    "unsandboxed(git switch)",
    "unsandboxed(git reset)",
    "unsandboxed(git clean)",
    "unsandboxed(git merge)",
    "unsandboxed(git rebase)",
]
for rule in required_deny:
    if rule not in deny:
        deny.append(rule)
permissions["deny"] = deny

# Quota observability uses Antigravity's documented status-line JSON payload.
# Never replace a user-defined custom status-line command. PCP runs its sink from
# a private runtime copy under ~/.coding-platform so bridge startup never chmods
# or otherwise mutates a tracked repository file. Migrate the previous PCP sink
# path automatically while preserving unrelated custom commands.
status_line = data.get("statusLine")
existing_command = ""
if isinstance(status_line, dict):
    existing_command = str(status_line.get("command") or "").strip()
if not existing_command:
    data["statusLine"] = {
        "type": "command",
        "command": sink,
        "enabled": True,
        "stack_with_default": True,
    }
elif existing_command in {sink, legacy_sink}:
    status_line["type"] = "command"
    status_line["command"] = sink
    status_line["enabled"] = True
    status_line["stack_with_default"] = True
else:
    print(f"Antigravity custom status line preserved; PCP quota sink not installed: {existing_command}")

path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(path)
print(f"Antigravity bounded headless settings enforced: {path}")
PY
}

start() {
  local real_agy
  real_agy="$(command -v agy || true)"
  [[ -n "$real_agy" ]] || { echo "agy is required on the WSL host." >&2; exit 1; }
  [[ -f "$AGY_WRAPPER" ]] || { echo "Missing $AGY_WRAPPER" >&2; exit 1; }
  [[ -f "$AGY_QUOTA_SINK_SOURCE" ]] || { echo "Missing $AGY_QUOTA_SINK_SOURCE" >&2; exit 1; }
  [[ -f "$BRIDGE_LAUNCHER" ]] || { echo "Missing $BRIDGE_LAUNCHER" >&2; exit 1; }

  # The tracked workspace wrapper already carries an executable bit. The quota
  # sink is copied into private runtime state and made executable there so bridge
  # startup never changes a tracked source file's mode or content.
  chmod 700 "$AGY_WRAPPER"
  install -m 700 "$AGY_QUOTA_SINK_SOURCE" "$AGY_QUOTA_SINK"
  export ANTIGRAVITY_REAL_AGY_BIN="$real_agy"
  export ANTIGRAVITY_QUOTA_SINK="$AGY_QUOTA_SINK"
  export ANTIGRAVITY_QUOTA_SNAPSHOT="$AGY_QUOTA_SNAPSHOT"

  configure_safe_settings
  if running; then
    echo "Antigravity bridge already running (pid $(cat "$PID_FILE"))."
    return
  fi
  rm -f "$PID_FILE"

  local -a bridge_args=(
    --host 0.0.0.0
    --port "$PORT"
    --workspaces "$CODING_WORKSPACES_ROOT"
    --agy-bin "$AGY_WRAPPER"
    --settings "$AGY_SETTINGS"
  )
  if [[ -n "${CODING_DIRECT_PROJECT_ROOT:-}" ]]; then
    bridge_args+=(--direct-workspace "$CODING_DIRECT_PROJECT_ROOT")
  fi

  nohup env -u ANTIGRAVITY_BRIDGE_TOKEN ANTIGRAVITY_BRIDGE_TOKEN_FD=3 \
    python3 "$BRIDGE_LAUNCHER" "${bridge_args[@]}" \
    3<<<"$ANTIGRAVITY_BRIDGE_TOKEN" \
    >>"$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  for _ in $(seq 1 30); do
    if bridge_curl "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
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
  if running && bridge_curl "http://127.0.0.1:$PORT/health"; then
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
