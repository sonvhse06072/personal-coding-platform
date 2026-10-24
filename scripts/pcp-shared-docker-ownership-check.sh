#!/usr/bin/env bash
# B2.2c1-A2 source-only: shared Docker Desktop PCP ownership preflight.
# Read-only, no Docker mutation or discovery of unrelated projects.
# Every outcome is STOP; neither cleanup nor LIVE is granted by this script.
set -euo pipefail
export LC_ALL=C

stop() {
  printf 'PCP_A2_RESULT=STOP\n'
  printf 'PCP_A2_REASON=%s\n' "$1"
  printf 'PCP_A2_DOCKER=SHARED_DAEMON_NOT_SANDBOXED\n'
  printf 'PCP_A2_CLEANUP=NOT_AUTHORIZED\n'
  printf 'PCP_B22C1_LIVE=STOP\n'
  exit 2
}

[[ $# -eq 1 && "$1" == "--check" ]] || stop USAGE
[[ "$(id -u)" != 0 ]] || stop ROOT_FORBIDDEN
for bin in git docker grep bash; do
  command -v "$bin" >/dev/null 2>&1 || stop REQUIRED_TOOL_MISSING
done
for key in DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH \
           DOCKER_CONFIG PCP_RUNTIME_STARTUP_MODE PCP_LOCAL_TASK_SOURCE_ENABLED \
           PCP_LOCAL_TASK_WORKER_ENABLED PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION; do
  [[ -z "${!key:-}" ]] || stop ENV_OVERRIDE_OR_ACTIVATION
done
[[ "${HOME:-}" == /* && "$HOME" != /mnt/* && "$HOME" != *$'\n'* ]] ||
  stop HOME_UNSAFE
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)" ||
  stop ROOT_MISSING
[[ "$ROOT" == /* && "$ROOT" != /mnt/* &&
   ! -L "$ROOT/scripts" && ! -L "$ROOT/config" && ! -L "$ROOT/.ddev" ]] ||
  stop ROOT_UNSAFE
top="$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" ||
  stop SOURCE_GIT_UNAVAILABLE
[[ "$top" == "$ROOT" ]] || stop SOURCE_GIT_IDENTITY
origin="$(git -C "$ROOT" remote get-url origin 2>/dev/null)" ||
  stop SOURCE_REMOTE_UNAVAILABLE
case "$origin" in
  https://github.com/sonvhse06072/personal-coding-platform.git|\
  git@github.com:sonvhse06072/personal-coding-platform.git) ;;
  *) stop SOURCE_NOT_PCP ;;
esac
head="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null)" ||
  stop SOURCE_SHA_UNAVAILABLE
[[ "$head" =~ ^[a-f0-9]{40}$ ]] || stop SOURCE_SHA_INVALID
for relative in scripts/pcp-shared-docker-ownership-check.sh \
  config/projects.pcp-local.yml config/project-baselines.pcp-local.yml \
  .ddev/config.yaml .ddev/docker-compose.platform.yaml; do
  [[ -f "$ROOT/$relative" && ! -L "$ROOT/$relative" ]] ||
    stop SOURCE_FILE_UNSAFE
  pinned="$(git -C "$ROOT" rev-parse "HEAD:$relative" 2>/dev/null)" ||
    stop SOURCE_NOT_TRACKED
  working="$(git -C "$ROOT" hash-object -- "$ROOT/$relative" 2>/dev/null)" ||
    stop SOURCE_HASH_UNAVAILABLE
  [[ "$pinned" =~ ^[a-f0-9]{40}$ && "$pinned" == "$working" ]] ||
    stop SOURCE_FILE_DRIFT
done
# These checks prove only a still-draft PCP registry, not safe installed state.
grep -Fxq '  pcp-local:' "$ROOT/config/projects.pcp-local.yml" ||
  stop PCP_DRAFT_PROJECT_MISSING
grep -Fxq '    path: null' "$ROOT/config/projects.pcp-local.yml" ||
  stop PCP_PROJECT_ALREADY_ACTIVE
grep -Fxq '    active_revision: null' \
  "$ROOT/config/project-baselines.pcp-local.yml" ||
  stop PCP_BASELINE_ALREADY_ACTIVE
grep -Fxq '    revisions: {}' \
  "$ROOT/config/project-baselines.pcp-local.yml" ||
  stop PCP_BASELINE_ALREADY_POPULATED
# Historical Compose must not be started from this preflight.
grep -Fq '/config/projects.yml' "$ROOT/.ddev/docker-compose.platform.yaml" ||
  stop UNREVIEWED_LEGACY_COMPOSE_CHANGE

context="$(docker context show 2>/dev/null)" || stop CONTEXT_UNAVAILABLE
[[ "$context" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] ||
  stop CONTEXT_INVALID
endpoint="$(docker context inspect "$context" --format \
  '{{.Endpoints.docker.Host}}' 2>/dev/null)" || stop ENDPOINT_UNAVAILABLE
case "$endpoint" in
  unix:///var/run/docker.sock) ;;
  unix:///run/user/*/docker.sock)
    [[ "$endpoint" =~ ^unix:///run/user/[0-9]+/docker\.sock$ ]] ||
      stop ENDPOINT_NOT_LOCAL ;;
  *) stop ENDPOINT_NOT_LOCAL ;;
esac
provider="$(docker info --format '{{.OperatingSystem}}' 2>/dev/null)" ||
  stop DAEMON_UNAVAILABLE
[[ -n "$provider" && "$provider" != *$'\n'* &&
   "${provider,,}" == *docker*desktop* ]] || stop PROVIDER_NOT_DESKTOP

# The five queries below MUST keep their exact server-side label filters.
# Parse results privately: no names, paths, image metadata or IDs emitted.
count_query() {
  local result item count=0
  result="$(docker "$@" 2>/dev/null)" || stop FILTERED_DOCKER_QUERY_FAILED
  if [[ -n "$result" ]]; then
    while IFS= read -r item; do
      [[ "$item" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] ||
        stop DOCKER_RESPONSE_UNTRUSTED
      count=$((count + 1))
      (( count <= 200 )) || stop UNBOUNDED_RESOURCE_SET
    done <<< "$result"
  fi
  RESOURCE_COUNT="$count"
}
count_query ps -a --filter 'label=com.ddev.site-name=personal-coding-platform' \
  --format '{{.ID}}'
legacy_containers="$RESOURCE_COUNT"
count_query volume ls \
  --filter 'label=com.docker.compose.project=ddev-personal-coding-platform' \
  --format '{{.Name}}'
legacy_volumes="$RESOURCE_COUNT"
count_query ps -a --filter 'label=com.ddev.site-name=pcp-local' \
  --format '{{.ID}}'
new_containers="$RESOURCE_COUNT"
count_query volume ls --filter 'label=com.docker.compose.project=ddev-pcp-local' \
  --format '{{.Name}}'
new_volumes="$RESOURCE_COUNT"
count_query network ls --filter 'label=com.docker.compose.project=ddev-pcp-local' \
  --format '{{.ID}}'
new_networks="$RESOURCE_COUNT"

printf 'PCP_A2_SOURCE_HEAD=%s\n' "$head"
printf 'PCP_A2_PROVIDER=DOCKER_DESKTOP_SHARED_OWNER_ACCEPTED_RISK\n'
printf 'PCP_A2_LEGACY_PLATFORM_CONTAINER_CANDIDATES=%s\n' "$legacy_containers"
printf 'PCP_A2_LEGACY_PLATFORM_VOLUME_CANDIDATES=%s\n' "$legacy_volumes"
printf 'PCP_A2_NEW_NAMESPACE_CONTAINER_CANDIDATES=%s\n' "$new_containers"
printf 'PCP_A2_NEW_NAMESPACE_VOLUME_CANDIDATES=%s\n' "$new_volumes"
printf 'PCP_A2_NEW_NAMESPACE_NETWORK_CANDIDATES=%s\n' "$new_networks"
printf 'PCP_A2_LEGACY_JOBS_AND_DB=NOT_INSPECTED\n'
printf 'PCP_A2_UNLABELED_RESOURCES=NOT_VERIFIED\n'
if (( new_containers + new_volumes + new_networks > 0 )); then
  stop NEW_NAMESPACE_COLLISION_REVIEW_REQUIRED
fi
# Even clean filtered counts cannot prove exclusive ownership, safe cleanup,
# no unlabeled resources, or protection against a privileged Docker socket.
stop OWNER_REVIEW_REQUIRED_SHARED_DOCKER
