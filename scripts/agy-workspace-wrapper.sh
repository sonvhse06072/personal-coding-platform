#!/usr/bin/env bash
set -euo pipefail

REAL_AGY="${ANTIGRAVITY_REAL_AGY_BIN:-}"
if [[ -z "$REAL_AGY" || ! -x "$REAL_AGY" ]]; then
  echo "ANTIGRAVITY_REAL_AGY_BIN must point to the real agy executable" >&2
  exit 127
fi

SETTINGS_PATH="${ANTIGRAVITY_SETTINGS_PATH:-$HOME/.gemini/antigravity-cli/settings.json}"

restore_bounded_settings() {
  python3 - "$SETTINGS_PATH" <<'PY'
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"cannot restore Antigravity settings: {exc}")
if not isinstance(data, dict):
    raise SystemExit("cannot restore Antigravity settings: root is not an object")

required = {
    "enableTerminalSandbox": True,
    "toolPermission": "proceed-in-sandbox",
    "artifactReviewPolicy": "always-proceed",
    "allowNonWorkspaceAccess": False,
    "enableTelemetry": False,
}
for key, expected in required.items():
    data[key] = expected

permissions = data.setdefault("permissions", {})
if not isinstance(permissions, dict):
    permissions = {}
    data["permissions"] = permissions
allow = permissions.get("allow")
deny = permissions.get("deny")
allow = list(allow) if isinstance(allow, list) else []
deny = list(deny) if isinstance(deny, list) else []
permissions["allow"] = [rule for rule in allow if rule != "unsandboxed(ddev)"]
for rule in ("command(ddev)", "unsandboxed(ddev)"):
    if rule not in deny:
        deny.append(rule)
permissions["deny"] = deny

tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(path)
PY
}

# Headless Antigravity only auto-allows file tools inside directories registered
# as active workspaces. The bridge already validates and chdirs into the isolated
# job workspace, so explicitly register that exact absolute path for this run.
#
# Antigravity CLI may also rewrite its global settings.json while exiting. Keep
# the bridge-owned scalar safety/privacy settings durable across that rewrite;
# temporary per-workspace file grants remain owned and cleaned up by the bridge.
set +e
"$REAL_AGY" --add-dir "$(pwd -P)" "$@"
agy_rc=$?
set -e

if ! restore_bounded_settings; then
  echo "Failed to restore bounded Antigravity settings after agy exit" >&2
  exit 78
fi

exit "$agy_rc"
