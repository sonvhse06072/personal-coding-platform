#!/usr/bin/env bash
# Fresh PCP install: only Docker, DDEV and basic host shell tools are needed.
# This program cannot migrate an existing installation or dispatch a model.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DDEV_DIR="$ROOT/.ddev"
ENV_FILE="$DDEV_DIR/.env"
EXAMPLE="$DDEV_DIR/.env.example"
PIN_FILE="$ROOT/config/tool-versions.env"
SETUP_IMAGE="python:3.13-slim-bookworm"
TEMP_ENV=""
stop() { printf 'PCP_PORTABLE_SETUP=STOP_%s\n' "$1" >&2; exit 2; }
finish() { if [[ -n "$TEMP_ENV" && -f "$TEMP_ENV" ]]; then rm -f -- "$TEMP_ENV"; fi; }
trap finish EXIT

[[ $# -eq 1 ]] || stop USAGE
case "$1" in
  --check|--prepare|--start) ACTION="$1" ;;
  *) stop USAGE ;;
esac
[[ "$(id -u)" != 0 ]] || stop ROOT_NOT_ALLOWED
[[ -d "$DDEV_DIR" && ! -L "$DDEV_DIR" &&
   -f "$EXAMPLE" && ! -L "$EXAMPLE" &&
   -f "$PIN_FILE" && ! -L "$PIN_FILE" &&
   -f "$ROOT/scripts/scope-service-secrets.sh" &&
   -f "$ROOT/scripts/n8n-control-plane.sh" ]] || stop SOURCE_INCOMPLETE
