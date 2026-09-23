#!/usr/bin/env bash
set -uo pipefail

BUILDER="pcp-builder"
BUILDX_STATE="${PCP_BUILDX_CONFIG:-${HOST_HOME:-$HOME}/.coding-platform/buildx}"
RUNTIME_URL="${PCP_RUNTIME_URL:-https://personal-coding-platform.ddev.site:8788}"
WORKSPACES_ROOT="${CODING_WORKSPACES_ROOT:-$HOME/.coding-platform/workspaces}"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
jobs_map="$tmpdir/jobs.map"

section() {
  printf '\n== %s ==\n' "$1"
}

pcp_buildx() {
  BUILDX_CONFIG="$BUILDX_STATE" docker buildx "$@"
}

shared_buildx() {
  env -u BUILDX_CONFIG -u BUILDX_BUILDER docker buildx "$@"
}

load_runtime_map() {
  local jobs_json="$tmpdir/jobs.json"
  [[ -n "${RUNTIME_API_TOKEN:-}" ]] || return 1
  curl -fsS --max-time 15 \
    -H "Authorization: Bearer $RUNTIME_API_TOKEN" \
    "$RUNTIME_URL/v1/jobs?limit=500" \
    -o "$jobs_json" \
    || return 1
  python3 - "$jobs_json" "$jobs_map" <<'PY'
import json
import re
import sys

source, target = sys.argv[1:]
jobs = json.load(open(source, encoding="utf-8"))["jobs"]
seen = {}
with open(target, "w", encoding="utf-8") as handle:
    for job in jobs:
        job_id = str(job.get("id") or "")
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            continue
        project = "cp-" + job_id[:10]
        if project in seen and seen[project] != job_id:
            continue
        seen[project] = job_id
        handle.write("|".join((
            project,
            job_id,
            str(job.get("status") or "unknown"),
            str(job.get("workspace") or ""),
        )) + "\n")
PY
}

runtime_map_status="unavailable"
if load_runtime_map; then
  runtime_map_status="available"
fi

section "Docker aggregate disk usage"
docker system df || true

section "PCP dedicated builder identity"
echo "BUILDX_CONFIG=$BUILDX_STATE"
if builder_info="$(pcp_buildx inspect "$BUILDER" 2>&1)"; then
  echo "$builder_info"
  builder_driver="$(awk -F': *' '$1 == "Driver" {print $2; exit}' <<<"$builder_info")"
  builder_status="$(awk -F': *' '$1 == "Status" {print $2; exit}' <<<"$builder_info")"
  echo "PCP_BUILDER=$BUILDER DRIVER=${builder_driver:-unknown} STATUS=${builder_status:-unknown}"
else
  echo "PCP_BUILDER=$BUILDER STATUS=absent"
fi

section "PCP dedicated builder disk usage"
if ! pcp_buildx du --builder "$BUILDER"; then
  echo "PCP builder usage unavailable"
fi

section "Shared/default builder identity"
shared_buildx inspect || true

section "Shared/default builder disk usage"
shared_buildx du || true

section "PCP platform containers"
docker ps -a --size \
  --filter "name=ddev-personal-coding-platform" \
  --format 'ID={{.ID}} NAME={{.Names}} IMAGE={{.Image}} STATUS={{.Status}} SIZE={{.Size}}' || true

section "PCP-managed workspace DDEV containers"
docker ps -a --size \
  --filter "label=com.ddev.site-name" \
  --format '{{.Label "com.ddev.site-name"}}|{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Size}}' \
  | awk -F'|' '$1 ~ /^cp-/ {print "PROJECT="$1" ID="$2" NAME="$3" IMAGE="$4" STATUS="$5" SIZE="$6}' \
  || true

section "PCP platform images"
docker image ls \
  --format '{{.Repository}}|{{.Tag}}|{{.ID}}|{{.CreatedSince}}|{{.Size}}' \
  | awk -F'|' '$1 ~ /^personal-coding-platform-(router|coding-runtime|ddev-executor)$/ {print "REPO="$1" TAG="$2" ID="$3" CREATED="$4" SIZE="$5}' \
  || true

section "PCP-managed workspace DDEV built images"
echo "RUNTIME_JOB_MAP=$runtime_map_status"
while IFS='|' read -r repo tag image_id created size; do
  [[ "$tag" =~ -cp-[0-9a-f]{10}-built$ ]] || continue
  labels="$(docker image inspect --format '{{ index .Config.Labels "com.ddev.site-name" }}|{{ index .Config.Labels "com.ddev.platform" }}|{{ index .Config.Labels "com.ddev.approot" }}' "$image_id" 2>/dev/null || true)"
  IFS='|' read -r site platform approot <<<"$labels"
  [[ "$site" =~ ^cp-[0-9a-f]{10}$ && "$platform" == "ddev" ]] || continue
  mapping="$(awk -F'|' -v site="$site" '$1 == site {print; exit}' "$jobs_map" 2>/dev/null || true)"
  if [[ -n "$mapping" ]]; then
    IFS='|' read -r _ job_id job_status runtime_workspace <<<"$mapping"
  else
    job_id="unknown"
    job_status="unknown"
    runtime_workspace="unknown"
  fi
  containers="$(docker ps -a --filter "ancestor=$image_id" --format '{{.Names}}' | paste -sd, -)"
  containers="${containers:-none}"
  echo "PROJECT=$site JOB=$job_id JOB_STATUS=$job_status REPO=$repo TAG=$tag ID=$image_id SIZE=$size CREATED=$created CONTAINERS=$containers APPROOT=$approot RUNTIME_WORKSPACE=$runtime_workspace"
done < <(docker image ls --no-trunc --format '{{.Repository}}|{{.Tag}}|{{.ID}}|{{.CreatedSince}}|{{.Size}}')

section "Dangling images"
docker image ls \
  --filter dangling=true \
  --format 'ID={{.ID}} CREATED={{.CreatedSince}} SIZE={{.Size}}' || true

section "PCP job volumes"
while IFS= read -r volume; do
  [[ "$volume" =~ (^|[-_])cp-[0-9a-f]{10}([-_]|$) ]] || continue
  containers="$(docker ps -a --filter "volume=$volume" --format '{{.Names}}' | paste -sd, -)"
  containers="${containers:-none}"
  echo "VOLUME=$volume CONTAINERS=$containers"
done < <(docker volume ls --format '{{.Name}}')

section "Other PCP/DDEV candidate volumes"
docker volume ls \
  --format '{{.Name}}' \
  | grep -E 'personal-coding-platform|(^|[-_])ddev' \
  || true

section "Workspace directory sizes"
if [[ -d "$WORKSPACES_ROOT" ]]; then
  find "$WORKSPACES_ROOT" \
    -mindepth 1 -maxdepth 1 -type d -print0 \
    | xargs -0 -r du -sh \
    | sort -h
else
  echo "Workspace root not found: $WORKSPACES_ROOT"
fi

section "DDEV project registry"
if command -v ddev >/dev/null 2>&1; then
  ddev list || true
else
  echo "ddev is unavailable on this host"
fi

echo
echo "RESOURCE_INVENTORY=PASS"
