#!/usr/bin/env bash
# B2.2c1-A1: read-only source/daemon-metadata prescreen, NEVER a live gate.
# On an independently disposable WSL2/VM only. No container enumeration,
# historical project access, credentials, Docker mutation or DDEV startup.
set -euo pipefail
export LC_ALL=C

stop() {
  # Codes are fixed literals in this script, not untrusted tool output.
  printf 'PCP_GATE_A_RESULT=STOP\nPCP_GATE_A_REASON=%s\n' "$1"
  printf 'PCP_GATE_A_PHYSICAL_ISOLATION=NOT_ATTESTED\n'
  printf 'PCP_B22C1_LIVE=STOP\n'
  exit 2
}

[[ $# -eq 1 && "$1" == "--check" ]] || stop USAGE
[[ "$(id -u)" != 0 ]] || stop ROOT_FORBIDDEN
for tool in bash git docker ddev grep sha256sum uname; do
  command -v "$tool" >/dev/null 2>&1 || stop REQUIRED_TOOL_MISSING
done

# The source-only inspector cannot be repurposed by model/worker env flags.
for key in PCP_RUNTIME_STARTUP_MODE PCP_LOCAL_TASK_SOURCE_ENABLED \
           PCP_LOCAL_TASK_WORKER_ENABLED PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION; do
  [[ -z "${!key:-}" ]] || stop ACTIVATION_FLAG_PRESENT
done
# No Docker-over-TCP/SSH, injected context, TLS or alternate Docker config.
for key in DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH DOCKER_CONFIG; do
  [[ -z "${!key:-}" ]] || stop DOCKER_ENV_OVERRIDE
done

[[ "${HOME:-}" == /* && "$HOME" != /mnt/* && "$HOME" != *:* &&
   "$HOME" != *$'\n'* ]] || stop HOST_HOME_UNSAFE
[[ ! -L "$HOME/.docker" ]] || stop DOCKER_HOME_SYMLINK
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)" ||
  stop SOURCE_ROOT_UNAVAILABLE
[[ "$ROOT" == /* && "$ROOT" != /mnt/* && ! -L "$ROOT/scripts" &&
   ! -L "$ROOT/config" && ! -L "$ROOT/.ddev" ]] || stop SOURCE_ROOT_UNSAFE

# No git checkout, remote fetch, status refresh, write or hook invocation.
repo_root="$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null)" ||
  stop SOURCE_GIT_UNAVAILABLE
[[ "$repo_root" == "$ROOT" ]] || stop SOURCE_GIT_IDENTITY
origin="$(git -C "$ROOT" remote get-url origin 2>/dev/null)" ||
  stop SOURCE_REMOTE_MISSING
case "$origin" in
  https://github.com/sonvhse06072/personal-coding-platform.git|\
  git@github.com:sonvhse06072/personal-coding-platform.git) ;;
  *) stop SOURCE_REMOTE_NOT_CANONICAL ;;
esac
head="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null)" || stop SOURCE_HEAD_MISSING
[[ "$head" =~ ^[0-9a-f]{40}$ ]] || stop SOURCE_HEAD_INVALID

files=(
  "scripts/pcp-local-gate-a-inspect.sh"
  "config/projects.pcp-local.yml"
  "config/project-baselines.pcp-local.yml"
  ".ddev/docker-compose.platform.yaml"
  ".ddev/config.yaml"
  "config/tool-versions.env"
)
for rel in "${files[@]}"; do
  [[ -f "$ROOT/$rel" && ! -L "$ROOT/$rel" ]] ||
    stop SOURCE_FILE_UNSAFE
  expected="$(git -C "$ROOT" rev-parse "HEAD:$rel" 2>/dev/null)" ||
    stop SOURCE_FILE_NOT_TRACKED
  observed="$(git -C "$ROOT" hash-object -- "$ROOT/$rel" 2>/dev/null)" ||
    stop SOURCE_FILE_UNHASHABLE
  [[ "$expected" =~ ^[0-9a-f]{40}$ && "$observed" == "$expected" ]] ||
    stop SOURCE_FILE_DRIFT
done

# Only conservative checks against reviewed source. YAML is NOT parsed and
# these substrings can never authorize live registration or a worker.
grep -Fxq '  pcp-local:' "$ROOT/config/projects.pcp-local.yml" ||
  stop DRAFT_PROJECT_MISSING
grep -Fxq '    path: null' "$ROOT/config/projects.pcp-local.yml" ||
  stop DRAFT_PROJECT_PATH_NOT_NULL
grep -Fxq '    active_revision: null' \
  "$ROOT/config/project-baselines.pcp-local.yml" ||
  stop DRAFT_BASELINE_NOT_INACTIVE
grep -Fxq '    revisions: {}' \
  "$ROOT/config/project-baselines.pcp-local.yml" ||
  stop DRAFT_BASELINE_REVISIONS_PRESENT
grep -Fq '/config/projects.yml' "$ROOT/.ddev/docker-compose.platform.yaml" ||
  stop LEGACY_COMPOSE_LAYOUT_CHANGED
grep -Fq '${HOST_HOME}/.codex' "$ROOT/.ddev/docker-compose.platform.yaml" ||
  stop HOST_CREDENTIAL_MOUNT_LAYOUT_CHANGED
grep -Fq '/var/run/docker.sock:/var/run/docker.sock' \
  "$ROOT/.ddev/docker-compose.platform.yaml" ||
  stop EXECUTOR_SOCKET_LAYOUT_CHANGED
grep -Fq 'pcp-build-images.sh' "$ROOT/.ddev/config.yaml" ||
  stop DDEV_MUTATING_HOOK_LAYOUT_CHANGED

# Unix-local *metadata* only: do not enumerate containers, volumes, images,
# projects, jobs, mounts or daemon storage, including on a shared host.
[[ "$(uname -s 2>/dev/null)" == "Linux" ]] || stop TARGET_NOT_LINUX
kernel="$(uname -r 2>/dev/null)" || stop KERNEL_UNAVAILABLE
[[ -n "$kernel" && "$kernel" != *$'\n'* ]] || stop KERNEL_INVALID
kernel_class="LINUX_OTHER_UNATTESTED"
if [[ "${kernel,,}" == *microsoft* ]]; then
  kernel_class="WSL_KERNEL_UNATTESTED"
fi

context="$(docker context show 2>/dev/null)" || stop DOCKER_CONTEXT_UNAVAILABLE
[[ "$context" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$ ]] ||
  stop DOCKER_CONTEXT_UNSAFE
endpoint="$(docker context inspect "$context" --format \
  '{{.Endpoints.docker.Host}}' 2>/dev/null)" ||
  stop DOCKER_ENDPOINT_UNAVAILABLE
case "$endpoint" in
  unix:///var/run/docker.sock) ;;
  unix:///run/user/*/docker.sock)
    [[ "$endpoint" =~ ^unix:///run/user/[0-9]+/docker\.sock$ ]] ||
      stop DOCKER_ENDPOINT_NOT_LOCAL ;;
  *) stop DOCKER_ENDPOINT_NOT_LOCAL ;;
esac
metadata="$(docker info --format \
  '{{.ID}}|{{.OperatingSystem}}|{{.ServerVersion}}' 2>/dev/null)" ||
  stop DOCKER_METADATA_UNAVAILABLE
[[ -n "$metadata" && "$metadata" != *$'\n'* &&
   "$metadata" != *$'\r'* ]] || stop DOCKER_METADATA_INVALID
IFS='|' read -r daemon_id daemon_os daemon_version extra <<< "$metadata"
[[ -z "$extra" && "$daemon_id" =~ ^[a-zA-Z0-9:._-]{8,200}$ &&
   -n "$daemon_os" && "$daemon_version" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)? ]] ||
  stop DOCKER_METADATA_INVALID
[[ "${daemon_os,,}" != *docker*desktop* ]] || stop DOCKER_DESKTOP_SHARED

# Fingerprint is derived only from bounded daemon metadata. It is a correlation
# hint, NOT third-party attestation that the daemon is exclusive or pristine.
fingerprint="$(printf '%s' "$daemon_id|$endpoint" | sha256sum)"
fingerprint="${fingerprint%% *}"
[[ "$fingerprint" =~ ^[0-9a-f]{64}$ ]] || stop DAEMON_FINGERPRINT_INVALID

printf 'PCP_GATE_A_SOURCE_HEAD=%s\n' "$head"
printf 'PCP_GATE_A_KERNEL_CLASS=%s\n' "$kernel_class"
printf 'PCP_GATE_A_DOCKER_SCOPE=UNIX_LOCAL_METADATA_ONLY\n'
printf 'PCP_GATE_A_DAEMON_FINGERPRINT_SHA256=%s\n' "$fingerprint"
printf 'PCP_GATE_A_SOURCE_STATUS=REVIEWED_FILES_UNMODIFIED\n'
printf 'PCP_GATE_A_LEGACY_COMPOSE=UNSAFE_NOT_STARTED\n'
# Metadata from one daemon cannot independently prove absence of historic
# projects, shared daemon backing storage, credential mounts or privileges.
stop PHYSICAL_ISOLATION_NOT_ATTESTED
