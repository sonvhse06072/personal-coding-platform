#!/usr/bin/env bash
set -euo pipefail

MIN_DDEV_VERSION="${1:-1.25.4}"

fail() {
  echo "$1" >&2
  exit 1
}

command -v ddev >/dev/null 2>&1 || fail "DDEV is required but was not found in PATH."
command -v python3 >/dev/null 2>&1 || fail "python3 is required to validate the DDEV version."

raw_version="$(ddev --version 2>&1)" || fail "Unable to determine the installed DDEV version."
current_version="$(python3 - "$raw_version" <<'PY'
import re
import sys

match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", sys.argv[1])
if match:
    print(".".join(match.groups()))
PY
)"

if [[ -z "$current_version" ]]; then
  fail "Unable to parse the installed DDEV version from: $raw_version"
fi

if ! python3 - "$current_version" "$MIN_DDEV_VERSION" <<'PY'
import sys


def version_tuple(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(value)
    return tuple(int(part) for part in parts)

current = version_tuple(sys.argv[1])
minimum = version_tuple(sys.argv[2])
raise SystemExit(0 if current >= minimum else 1)
PY
then
  fail "DDEV >= ${MIN_DDEV_VERSION} is required for service-scoped .ddev/.env.<service>.local files; found v${current_version}. Upgrade DDEV and retry."
fi
