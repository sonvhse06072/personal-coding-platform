#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DDEV_DIR="$ROOT/.ddev"
GLOBAL_ENV="$DDEV_DIR/.env"

ROUTER_ENV="$DDEV_DIR/.env.router.local"
RUNTIME_ENV="$DDEV_DIR/.env.coding-runtime.local"
EXECUTOR_ENV="$DDEV_DIR/.env.ddev-executor.local"
N8N_ENV="$DDEV_DIR/.env.n8n.local"
HOST_ENV="$DDEV_DIR/.env.host.local"

random_secret() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

read_env_value() {
  local file="$1" key="$2"
  python3 - "$file" "$key" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); key=sys.argv[2]
if not path.exists():
    raise SystemExit(0)
for line in path.read_text(encoding="utf-8").splitlines():
    if line.startswith(key + "="):
        print(line.split("=",1)[1])
        break
PY
}

is_real_secret() {
  local value="${1:-}"
  local trimmed="$value"
  trimmed="${trimmed#"${trimmed%%[![:space:]]*}"}"
  trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
  [[ -n "$trimmed" && "$trimmed" != "CHANGE_ME" && "$trimmed" != "change-me" ]]
}

set_env_value() {
  local file="$1" key="$2" value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); key=sys.argv[2]; value=sys.argv[3]
lines=path.read_text(encoding="utf-8").splitlines() if path.exists() else []
out=[]; written=False
for line in lines:
    if line.startswith(key + "="):
        if not written:
            out.append(f"{key}={value}")
            written=True
        continue
    out.append(line)
if not written:
    out.append(f"{key}={value}")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("\n".join(out)+"\n", encoding="utf-8")
PY
}

remove_env_key() {
  local file="$1" key="$2"
  python3 - "$file" "$key" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]); key=sys.argv[2]
if not path.exists():
    raise SystemExit(0)
lines=[line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith(key + "=")]
path.write_text("\n".join(lines)+"\n", encoding="utf-8")
PY
}

ensure_local_file() {
  local target="$1" example="$2"
  if [[ ! -f "$target" ]]; then
    cp "$example" "$target"
  fi
  chmod 600 "$target"
}

resolve_shared_secret() {
  local key="$1"; shift
  local destinations=("$@")
  local values=() value file global_value canonical=""

  global_value="$(read_env_value "$GLOBAL_ENV" "$key")"
  if is_real_secret "$global_value"; then
    values+=("$global_value")
  fi
  for file in "${destinations[@]}"; do
    value="$(read_env_value "$file" "$key")"
    if is_real_secret "$value"; then
      values+=("$value")
    fi
  done

  if (( ${#values[@]} > 0 )); then
    canonical="${values[0]}"
    for value in "${values[@]}"; do
      if [[ "$value" != "$canonical" ]]; then
        echo "Conflicting existing values for $key; refusing credential migration." >&2
        exit 1
      fi
    done
  else
    canonical="$(random_secret)"
  fi

  for file in "${destinations[@]}"; do
    set_env_value "$file" "$key" "$canonical"
  done
  remove_env_key "$GLOBAL_ENV" "$key"
}

move_optional_secret() {
  local key="$1" destination="$2"
  local global_value local_value
  global_value="$(read_env_value "$GLOBAL_ENV" "$key")"
  local_value="$(read_env_value "$destination" "$key")"

  if is_real_secret "$global_value" && is_real_secret "$local_value" && [[ "$global_value" != "$local_value" ]]; then
    echo "Conflicting existing values for $key; refusing credential migration." >&2
    exit 1
  fi
  if is_real_secret "$global_value"; then
    set_env_value "$destination" "$key" "$global_value"
  fi
  remove_env_key "$GLOBAL_ENV" "$key"
}

main() {
  [[ -f "$GLOBAL_ENV" ]] || {
    echo "Missing $GLOBAL_ENV. Run ./scripts/bootstrap.sh first." >&2
    exit 1
  }

  ensure_local_file "$ROUTER_ENV" "$DDEV_DIR/.env.router.local.example"
  ensure_local_file "$RUNTIME_ENV" "$DDEV_DIR/.env.coding-runtime.local.example"
  ensure_local_file "$EXECUTOR_ENV" "$DDEV_DIR/.env.ddev-executor.local.example"
  ensure_local_file "$N8N_ENV" "$DDEV_DIR/.env.n8n.local.example"
  ensure_local_file "$HOST_ENV" "$DDEV_DIR/.env.host.local.example"

  # Shared bearer tokens are copied only to the services that consume them.
  resolve_shared_secret ROUTER_API_TOKEN "$ROUTER_ENV" "$RUNTIME_ENV"
  resolve_shared_secret RUNTIME_API_TOKEN "$RUNTIME_ENV" "$N8N_ENV" "$HOST_ENV"
  resolve_shared_secret PLATFORM_INTERNAL_TOKEN "$RUNTIME_ENV" "$EXECUTOR_ENV"
  resolve_shared_secret ANTIGRAVITY_BRIDGE_TOKEN "$RUNTIME_ENV" "$HOST_ENV"

  resolve_shared_secret DASHBOARD_CONTROL_TOKEN "$RUNTIME_ENV"

  # Provider credentials are Runtime-only. Empty values are removed from the
  # global DDEV environment as well, so future configuration cannot leak them.
  move_optional_secret DEEPSEEK_API_KEY "$RUNTIME_ENV"
  move_optional_secret ANTHROPIC_API_KEY "$RUNTIME_ENV"
  move_optional_secret OPENAI_API_KEY "$RUNTIME_ENV"
  move_optional_secret GROQ_API_KEY "$RUNTIME_ENV"
  move_optional_secret OPENROUTER_API_KEY "$RUNTIME_ENV"

  echo "Service-scoped credential migration complete. Global .ddev/.env contains no platform credentials."
}

main "$@"
