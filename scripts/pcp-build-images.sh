#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILDER="pcp-builder"
BUILDX_STATE="${PCP_BUILDX_CONFIG:-${HOST_HOME:-$HOME}/.coding-platform/buildx}"

ROUTER_IMAGE="personal-coding-platform-router:local"
RUNTIME_IMAGE="personal-coding-platform-coding-runtime:local"
EXECUTOR_IMAGE="personal-coding-platform-ddev-executor:local"

TOOL_VERSIONS_FILE="${PCP_TOOL_VERSIONS_FILE:-$ROOT/config/tool-versions.env}"
[[ -f "$TOOL_VERSIONS_FILE" ]] || {
  echo "Missing tool-version contract: $TOOL_VERSIONS_FILE" >&2
  exit 20
}
PINNED_CODEX_VERSION="$(
  awk -F= '$1 == "CODEX_VERSION" {print $2; exit}' "$TOOL_VERSIONS_FILE"
)"
[[ "$PINNED_CODEX_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.]+)?$ ]] || {
  echo "Invalid pinned CODEX_VERSION in $TOOL_VERSIONS_FILE" >&2
  exit 20
}
CODEX_VERSION="${CODEX_VERSION:-$PINNED_CODEX_VERSION}"
OPENCODE_VERSION="${OPENCODE_VERSION:-latest}"
DDEV_UID="${DDEV_UID:-$(id -u)}"
DDEV_GID="${DDEV_GID:-$(id -g)}"
DDEV_EXECUTOR_VERSION="${DDEV_EXECUTOR_VERSION:-v1.25.4}"
DDEV_EXECUTOR_BUILDX_VERSION="${DDEV_EXECUTOR_BUILDX_VERSION:-v0.37.0}"

mkdir -p "$BUILDX_STATE"

buildx() {
  BUILDX_CONFIG="$BUILDX_STATE" docker buildx "$@"
}

if ! buildx inspect "$BUILDER" >/dev/null 2>&1; then
  buildx create \
    --name "$BUILDER" \
    --driver docker-container \
    >/dev/null
fi

builder_info="$(buildx inspect --bootstrap "$BUILDER")"
builder_driver="$(awk -F': *' '$1 == "Driver" {print $2; exit}' <<<"$builder_info")"
if [[ "$builder_driver" != "docker-container" ]]; then
  echo "Refusing PCP build: $BUILDER uses driver '$builder_driver', expected docker-container." >&2
  exit 20
fi

buildx build \
  --builder "$BUILDER" \
  --load \
  --tag "$ROUTER_IMAGE" \
  "$ROOT/services/router"

buildx build \
  --builder "$BUILDER" \
  --load \
  --tag "$RUNTIME_IMAGE" \
  --build-arg "CODEX_VERSION=$CODEX_VERSION" \
  --build-arg "OPENCODE_VERSION=$OPENCODE_VERSION" \
  --build-arg "DDEV_UID=$DDEV_UID" \
  --build-arg "DDEV_GID=$DDEV_GID" \
  "$ROOT/services/runtime"

buildx build \
  --builder "$BUILDER" \
  --load \
  --tag "$EXECUTOR_IMAGE" \
  --build-arg "DDEV_VERSION=$DDEV_EXECUTOR_VERSION" \
  --build-arg "BUILDX_VERSION=$DDEV_EXECUTOR_BUILDX_VERSION" \
  --build-arg "DDEV_UID=$DDEV_UID" \
  --build-arg "DDEV_GID=$DDEV_GID" \
  "$ROOT/services/ddev-executor"

for image in "$ROUTER_IMAGE" "$RUNTIME_IMAGE" "$EXECUTOR_IMAGE"; do
  docker image inspect "$image" >/dev/null
done

echo "PCP_IMAGE_BUILD=PASS"
echo "PCP_CODEX_VERSION=$CODEX_VERSION"
echo "PCP_CODEX_PINNED_VERSION=$PINNED_CODEX_VERSION"
echo "PCP_BUILDER=$BUILDER"
echo "PCP_BUILDER_DRIVER=$builder_driver"
echo "PCP_BUILDX_CONFIG=$BUILDX_STATE"
