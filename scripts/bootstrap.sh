#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.ddev/.env"

if ! command -v ddev >/dev/null 2>&1; then
  echo "DDEV is required on the WSL host. Install DDEV first: https://docs.ddev.com/en/stable/users/install/ddev-installation/"
  exit 1
fi

mkdir -p "$HOME/projects" "$HOME/.coding-platform/workspaces" "$HOME/.coding-platform/direct-disabled" "$HOME/.codex" "$HOME/.config/opencode" "$HOME/.local/share/opencode"
touch "$HOME/.gitconfig"

DOCKER_GID="$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 999)"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/.ddev/.env.example" "$ENV_FILE"
  sed -i "s|/home/CHANGE_ME/projects|$HOME/projects|g" "$ENV_FILE"
  sed -i "s|/home/CHANGE_ME/.coding-platform/workspaces|$HOME/.coding-platform/workspaces|g" "$ENV_FILE"
  sed -i "s|/home/CHANGE_ME|$HOME|g" "$ENV_FILE"
  sed -i "s|DOCKER_GID=999|DOCKER_GID=$DOCKER_GID|g" "$ENV_FILE"
  echo "Created $ENV_FILE with non-secret shared configuration."
else
  echo "Using existing $ENV_FILE"
fi

if ! grep -q '^ANTIGRAVITY_BRIDGE_PORT=' "$ENV_FILE"; then
  echo "ANTIGRAVITY_BRIDGE_PORT=8792" >> "$ENV_FILE"
fi

# Migrate/generate service credentials before any container starts. This keeps
# DDEV's globally injected .env free of bearer tokens and provider API keys.
bash "$ROOT/scripts/scope-service-secrets.sh"
# n8n additionally owns its encryption key and ingress control token.
bash "$ROOT/scripts/n8n-control-plane.sh" prepare-env

cd "$ROOT"

if ! command -v agy >/dev/null 2>&1; then
  echo "Antigravity CLI (agy) is required on the WSL host for the free Individual agent pool."
  echo "Install it with: curl -fsSL https://antigravity.google/cli/install.sh | bash"
  exit 1
fi

if ! grep -Eq '^type:[[:space:]]+(php|generic)$' "$ROOT/.ddev/config.yaml"; then
  echo "Invalid DDEV config: .ddev/config.yaml must contain a valid 'type:' (expected 'php' for this platform)."
  exit 1
fi

bash "$ROOT/scripts/with-host-secrets.sh" "$ROOT/scripts/antigravity-bridge.sh" start
ddev start

echo
echo "Platform started. Daily startup from now on:"
echo "  cd $ROOT && ddev start"
echo
echo "Health:"
ddev platform-status || true
