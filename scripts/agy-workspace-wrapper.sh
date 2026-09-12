#!/usr/bin/env bash
set -euo pipefail

REAL_AGY="${ANTIGRAVITY_REAL_AGY_BIN:-}"
if [[ -z "$REAL_AGY" || ! -x "$REAL_AGY" ]]; then
  echo "ANTIGRAVITY_REAL_AGY_BIN must point to the real agy executable" >&2
  exit 127
fi

# Headless Antigravity only auto-allows file tools inside directories registered
# as active workspaces. The bridge already validates and chdirs into the isolated
# job workspace, so explicitly register that exact absolute path for this run.
exec "$REAL_AGY" --add-dir "$(pwd -P)" "$@"
