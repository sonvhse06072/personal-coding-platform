#!/usr/bin/env bash
# GH-815 local preparation. No service start, registration, worker or cleanup.
set -euo pipefail
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
MODE=--dry-run
INSTALL_ROOT= INSTANCE= APPROVAL= EXPECTED_HEAD= NODE_BASE= PYTHON_BASE= OPENCODE= POSTGRES_IMAGE=
stop() { printf 'PCP_LOCAL_BOOTSTRAP=STOP_%s\n' "$1" >&2; exit 2; }
while (($#)); do
  case "$1" in
    --dry-run|--apply) MODE="$1"; shift ;;
    --root|--instance|--owner-approval|--source-commit|--node-base|--python-base|--opencode-version|--postgres-image)
      (($# >= 2)) || stop USAGE
      case "$1" in
        --root) INSTALL_ROOT="$2" ;; --instance) INSTANCE="$2" ;;
        --owner-approval) APPROVAL="$2" ;; --source-commit) EXPECTED_HEAD="$2" ;;
        --node-base) NODE_BASE="$2" ;; --python-base) PYTHON_BASE="$2" ;;
        --opencode-version) OPENCODE="$2" ;;
        --postgres-image) POSTGRES_IMAGE="$2" ;;
      esac
      shift 2 ;;
    *) stop USAGE ;;
  esac
done
[[ "$INSTANCE" =~ ^pcp-local-[a-z0-9][a-z0-9-]{5,30}$ ]] || stop INSTANCE_REQUIRED
# Paths are literal Compose/env values; no interpolation, spaces or traversal.
[[ "$INSTALL_ROOT" =~ ^/(home|tmp)/[a-zA-Z0-9_/-]+$ &&
   "$INSTALL_ROOT" != /home && "$INSTALL_ROOT" != /tmp &&
   "$INSTALL_ROOT" != */ && "$INSTALL_ROOT" != *//* &&
   "$INSTALL_ROOT" != "$SOURCE" && "$INSTALL_ROOT" != "$SOURCE/"* &&
   "$SOURCE" != "$INSTALL_ROOT/"* ]] || stop ROOT_UNSAFE
[[ "$(realpath -m -- "$INSTALL_ROOT")" == "$INSTALL_ROOT" ]] || stop ROOT_SYMLINK
[[ -d "$(dirname "$INSTALL_ROOT")" ]] || stop ROOT_PARENT_MISSING
[[ "$INSTALL_ROOT" == "$HOME/$INSTANCE" ]] || stop ROOT_MUST_BE_NEW_INSTANCE_IN_HOME
ORIGIN="$(git -C "$SOURCE" remote get-url origin)"
case "$ORIGIN" in
  https://github.com/sonvhse06072/personal-coding-platform.git|https://github.com/sonvhse06072/personal-coding-platform|git@github.com:sonvhse06072/personal-coding-platform.git) ;;
  *) stop REPOSITORY_IDENTITY ;;
