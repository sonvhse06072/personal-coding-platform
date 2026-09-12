#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GLOBAL_ENV="$ROOT/.ddev/.env"
HOST_ENV="$ROOT/.ddev/.env.host.local"

[[ -f "$GLOBAL_ENV" ]] || { echo "Missing $GLOBAL_ENV" >&2; exit 1; }
[[ -f "$HOST_ENV" ]] || { echo "Missing $HOST_ENV; run ./scripts/scope-service-secrets.sh" >&2; exit 1; }

# Shared non-secret paths/ports come from global env; only host helper
# credentials come from the host-local file.
# shellcheck disable=SC1090
source "$GLOBAL_ENV"
# shellcheck disable=SC1090
source "$HOST_ENV"
export RUNTIME_API_TOKEN ANTIGRAVITY_BRIDGE_TOKEN

[[ $# -gt 0 ]] || { echo "Usage: $0 <command> [args...]" >&2; exit 2; }
exec "$@"
