#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <project-id> <title> <description>"
  echo "Optional env: CODING_DISABLED_PROVIDERS=openai,google"
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1090
source "$ROOT/.ddev/.env"
PROJECT=$1; TITLE=$2; DESC=$3
DISABLED_PROVIDERS="${CODING_DISABLED_PROVIDERS:-}"
curl -fsS -X POST "https://personal-coding-platform.ddev.site:8788/v1/jobs" \
  -H "Authorization: Bearer $RUNTIME_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$(python3 - "$PROJECT" "$TITLE" "$DESC" "$DISABLED_PROVIDERS" <<'PY'
import json,sys
providers=[p.strip() for p in sys.argv[4].split(',') if p.strip()]
provider_state={
    f"provider:{provider}": {
        "healthy": False,
        "available": False,
        "quota_pressure": 1.0,
        "error_rate": 1.0,
    }
    for provider in providers
}
print(json.dumps({
    "project_id":sys.argv[1],
    "task":{"title":sys.argv[2],"description":sys.argv[3]},
    "provider_state":provider_state,
    "auto_run":True,
}))
PY
)"
echo