esac
HEAD="$(git -C "$SOURCE" rev-parse HEAD)"
[[ "$HEAD" =~ ^[0-9a-f]{40}$ ]] || stop SOURCE_IDENTITY
CODEX="$(sed -n 's/^CODEX_VERSION=//p' "$SOURCE/config/tool-versions.env")"
[[ "$CODEX" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || stop CODEX_PIN
for service in router runtime ddev-executor; do
  [[ -f "$SOURCE/services/$service/Dockerfile" ]] || stop SOURCE_INCOMPLETE
done
printf '%s\n' "REPOSITORY=sonvhse06072/personal-coding-platform" "SOURCE_COMMIT=$HEAD" \
  "INSTANCE=$INSTANCE" "INSTALL_ROOT=$INSTALL_ROOT" "CODEX_VERSION=$CODEX"
for service in router runtime ddev-executor; do
  printf 'IMAGE=%s-%s:%s\n' "$INSTANCE" "$service" "$HEAD"
done
printf '%s\n' 'SERVICES=router,coding-runtime,ddev-executor; PostgreSQL=db (native Compose)' \
  'REGISTRATION=DRAFT; BASELINE=INACTIVE; SERVICES=OFF; CODEX_LIVE=STOP' \
  'ROLLBACK=preserve root, images, logs and data; no automatic deletion or restart'
if [[ "$MODE" == --dry-run ]]; then
  # No Docker/DDEV calls, writes, credential reads or live inventory in planning.
  [[ ! -e "$INSTALL_ROOT" && ! -L "$INSTALL_ROOT" ]] || stop ROOT_EXISTS
  echo 'PCP_LOCAL_BOOTSTRAP=PLAN_ONLY; RESOURCE_COLLISIONS=NOT_CHECKED'
  exit 0
fi
# This records a separate physical delegation, NOT the SOURCE approval in #815.
[[ "$APPROVAL" =~ ^https://github.com/sonvhse06072/personal-coding-platform/issues/[0-9]+#issuecomment-[0-9]+$ &&
   "$EXPECTED_HEAD" == "$HEAD" ]] || stop PHYSICAL_APPROVAL_AND_EXACT_HEAD_REQUIRED
[[ "$APPROVAL" != *'#issuecomment-6438475541' &&
   "$APPROVAL" != *'#issuecomment-6438904126' &&
   "$APPROVAL" != *'#issuecomment-6440446016' &&
   "$APPROVAL" != *'#issuecomment-6443075044' &&
   "$APPROVAL" != *'#issuecomment-6446718577' &&
   "$APPROVAL" != *'#issuecomment-6447953456' ]] || stop SOURCE_APPROVAL_IS_NOT_PHYSICAL
[[ "$NODE_BASE" =~ ^node:22-bookworm-slim@sha256:[0-9a-f]{64}$ &&
   "$PYTHON_BASE" =~ ^python:3\.13(\.[0-9]+)?-slim-bookworm@sha256:[0-9a-f]{64}$ &&
   "$OPENCODE" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ &&
   "$POSTGRES_IMAGE" =~ ^postgres:17(\.[0-9]+)?-bookworm@sha256:[0-9a-f]{64}$ ]] || stop BUILD_PINS_REQUIRED
[[ "$(id -u)" != 0 ]] || stop ROOT_USER
[[ -z "$(git -C "$SOURCE" status --porcelain --untracked-files=all)" ]] || stop SOURCE_DIRTY
# Reject ambient controls rather than silently build/use another daemon/profile.
for key in DOCKER_HOST DOCKER_CONTEXT DOCKER_CONFIG DOCKER_TLS_VERIFY COMPOSE_FILE \
  COMPOSE_PROJECT_NAME COMPOSE_PROFILES DDEV_APPROOT DDEV_SITENAME DDEV_GLOBAL_CONFIG \
  BUILDX_BUILDER BUILDX_CONFIG PCP_LOCAL_TASK_SOURCE_ENABLED PCP_LOCAL_TASK_WORKER_ENABLED \
  PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION; do
  [[ -z "${!key:-}" ]] || stop AMBIENT_OVERRIDE
done
RECEIPT="$(printf '%s\n' "$HEAD" "$INSTALL_ROOT" "$INSTANCE" "$APPROVAL" "$NODE_BASE" "$PYTHON_BASE" "$OPENCODE" "$POSTGRES_IMAGE" "$(id -u):$(id -g)" | sha256sum | cut -d' ' -f1)"
if [[ -e "$INSTALL_ROOT" || -L "$INSTALL_ROOT" ]]; then
  # Exact completed retry is a read-only no-op, never a rebuild/restart.
  [[ -d "$INSTALL_ROOT" && ! -L "$INSTALL_ROOT" &&
     -f "$INSTALL_ROOT/prepared" && ! -L "$INSTALL_ROOT/prepared" &&
     "$(cat "$INSTALL_ROOT/prepared")" == "$RECEIPT" ]] || stop EXISTING_OR_PARTIAL_ROOT
  echo 'PCP_LOCAL_BOOTSTRAP=ALREADY_PREPARED; NO_ACTION; HEALTH=NOT_ATTESTED'
  exit 0
fi
for exe in docker tar stat; do command -v "$exe" >/dev/null || stop "MISSING_$exe"; done
# An ambient selected Docker context must not redirect local preparation.
docker() { command docker --host unix:///var/run/docker.sock "$@"; }
# Only exact instance namespace metadata is requested. Never inspect consumers,
# change the selected builder, or adopt existing/stopped resources.
empty_inventory() {
  local found
  found="$(docker "$@")" || stop RESOURCE_QUERY_FAILED
  [[ -z "$found" ]] || stop RESOURCE_COLLISION
}
empty_inventory ps -aq --filter "name=^/${INSTANCE}-"
empty_inventory volume ls -q --filter "name=${INSTANCE}"
empty_inventory network ls -q --filter "name=${INSTANCE}"
for service in router runtime ddev-executor; do
  empty_inventory image ls -q --filter "reference=${INSTANCE}-${service}:*"
done
SOCKET_GID="$(stat -c '%g' /var/run/docker.sock)" || stop SOCKET_UNAVAILABLE
[[ "$SOCKET_GID" =~ ^[0-9]+$ ]] || stop SOCKET_GROUP
umask 077
# Atomic claim serializes bootstrap retries for this root. A partial failure is
# retained for diagnosis; traps deliberately do not delete or stop anything.
mkdir -- "$INSTALL_ROOT" || stop ROOT_RACE
trap 'if [[ ! -f "$INSTALL_ROOT/prepared" ]]; then printf "PCP_LOCAL_BOOTSTRAP=PARTIAL_STOP; PRESERVE_ROOT_AND_IMAGES\n" >&2; fi' EXIT
mkdir -p "$INSTALL_ROOT"/{build,logs,sources,workspaces,runtime-home,executor-home,instance,instance/config,instance/initdb}
printf '%s\n' "$RECEIPT" > "$INSTALL_ROOT/intent"
git -C "$SOURCE" archive "$HEAD" services/router services/runtime services/ddev-executor | tar -x -C "$INSTALL_ROOT/build"
# Build from committed service-only inputs, never from host secrets or .ddev.
for service in router runtime ddev-executor; do
  context="$INSTALL_ROOT/build/services/$service"
  [[ -z "$(find "$context" -type l -print -quit)" ]] || stop BUILD_SYMLINK
  case "$service" in runtime) base="$NODE_BASE" ;; *) base="$PYTHON_BASE" ;; esac
  sed "1cFROM $base" "$context/Dockerfile" > "$context/Dockerfile.local"
  image="${INSTANCE}-${service}:${HEAD}"
  docker build --builder default --file "$context/Dockerfile.local" --tag "$image" \
    --iidfile "$INSTALL_ROOT/logs/$service.iid" \
    --label "org.opencontainers.image.revision=$HEAD" \
    --label "org.pcp.local.instance=$INSTANCE" \
    --build-arg "CODEX_VERSION=$CODEX" --build-arg "OPENCODE_VERSION=$OPENCODE" \
    --build-arg "DDEV_UID=$(id -u)" --build-arg "DDEV_GID=$(id -g)" \
    "$context" > "$INSTALL_ROOT/logs/$service.build.log" 2>&1
  [[ "$(cat "$INSTALL_ROOT/logs/$service.iid")" =~ ^sha256:[0-9a-f]{64}$ ]] || stop BUILD_ID_MISSING
done
# No GitHub credentials or network required to create the local source clone.
git -c core.hooksPath=/dev/null clone --no-local --no-hardlinks "$SOURCE" "$INSTALL_ROOT/sources/personal-coding-platform" > "$INSTALL_ROOT/logs/source.log" 2>&1
git -C "$INSTALL_ROOT/sources/personal-coding-platform" -c core.hooksPath=/dev/null checkout --detach "$HEAD" >> "$INSTALL_ROOT/logs/source.log" 2>&1
git -C "$INSTALL_ROOT/sources/personal-coding-platform" remote set-url origin https://github.com/sonvhse06072/personal-coding-platform.git
for name in projects.pcp-local.yml project-baselines.pcp-local.yml models.yml routing-policy.yml; do
  git -C "$SOURCE" show "$HEAD:config/$name" > "$INSTALL_ROOT/instance/config/$name"
done
git -C "$SOURCE" show "$HEAD:profiles/pcp-local/docker-compose.local.yaml" > "$INSTALL_ROOT/instance/docker-compose.local.yaml"
cat > "$INSTALL_ROOT/instance/.env" <<ENV
PCP_LOCAL_ROOT=$INSTALL_ROOT
PCP_LOCAL_INSTANCE=$INSTANCE
PCP_LOCAL_SOURCE_COMMIT=$HEAD
PCP_LOCAL_UID=$(id -u)
PCP_LOCAL_GID=$(id -g)
PCP_LOCAL_ROUTER_IMAGE=$(cat "$INSTALL_ROOT/logs/router.iid")
PCP_LOCAL_RUNTIME_IMAGE=$(cat "$INSTALL_ROOT/logs/runtime.iid")
PCP_LOCAL_EXECUTOR_IMAGE=$(cat "$INSTALL_ROOT/logs/ddev-executor.iid")
PCP_LOCAL_POSTGRES_IMAGE=$POSTGRES_IMAGE
PCP_LOCAL_DOCKER_GID=$SOCKET_GID
COMPOSE_PROFILES=
ENV
# Fresh internal service tokens only. Provider/GitHub credentials are NOT copied
# or provisioned. Python is supplied by the newly built Runtime, not the host.
docker run --rm --pull=never --network=none --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges --user "$(id -u):$(id -g)" \
  --cpus=0.25 --memory=128m --pids-limit=64 --env HOME=/tmp --tmpfs /tmp:rw,nosuid,nodev,size=16777216 \
  --mount "type=bind,source=$INSTALL_ROOT/instance,target=/output" \
  "$(cat "$INSTALL_ROOT/logs/runtime.iid")" python3 -c '
import os, secrets
router, runtime, executor, admin, database = (secrets.token_hex(32) for _ in range(5))
files = {
    "router": {"ROUTER_API_TOKEN": router},
    "coding-runtime": {"ROUTER_API_TOKEN": router, "RUNTIME_API_TOKEN": runtime, "PLATFORM_INTERNAL_TOKEN": executor,
        "DATABASE_URL": "postgresql://pcp_runtime:" + database + "@db:5432/pcp_local"},
    "db": {"POSTGRES_USER": "pcp_bootstrap", "POSTGRES_DB": "pcp_local", "POSTGRES_PASSWORD": admin},
    "ddev-executor": {"PLATFORM_INTERNAL_TOKEN": executor},
}
for service, values in files.items():
    fd = os.open("/output/.env." + service + ".local", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write("".join(key + "=" + value + "\n" for key, value in values.items()))
# The PostgreSQL image runs as its own non-root UID, so this sole non-secret-
# directory traversal is intentional. Only DB can mount the SQL with role secret.
os.chmod("/output/initdb", 0o755)
fd = os.open("/output/initdb/01-runtime.sql", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
with os.fdopen(fd, "w") as out:
    out.write("CREATE ROLE pcp_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD "
        + chr(39) + database + chr(39) + ";\n"
        + "ALTER DATABASE pcp_local OWNER TO pcp_runtime;\n"
        + "ALTER SCHEMA public OWNER TO pcp_runtime;\n")
os.chmod("/output/initdb/01-runtime.sql", 0o644)
'
for service in router coding-runtime ddev-executor db; do
  file="$INSTALL_ROOT/instance/.env.$service.local"
  [[ -s "$file" && ! -L "$file" && "$(stat -c '%a' "$file")" == 600 ]] || stop SERVICE_ENV_INCOMPLETE
done
printf '%s\n' "$HEAD" "$NODE_BASE" "$PYTHON_BASE" "CODEX_VERSION=$CODEX" "OPENCODE_VERSION=$OPENCODE" "$POSTGRES_IMAGE" > "$INSTALL_ROOT/logs/build-inputs"
printf '%s\n' "$RECEIPT" > "$INSTALL_ROOT/prepared"
echo 'PCP_LOCAL_BOOTSTRAP=PREPARED; COMPOSE_START=NOT_RUN; BASELINE=INACTIVE; CODEX_LIVE=STOP'
