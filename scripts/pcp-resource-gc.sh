#!/usr/bin/env bash
set -euo pipefail

BUILDER="pcp-builder"
BUILDX_STATE="${PCP_BUILDX_CONFIG:-${HOST_HOME:-$HOME}/.coding-platform/buildx}"
RUNTIME_URL="${PCP_RUNTIME_URL:-https://personal-coding-platform.ddev.site:8788}"
MODE="dry-run"
UNTIL="168h"
TERMINAL_IMAGES=false

usage() {
  cat <<'EOF'
Usage: scripts/pcp-resource-gc.sh [--dry-run|--execute] [--until DURATION] [--terminal-images]

Defaults to report-only dry-run. DURATION is a positive Buildx duration in
hours, minutes or seconds (default: 168h). --terminal-images additionally
removes exact unreferenced DDEV built-image tags for Runtime jobs in completed
or cancelled state. It never removes volumes, containers or Git workspaces.

Run through scripts/with-host-secrets.sh so RUNTIME_API_TOKEN is available.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      MODE="dry-run"
      ;;
    --execute)
      MODE="execute"
      ;;
    --until)
      [[ $# -ge 2 ]] || { echo "--until requires a duration" >&2; exit 2; }
      UNTIL="$2"
      shift
      ;;
    --terminal-images)
      TERMINAL_IMAGES=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ ! "$UNTIL" =~ ^[1-9][0-9]*(h|m|s)$ ]]; then
  echo "Invalid --until duration '$UNTIL'; use a positive value such as 168h." >&2
  exit 2
fi

if [[ -z "${RUNTIME_API_TOKEN:-}" ]]; then
  echo "GATE=BLOCKED: RUNTIME_API_TOKEN is unavailable; Runtime cannot be queried." >&2
  exit 20
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
jobs_json="$tmpdir/jobs.json"
jobs_map="$tmpdir/jobs.map"
active_count_json="$tmpdir/active-count.json"
executor_json="$tmpdir/executor.json"
images_list="$tmpdir/images.list"

pcp_buildx() {
  BUILDX_CONFIG="$BUILDX_STATE" docker buildx "$@"
}

shared_buildx() {
  env -u BUILDX_CONFIG -u BUILDX_BUILDER docker buildx "$@"
}

fetch_runtime_active_count() {
  if ! curl -fsS --max-time 15 \
    -H "Authorization: Bearer $RUNTIME_API_TOKEN" \
    "$RUNTIME_URL/v1/jobs/active-count" \
    -o "$active_count_json"; then
    echo "GATE=BLOCKED: authoritative Runtime active-work count is unavailable." >&2
    exit 20
  fi

  if ! python3 - "$active_count_json" <<'PY'
import json
import sys

try:
    payload = json.load(open(sys.argv[1], encoding="utf-8"))
    count = payload["active_engineering_jobs"]
except (KeyError, TypeError, ValueError, OSError) as exc:
    raise SystemExit(f"invalid Runtime active-work count response: {exc}")

if isinstance(count, bool) or not isinstance(count, int) or count < 0:
    raise SystemExit(f"invalid Runtime active-work count: {count!r}")
print(f"AUTHORITATIVE_ACTIVE_ENGINEERING_JOBS={count}")
if count != 0:
    raise SystemExit(20)
PY
  then
    echo "GATE=BLOCKED: authoritative Runtime active-work count is not exactly zero." >&2
    exit 20
  fi
}