[[ "$ROOT" != *:* && "$ROOT" != *$'\n'* &&
   "$HOME" == /* && "$HOME" != *:* && "$HOME" != *$'\n'* ]] ||
  stop PATH_UNSAFE
for exe in bash docker ddev git stat awk grep id; do
  command -v "$exe" >/dev/null 2>&1 || stop "MISSING_$exe"
done
docker version --format '{{.Server.Version}}' >/dev/null 2>&1 ||
  stop DOCKER_UNAVAILABLE
ddev version >/dev/null 2>&1 || stop DDEV_UNAVAILABLE
PIN="$(awk -F= '$1 == "CODEX_VERSION" {print $2; exit}' "$PIN_FILE")"
[[ "$PIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.]+)?$ ]] ||
  stop CODEX_PIN_INVALID

# Existing legacy .ddev/.env is an absolute STOP, not a migration target.
if [[ -e "$ENV_FILE" || -L "$ENV_FILE" ]]; then
  [[ -f "$ENV_FILE" && ! -L "$ENV_FILE" &&
     "$(stat -c '%u' "$ENV_FILE")" == "$(id -u)" &&
     "$(stat -c '%a' "$ENV_FILE")" == 600 ]] || stop ENV_FILE_UNSAFE
  [[ "$(grep -c '^PCP_ANTIGRAVITY_MODE=' "$ENV_FILE" || true)" == 1 ]] ||
    stop LEGACY_INSTALL_NO_MIGRATION
  grep -Fxq 'PCP_ANTIGRAVITY_MODE=disabled' "$ENV_FILE" ||
    stop LEGACY_INSTALL_NO_MIGRATION
  grep -Fxq "CODEX_VERSION=$PIN" "$ENV_FILE" || stop CODEX_PIN_DRIFT
  INSTALL_STATE=PORTABLE_EXISTING
else
  INSTALL_STATE=FRESH
fi

if [[ "$ACTION" == "--check" ]]; then
  echo "PCP_PORTABLE_PREFLIGHT=PASS"
  echo "PCP_PORTABLE_INSTALL_STATE=$INSTALL_STATE"
  echo "PCP_PORTABLE_SETUP=NOT_RUN"
  echo "PCP_RUNTIME_DEPLOY=NOT_RUN"
  exit 0
fi

# Prevent unexpected secret migrations and symlink redirection.
for suffix in router coding-runtime ddev-executor n8n host; do
  file="$DDEV_DIR/.env.$suffix.local"
  if [[ "$INSTALL_STATE" == FRESH && ( -e "$file" || -L "$file" ) ]]; then
    stop EXISTING_SERVICE_ENV_NO_MIGRATION
  fi
  if [[ "$INSTALL_STATE" == PORTABLE_EXISTING && ( -e "$file" || -L "$file" ) ]]; then
    [[ -f "$file" && ! -L "$file" &&
       "$(stat -c '%u' "$file")" == "$(id -u)" &&
       "$(stat -c '%a' "$file")" == 600 ]] || stop SERVICE_ENV_UNSAFE
  fi
done
for path in "$HOME/projects" "$HOME/.coding-platform" \
  "$HOME/.coding-platform/workspaces" "$HOME/.coding-platform/direct-disabled" \
  "$HOME/.codex" "$HOME/.config" "$HOME/.config/opencode" \
  "$HOME/.local" "$HOME/.local/share" "$HOME/.local/share/opencode" \
  "$HOME/.gitconfig"; do
  [[ ! -L "$path" ]] || stop HOST_PATH_SYMLINK
done
mkdir -p -- "$HOME/projects" "$HOME/.coding-platform/workspaces" \
  "$HOME/.coding-platform/direct-disabled" "$HOME/.codex" \
  "$HOME/.config/opencode" "$HOME/.local/share/opencode"
if [[ ! -e "$HOME/.gitconfig" ]]; then (umask 077; : > "$HOME/.gitconfig"); fi
[[ -f "$HOME/.gitconfig" ]] || stop GITCONFIG_UNSAFE

if [[ "$INSTALL_STATE" == FRESH ]]; then
  DOCKER_GID="$(stat -c '%g' /var/run/docker.sock 2>/dev/null)" ||
    stop DOCKER_SOCKET_UNAVAILABLE
  [[ "$DOCKER_GID" =~ ^[0-9]+$ ]] || stop DOCKER_GID_INVALID
  TEMP_ENV="$(mktemp "$DDEV_DIR/.env.pcp-portable.XXXXXXXX")" ||
    stop ENV_TEMP_CREATE_FAILED
  chmod 600 "$TEMP_ENV"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line//\/home\/CHANGE_ME/$HOME}"
    case "$line" in
      DOCKER_GID=999) line="DOCKER_GID=$DOCKER_GID" ;;
      CODEX_VERSION=latest) line="CODEX_VERSION=$PIN" ;;
      PCP_ANTIGRAVITY_MODE=*) stop UNEXPECTED_MODE_IN_TEMPLATE ;;
    esac
    printf '%s\n' "$line" >> "$TEMP_ENV"
  done < "$EXAMPLE"
  printf '%s\n' 'PCP_ANTIGRAVITY_MODE=disabled' >> "$TEMP_ENV"
  # Atomic hardlink claim: never overwrite any concurrent or legacy env file.
  ln -- "$TEMP_ENV" "$ENV_FILE" || stop ENV_RACE
  rm -f -- "$TEMP_ENV"
  TEMP_ENV=""
fi

# Service secret generation runs exclusively inside a short-lived Python image:
# unprivileged user, no network, no Docker socket, read-only container root.
docker run --rm --pull=missing \
  --network=none --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --user "$(id -u):$(id -g)" \
  --tmpfs /tmp:rw,nosuid,nodev,mode=1777 \
  --mount "type=bind,source=$ROOT,target=$ROOT" \
  --workdir "$ROOT" --env HOME=/tmp \
  "$SETUP_IMAGE" \
  bash -euc \
  'bash scripts/scope-service-secrets.sh && bash scripts/n8n-control-plane.sh prepare-env' ||
  stop CONTAINER_SETUP_FAILED

for suffix in router coding-runtime ddev-executor n8n host; do
  file="$DDEV_DIR/.env.$suffix.local"
  [[ -f "$file" && ! -L "$file" && -s "$file" &&
     "$(stat -c '%u' "$file")" == "$(id -u)" &&
     "$(stat -c '%a' "$file")" == 600 ]] ||
    stop CONTAINER_CREDENTIALS_INCOMPLETE
done
echo "PCP_PORTABLE_PREPARE=PASS"
echo "PCP_PORTABLE_HOST_PYTHON=NOT_REQUIRED"
echo "PCP_PORTABLE_HOST_AGY=DISABLED"
echo "PCP_PORTABLE_INSTALL_STATE=$INSTALL_STATE"
if [[ "$ACTION" == --start ]]; then
  # Only explicit first-install operator intent may start DDEV.
  (cd "$ROOT" && ddev start) || stop DDEV_START_FAILED
  echo "PCP_PORTABLE_DDEV_START=PASS"
  echo "PCP_RUNTIME_FUNCTIONAL_UAT=NOT_RUN"
else
  echo "PCP_PORTABLE_DDEV_START=NOT_RUN"
fi
echo "G1_T02_DISPATCH=BLOCKED"
