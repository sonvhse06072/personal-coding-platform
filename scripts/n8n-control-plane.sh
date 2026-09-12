#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GLOBAL_ENV="$ROOT/.ddev/.env"
N8N_ENV="$ROOT/.ddev/.env.n8n.local"
N8N_ENV_EXAMPLE="$ROOT/.ddev/.env.n8n.local.example"
PINNED_N8N_IMAGE="n8nio/n8n:2.38.6"
WORKFLOW_DIR="/opt/pcp-workflows"
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

  local existing_key control_token
  existing_key="$(read_env_value "$GLOBAL_ENV" N8N_ENCRYPTION_KEY)"

  if [[ ! -f "$N8N_ENV" ]]; then
    local encryption_key
    encryption_key="${existing_key:-$(random_secret)}"
    control_token="$(random_secret)"
    cat >"$N8N_ENV" <<EOF
N8N_ENCRYPTION_KEY=$encryption_key
N8N_CONTROL_PLANE_TOKEN=$control_token
EOF
    chmod 600 "$N8N_ENV"
    echo "Created service-scoped n8n secrets at $N8N_ENV"
  else
    chmod 600 "$N8N_ENV"
    if [[ -z "$(read_env_value "$N8N_ENV" N8N_ENCRYPTION_KEY)" ]]; then
      echo "N8N_ENCRYPTION_KEY=${existing_key:-$(random_secret)}" >>"$N8N_ENV"
    fi
    if [[ -z "$(read_env_value "$N8N_ENV" N8N_CONTROL_PLANE_TOKEN)" ]]; then
      echo "N8N_CONTROL_PLANE_TOKEN=$(random_secret)" >>"$N8N_ENV"
    fi
  fi

  # Once the same encryption key is safely service-scoped, remove the legacy
  # global copy so Router/Runtime/other containers no longer receive it.
  if [[ -n "$existing_key" ]]; then
    local scoped_key
    scoped_key="$(read_env_value "$N8N_ENV" N8N_ENCRYPTION_KEY)"
    if [[ "$existing_key" != "$scoped_key" ]]; then
      echo "Refusing n8n secret migration: scoped encryption key differs from the existing global key." >&2
      exit 1
    fi
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

sync_workflows() {
  prepare_env
  cd "$ROOT"

  # First restart loads the service-scoped ingress token, workflow mount and the
  # pinned image before CLI import. Publishing through the server CLI writes the
  # database but needs one more restart for webhook registrations to refresh.
  ddev restart
  wait_for_n8n

  ddev exec -s n8n n8n import:workflow --separate --input="$WORKFLOW_DIR"
  for workflow_id in "${WORKFLOW_IDS[@]}"; do
    ddev exec -s n8n n8n publish:workflow --id="$workflow_id"
  done

  ddev restart
  wait_for_n8n

  # Fail closed if the public control-plane webhook can be used without its
  # service-scoped ingress token.
  local status
  status="$(ddev exec -s n8n node - <<'NODE'
fetch('http://127.0.0.1:5678/webhook/coding-platform/jobs/not-a-real-job')
  .then(r => { console.log(r.status); })
  .catch(() => process.exit(1));
NODE
)"
  if [[ "$status" != "401" ]]; then
    echo "Expected unauthenticated control-plane request to return 401, got: $status" >&2
    exit 1
  fi

  echo "n8n thin control plane synced and published."
  echo "Webhooks:"
  echo "  POST https://${DDEV_HOSTNAME}:5679/webhook/coding-platform/jobs"
  echo "  GET  https://${DDEV_HOSTNAME}:5679/webhook/coding-platform/jobs/<job_id>"
  echo "  POST https://${DDEV_HOSTNAME}:5679/webhook/coding-platform/jobs/<job_id>/decision"
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