fetch_runtime_jobs() {
  if ! curl -fsS --max-time 15 \
    -H "Authorization: Bearer $RUNTIME_API_TOKEN" \
    "$RUNTIME_URL/v1/jobs?limit=500" \
    -o "$jobs_json"; then
    echo "GATE=BLOCKED: Runtime job inventory is unavailable." >&2
    exit 20
  fi

  if ! python3 - "$jobs_json" "$jobs_map" <<'PY'
import collections
import json
import re
import sys

source, target = sys.argv[1:]
try:
    jobs = json.load(open(source, encoding="utf-8"))["jobs"]
except (KeyError, TypeError, ValueError, OSError) as exc:
    raise SystemExit(f"invalid Runtime job response: {exc}")

counts = collections.Counter(str(job.get("status")) for job in jobs)
print("RUNTIME_STATUS_COUNTS=" + ",".join(
    f"{key}:{counts[key]}" for key in sorted(counts)
))

seen = {}
rows = []
for job in jobs:
    job_id = str(job.get("id") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise SystemExit(f"invalid Runtime job id: {job_id!r}")
    project = "cp-" + job_id[:10]
    if project in seen and seen[project] != job_id:
        raise SystemExit(f"ambiguous PCP project prefix: {project}")
    seen[project] = job_id
    status = str(job.get("status") or "")
    workspace = str(job.get("workspace") or "")
    rows.append((project, status, job_id, workspace))

with open(target, "w", encoding="utf-8") as handle:
    for row in rows:
        handle.write("|".join(row) + "\n")
PY
  then
    echo "GATE=BLOCKED: Runtime job inventory has invalid ownership data." >&2
    exit 20
  fi
}

check_executor_idle() {
  if ! ddev exec -s ddev-executor \
    curl -fsS --max-time 10 http://127.0.0.1:8790/health \
    >"$executor_json"; then
    echo "GATE=BLOCKED: ddev-executor health cannot be queried." >&2
    exit 20
  fi

  if ! python3 - "$executor_json" <<'PY'
import json
import sys

try:
    health = json.load(open(sys.argv[1], encoding="utf-8"))
except (TypeError, ValueError, OSError) as exc:
    raise SystemExit(f"invalid ddev-executor response: {exc}")
if health.get("status") != "ok":
    raise SystemExit("ddev-executor is not healthy")
if health.get("active_jobs") != 0:
    raise SystemExit(f"ddev-executor active_jobs={health.get('active_jobs')}")
print("DDEV_EXECUTOR_ACTIVE_JOBS=0")
PY
  then
    echo "GATE=BLOCKED: ddev-executor is unhealthy or has an active process." >&2
    exit 20
  fi
}

check_builder() {
  local info driver
  if ! info="$(pcp_buildx inspect "$BUILDER" 2>&1)"; then
    echo "GATE=BLOCKED: dedicated builder $BUILDER is unavailable." >&2
    exit 20
  fi
  driver="$(awk -F': *' '$1 == "Driver" {print $2; exit}' <<<"$info")"
  if [[ "$driver" != "docker-container" ]]; then
    echo "GATE=BLOCKED: $BUILDER driver is '$driver', expected docker-container." >&2
    exit 20
  fi
  echo "PCP_BUILDER=$BUILDER"
  echo "PCP_BUILDER_DRIVER=$driver"
}

report_usage() {
  local stage="$1"
  echo
  echo "== $stage PCP builder usage =="
  pcp_buildx du --builder "$BUILDER"
  echo
  echo "== $stage shared/default builder identity =="
  shared_buildx inspect
  echo
  echo "== $stage shared/default builder usage =="
  shared_buildx du
}

process_terminal_images() {
  local mutate="$1"
  local repo tag image_id ref labels site platform approot mapping
  local status job_id workspace containers
  local failures=0

  docker image ls --no-trunc \
    --format '{{.Repository}}|{{.Tag}}|{{.ID}}' >"$images_list"

  echo
  echo "== PCP workspace DDEV built images =="
  while IFS='|' read -r repo tag image_id; do
    [[ "$tag" =~ -cp-[0-9a-f]{10}-built$ ]] || continue
    labels="$(docker image inspect --format '{{ index .Config.Labels "com.ddev.site-name" }}|{{ index .Config.Labels "com.ddev.platform" }}|{{ index .Config.Labels "com.ddev.approot" }}' "$image_id")"
    IFS='|' read -r site platform approot <<<"$labels"
    [[ "$site" =~ ^cp-[0-9a-f]{10}$ ]] || continue
    [[ "$platform" == "ddev" ]] || continue
    [[ "$tag" == *"-$site-built" ]] || continue

    mapping="$(awk -F'|' -v site="$site" '$1 == site {print; exit}' "$jobs_map")"
    if [[ -z "$mapping" ]]; then
      echo "PROJECT=$site REF=$repo:$tag STATUS=unknown ACTION=preserve REASON=no-runtime-job"
      continue
    fi
    IFS='|' read -r _ status job_id workspace <<<"$mapping"
    ref="$repo:$tag"
    containers="$(docker ps -a --filter "ancestor=$image_id" --format '{{.Names}}' | paste -sd, -)"
    containers="${containers:-none}"

    if [[ "$status" != "completed" && "$status" != "cancelled" ]]; then
      echo "PROJECT=$site JOB=$job_id STATUS=$status REF=$ref CONTAINERS=$containers ACTION=preserve"
      continue
    fi
    if [[ -z "$workspace" || "$approot" != "$workspace" ]]; then
      echo "PROJECT=$site JOB=$job_id STATUS=$status REF=$ref CONTAINERS=$containers ACTION=preserve REASON=workspace-label-mismatch"
      continue
    fi
    if [[ "$containers" != "none" ]]; then
      echo "PROJECT=$site JOB=$job_id STATUS=$status REF=$ref CONTAINERS=$containers ACTION=preserve REASON=container-reference"
      continue
    fi

    if [[ "$mutate" == "true" ]]; then
      echo "PROJECT=$site JOB=$job_id STATUS=$status REF=$ref CONTAINERS=none ACTION=remove"
      if ! docker image rm "$ref"; then
        failures=1
      fi
    else
      echo "PROJECT=$site JOB=$job_id STATUS=$status REF=$ref CONTAINERS=none ACTION=candidate"
    fi
  done <"$images_list"

  if [[ "$failures" -ne 0 ]]; then
    echo "One or more exact PCP terminal image removals failed." >&2
    return 1
  fi
}

fetch_runtime_jobs
fetch_runtime_active_count
check_executor_idle
check_builder
echo "ZERO_ACTIVE_ENGINEERING_WORK=PASS"
echo "GC_MODE=$MODE"
echo "GC_UNTIL=$UNTIL"
echo "GC_TERMINAL_IMAGES=$TERMINAL_IMAGES"
report_usage "BEFORE"
process_terminal_images false

if [[ "$MODE" == "dry-run" ]]; then
  echo
  echo "PCP_RESOURCE_GC=DRY_RUN_PASS"
  exit 0
fi

# Revalidate immediately before mutation. This is deliberately duplicated so a
# stale report cannot authorize GC after engineering work begins.
fetch_runtime_jobs
check_executor_idle
fetch_runtime_active_count

echo
echo "== Prune PCP builder cache older than $UNTIL =="
pcp_buildx prune \
  --builder "$BUILDER" \
  --filter "until=$UNTIL" \
  --force

if [[ "$TERMINAL_IMAGES" == "true" ]]; then
  fetch_runtime_jobs
  check_executor_idle
  fetch_runtime_active_count
  process_terminal_images true
fi

report_usage "AFTER"
echo
echo "PCP_RESOURCE_GC=PASS"
