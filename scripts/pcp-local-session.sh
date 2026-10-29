#!/bin/sh
# Exact existing Runtime container only. No startup, host interpreter or credential argv.
set -eu
if [ "$#" -lt 1 ]; then
  echo 'usage: pcp-local-session.sh FULL_CONTAINER_ID [status|readiness|finalize] --job-id ID [...]' >&2
  exit 2
fi
pcp_session_container=$1
shift
case "$pcp_session_container" in *[!0-9a-f]*|'') exit 2;; esac
[ "${#pcp_session_container}" -eq 64 ] || exit 2
unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
exec docker --host unix:///var/run/docker.sock exec "$pcp_session_container" python -m app.pcp_local_task_queue session "$@"
