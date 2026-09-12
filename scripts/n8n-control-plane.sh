#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GLOBAL_ENV="$ROOT/.ddev/.env"
N8N_ENV="$ROOT/.ddev/.env.n8n.local"
N8N_ENV_EXAMPLE="$ROOT/.ddev/.env.n8n.local.example"
PINNED_N8N_IMAGE="n8nio/n8n:2.38.6"
WORKFLOW_DIR="/opt/pcp-workflows"
JOB_STATUS_WEBHOOK_ID="f94fd841-0da8-42af-a06a-17b78d5a1ea7"
HUMAN_DECISION_WEBHOOK_ID="a0db357c-167e-43c4-a692-e049aa21ef63"
WORKFLOW_IDS=(
  pcpJobIntakeV001
  pcpJobStatusV001
  pcpHumanDecision1
)

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
path = Path(sys.argv[1])
key = sys.argv[2]
if not path.exists():
    raise SystemExit(0)
for line in path.read_text(encoding="utf-8").splitlines():
    if line.startswith(key + "="):
        print(line.split("=", 1)[1])
        break
PY
}

is_real_secret() {
  local value="${1:-}"
  [[ -n "$value" && "$value" != "CHANGE_ME" ]]
}

set_env_value() {
  local file="$1" key="$2" value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
updated = []
written = False
for line in lines:
    if line.startswith(key + "="):
        if not written:
            updated.append(f"{key}={value}")
            written = True
        continue
    updated.append(line)
if not written:
    updated.append(f"{key}={value}")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY
}

remove_env_key() {
  local file="$1" key="$2"
  python3 - "$file" "$key" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
key = sys.argv[2]
if not path.exists():
    raise SystemExit(0)
lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith(key + "=")]
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

prepare_env() {
  [[ -f "$GLOBAL_ENV" ]] || {
    echo "Missing $GLOBAL_ENV. Run ./scripts/bootstrap.sh first." >&2
    exit 1
  }
  [[ -f "$N8N_ENV_EXAMPLE" ]] || {
    echo "Missing $N8N_ENV_EXAMPLE" >&2
    exit 1
  }

  local global_raw global_key local_key control_token
  global_raw="$(read_env_value "$GLOBAL_ENV" N8N_ENCRYPTION_KEY)"
  global_key=""
  if is_real_secret "$global_raw"; then
    global_key="$global_raw"
  fi

  if [[ ! -f "$N8N_ENV" ]]; then
    cp "$N8N_ENV_EXAMPLE" "$N8N_ENV"
  fi
  chmod 600 "$N8N_ENV"

  local_key="$(read_env_value "$N8N_ENV" N8N_ENCRYPTION_KEY)"
  if ! is_real_secret "$local_key"; then
    local_key="${global_key:-$(random_secret)}"
    set_env_value "$N8N_ENV" N8N_ENCRYPTION_KEY "$local_key"
  fi

  control_token="$(read_env_value "$N8N_ENV" N8N_CONTROL_PLANE_TOKEN)"
  if ! is_real_secret "$control_token"; then
    set_env_value "$N8N_ENV" N8N_CONTROL_PLANE_TOKEN "$(random_secret)"
  fi

  # Existing n8n data is encrypted with the old key. Never silently rotate it.
  if [[ -n "$global_key" && "$global_key" != "$local_key" ]]; then
    echo "Refusing n8n secret migration: scoped encryption key differs from the existing global key." >&2
    exit 1
  fi

  # The service-scoped file now owns n8n secrets. Remove even a legacy
  # placeholder from the global DDEV environment so other services never receive it.
  if grep -q '^N8N_ENCRYPTION_KEY=' "$GLOBAL_ENV"; then
    remove_env_key "$GLOBAL_ENV" N8N_ENCRYPTION_KEY
    echo "Moved N8N_ENCRYPTION_KEY out of the global DDEV environment."
  fi

  python3 - "$GLOBAL_ENV" "$PINNED_N8N_IMAGE" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
pinned = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
found = False
for i, line in enumerate(lines):
    if line.startswith("N8N_IMAGE="):
        found = True
        value = line.split("=", 1)[1]
        if value in {"", "n8nio/n8n:latest"}:
            lines[i] = f"N8N_IMAGE={pinned}"
        elif value != pinned:
            print(f"Keeping custom N8N_IMAGE={value}; tested platform pin is {pinned}")
        break
if not found:
    lines.append(f"N8N_IMAGE={pinned}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

wait_for_n8n() {
  for _ in $(seq 1 60); do
    if ddev exec -s n8n node -e 'fetch("http://127.0.0.1:5678/healthz").then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))' >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "n8n did not become healthy in time." >&2
  return 1
}

assert_runtime_only_secret_boundary() {
  ddev exec -s n8n node -e '
const required = ["N8N_ENCRYPTION_KEY", "N8N_CONTROL_PLANE_TOKEN", "RUNTIME_API_TOKEN"];
const forbidden = [
  "ROUTER_API_TOKEN", "PLATFORM_INTERNAL_TOKEN", "ANTIGRAVITY_BRIDGE_TOKEN",
  "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
  "GROQ_API_KEY", "OPENROUTER_API_KEY", "GITHUB_DELIVERY_TOKEN"
];
const missing = required.filter((key) => !process.env[key] || process.env[key] === "CHANGE_ME");
const leaked = forbidden.filter((key) => Boolean(process.env[key]));
if (missing.length || leaked.length) {
  console.error(JSON.stringify({error:"n8n_secret_boundary_failed", missing, leaked}));
  process.exit(1);
}
console.log(JSON.stringify({status:"ok", boundary:"runtime-only"}));
'
}

smoke_webhooks() {
  local status_path unauth_status auth_status
  status_path="/webhook/${JOB_STATUS_WEBHOOK_ID}/coding-platform/jobs/not-a-real-job"

  unauth_status="$(
    ddev exec -s n8n node -e \
      'fetch("http://127.0.0.1:5678'"$status_path"'").then(r=>console.log(r.status)).catch(()=>process.exit(1))' \
      2>/dev/null | tr -d '\r' | tail -n1
  )"
  if [[ "$unauth_status" != "401" ]]; then
    echo "Expected unauthenticated control-plane request to return 401, got: $unauth_status" >&2
    exit 1
  fi

  # With the service-scoped ingress token, the request must cross n8n and reach
  # Runtime. A deliberately unknown job should therefore preserve Runtime's 404.
  auth_status="$(
    ddev exec -s n8n node -e \
      'fetch("http://127.0.0.1:5678'"$status_path"'", {headers:{"X-Control-Token":process.env.N8N_CONTROL_PLANE_TOKEN}}).then(r=>console.log(r.status)).catch(()=>process.exit(1))' \
      2>/dev/null | tr -d '\r' | tail -n1
  )"
  if [[ "$auth_status" != "404" ]]; then
    echo "Expected authenticated status proxy to preserve Runtime 404, got: $auth_status" >&2
    exit 1
  fi
}

