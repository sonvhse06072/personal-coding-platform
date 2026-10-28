#!/bin/sh
# Immutable image input: works when the private /tmp mount is noexec.
case "${1:-}" in
  *Username*) printf '%s\n' 'x-access-token' ;;
  *Password*) printf '%s\n' "${GITHUB_DELIVERY_TOKEN:-}" ;;
  *) exit 1 ;;
esac
