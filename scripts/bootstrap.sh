#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.ddev/.env"

if ! command -v ddev >/dev/null 2>&1; then
  echo "DDEV is required on the WSL host. Install DDEV first: https://docs.ddev.com/en/stable/users/install/ddev-installation/"
  exit 1
fi

mkdir -p "$HOME/projects" "$HOME/.coding-platform/workspaces" "$HOME/.codex" "$HOME/.config/opencode" "$HOME/.local/share/opencode"
touch "$HOME/.gitconfig"

DOCKER_GID="$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 999)"

random_secret() { python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/.ddev/.env.example" "$ENV_FILE"
  sed -i "s|/home/CHANGE_ME/projects|$HOME/projects|g" "$ENV_FILE"
  sed -i "s|/home/CHANGE_ME/.coding-platform/workspaces|$HOME/.coding-platform/workspaces|g" "$ENV_FILE"
  sed -i "s|/home/CHANGE_ME|$HOME|g" "$ENV_FILE"
  sed -i "s|DOCKER_GID=999|DOCKER_GID=$DOCKER_GID|g" "$ENV_FILE"
  mapfile -t SECRETS < <(printf '%s\n' "$(random_secret)" "$(random_secret)" "$(random_secret)" "$(random_secret)" "$(random_secret)")
  python3 - "$ENV_FILE" "${SECRETS[0]}" "${SECRETS[1]}" "${SECRETS[2]}" "${SECRETS[3]}" "${SECRETS[4]}" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); text=p.read_text()
for key,val in zip(["ROUTER_API_TOKEN","RUNTIME_API_TOKEN","PLATFORM_INTERNAL_TOKEN","N8N_ENCRYPTION_KEY","ANTIGRAVITY_BRIDGE_TOKEN"],sys.argv[2:]):
    text=text.replace(f"{key}=CHANGE_ME", f"{key}={val}")
p.write_text(text)
PY
  echo "Created $ENV_FILE with generated local secrets."
else
  echo "Using existing $ENV_FILE"
fi

if ! grep -q '^ANTIGRAVITY_BRIDGE_TOKEN=' "$ENV_FILE"; then
  echo "ANTIGRAVITY_BRIDGE_TOKEN=$(random_secret)" >> "$ENV_FILE"
fi
if ! grep -q '^ANTIGRAVITY_BRIDGE_PORT=' "$ENV_FILE"; then
  echo "ANTIGRAVITY_BRIDGE_PORT=8792" >> "$ENV_FILE"
fi

cd "$ROOT"

if ! command -v agy >/dev/null 2>&1; then
  echo "Antigravity CLI (agy) is required on the WSL host for the free Individual agent pool."
  echo "Install it with: curl -fsSL https://antigravity.google/cli/install.sh | bash"
  exit 1
fi

# Sanity-check the DDEV project type before startup.
if ! grep -Eq '^type:[[:space:]]+(php|generic)$' "$ROOT/.ddev/config.yaml"; then
  echo "Invalid DDEV config: .ddev/config.yaml must contain a valid 'type:' (expected 'php' for this platform)."
  exit 1
fi

"$ROOT/scripts/antigravity-bridge.sh" start
ddev start

echo
echo "Platform started. Daily startup from now on:"
echo "  cd $ROOT && ddev start"
echo
echo "Health:"
ddev platform-status || true