sync_workflows() {
  prepare_env
  cd "$ROOT"

  # First restart loads service-scoped secrets, the read-only workflow mount and
  # the pinned image. Publishing through server CLI updates the DB; restart once
  # more so webhook registrations are refreshed in the running n8n process.
  ddev restart
  wait_for_n8n
  assert_runtime_only_secret_boundary

  ddev exec -s n8n n8n import:workflow --separate --input="$WORKFLOW_DIR"
  for workflow_id in "${WORKFLOW_IDS[@]}"; do
    ddev exec -s n8n n8n publish:workflow --id="$workflow_id"
  done

  ddev restart
  wait_for_n8n
  assert_runtime_only_secret_boundary
  smoke_webhooks

  echo "n8n thin control plane synced and published."
  echo "Production webhook paths (use the n8n HTTPS base URL shown by 'ddev describe'):"
  echo "  POST /webhook/coding-platform/jobs"
  echo "  GET  /webhook/${JOB_STATUS_WEBHOOK_ID}/coding-platform/jobs/<job_id>"
  echo "  POST /webhook/${HUMAN_DECISION_WEBHOOK_ID}/coding-platform/jobs/<job_id>/decision"
  echo "Use header: X-Control-Token: <value from .ddev/.env.n8n.local>"
}

status() {
  cd "$ROOT"
  ddev exec -s n8n node -e 'fetch("http://127.0.0.1:5678/healthz").then(async r=>{console.log(JSON.stringify({status:r.ok?"ok":"down",http_status:r.status}))}).catch(()=>{console.log(JSON.stringify({status:"down"}));process.exit(1)})'
}

case "${1:-status}" in
  prepare-env) prepare_env ;;
  sync) sync_workflows ;;
  status) status ;;
  *) echo "Usage: $0 {prepare-env|sync|status}" >&2; exit 2 ;;
esac
