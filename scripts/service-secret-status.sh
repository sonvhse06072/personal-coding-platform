#!/usr/bin/env bash
set -uo pipefail

MODE="${1:-}"

valid_variable_name() {
  [[ "$1" =~ ^[A-Z_][A-Z0-9_]*$ ]]
}

is_present() {
  local service="$1" variable="$2" command

  if ! valid_variable_name "$variable"; then
    printf 'false'
    return
  fi

  # ddev exec interprets a single command argument through the target
  # container shell. Keep the variable name validated and never print the
  # value; only the command exit status crosses the service boundary.
  command='value="${'"$variable"'-}"; [ -n "$value" ] && [ "$value" != "CHANGE_ME" ] && [ "$value" != "change-me" ]'

  if ddev exec -s "$service" "$command" >/dev/null 2>&1; then
    printf 'true'
  else
    printf 'false'
  fi
}

is_absent() {
  local service="$1" variable="$2" command

  if ! valid_variable_name "$variable"; then
    printf 'false'
    return
  fi

  command='[ -z "${'"$variable"'-}" ]'

  if ddev exec -s "$service" "$command" >/dev/null 2>&1; then
    printf 'true'
  else
    printf 'false'
  fi
}

runtime_internal="$(is_present coding-runtime PLATFORM_INTERNAL_TOKEN)"
runtime_delivery_absent="$(is_absent coding-runtime GITHUB_DELIVERY_TOKEN)"
runtime_telegram_absent="$(is_absent coding-runtime TELEGRAM_BOT_TOKEN)"
executor_internal="$(is_present ddev-executor PLATFORM_INTERNAL_TOKEN)"
executor_delivery="$(is_present ddev-executor GITHUB_DELIVERY_TOKEN)"
executor_runtime_absent="$(is_absent ddev-executor RUNTIME_API_TOKEN)"
n8n_runtime="$(is_present n8n RUNTIME_API_TOKEN)"
n8n_delivery_absent="$(is_absent n8n GITHUB_DELIVERY_TOKEN)"
n8n_internal_absent="$(is_absent n8n PLATFORM_INTERNAL_TOKEN)"

ok=true
for value in \
  "$runtime_internal" \
  "$runtime_delivery_absent" \
  "$runtime_telegram_absent" \
  "$executor_internal" \
  "$executor_delivery" \
  "$executor_runtime_absent" \
  "$n8n_runtime" \
  "$n8n_delivery_absent" \
  "$n8n_internal_absent"
do
  if [[ "$value" != "true" ]]; then
    ok=false
  fi
done

printf '{"ok":%s,"coding_runtime":{"platform_internal_present":%s,"github_delivery_absent":%s,"telegram_bot_absent":%s},"ddev_executor":{"platform_internal_present":%s,"github_delivery_present":%s,"runtime_api_absent":%s},"n8n":{"runtime_api_present":%s,"github_delivery_absent":%s,"platform_internal_absent":%s}}\n' \
  "$ok" \
  "$runtime_internal" \
  "$runtime_delivery_absent" \
  "$runtime_telegram_absent" \
  "$executor_internal" \
  "$executor_delivery" \
  "$executor_runtime_absent" \
  "$n8n_runtime" \
  "$n8n_delivery_absent" \
  "$n8n_internal_absent"

if [[ "$MODE" == "--strict" && "$ok" != "true" ]]; then
  exit 1
fi
