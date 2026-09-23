#!/usr/bin/env bash
set -uo pipefail

WORKSPACES_ROOT="${CODING_WORKSPACES_ROOT:-$HOME/.coding-platform/workspaces}"

section() {
  printf '\n== %s ==\n' "$1"
}

section "Docker aggregate disk usage"
docker system df || true

section "PCP platform containers"
docker ps -a --size \
  --filter "name=ddev-personal-coding-platform" \
  --format 'ID={{.ID}} NAME={{.Names}} STATUS={{.Status}} SIZE={{.Size}}' || true

section "PCP-managed workspace DDEV containers"
docker ps -a --size \
  --filter "label=com.ddev.site-name" \
  --format '{{.Label "com.ddev.site-name"}}|{{.ID}}|{{.Names}}|{{.Status}}|{{.Size}}' \
  | awk -F'|' '$1 ~ /^cp-/ {print "PROJECT="$1" ID="$2" NAME="$3" STATUS="$4" SIZE="$5}' \
  || true

section "Dangling images"
docker image ls \
  --filter dangling=true \
  --format 'ID={{.ID}} CREATED={{.CreatedSince}} SIZE={{.Size}}' || true

section "PCP/DDEV-named images"
docker image ls \
  --format '{{.Repository}}|{{.Tag}}|{{.ID}}|{{.CreatedSince}}|{{.Size}}' \
  | awk -F'|' '$1 ~ /(personal-coding-platform|ddev)/ {print "REPO="$1" TAG="$2" ID="$3" CREATED="$4" SIZE="$5}' \
  || true

section "Buildx cache usage"
if docker buildx version >/dev/null 2>&1; then
  docker buildx du || true
else
  echo "docker buildx is unavailable"
fi

section "PCP/DDEV candidate volumes"
docker volume ls \
  --format '{{.Name}}' \
  | grep -E '(^|[-_])(cp-|personal-coding-platform|ddev)' \
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
