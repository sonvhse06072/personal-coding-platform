#!/usr/bin/env bash
# Runs in PCP DDEV Executor (not the Chợ Nhạc web container).
# Use real raw argv for each DDEV call; never embed shell expansions in ddev exec.
set -euo pipefail

git rev-parse --verify HEAD >/dev/null

# HEAD includes both index and working-tree edits; include untracked new tests.
# The old HEAD^..HEAD CI helper would miss an active direct-workspace diff.
changed_tracked="$(git diff --name-only HEAD -- web/modules/custom)"
changed_untracked="$(git ls-files --others --exclude-standard -- web/modules/custom)"
mapfile -t modules < <(
  printf '%s\n%s\n' "$changed_tracked" "$changed_untracked" |
    awk -F/ '$1=="web" && $2=="modules" && $3=="custom" && NF>=5 {print $4}' |
    LC_ALL=C sort -u
)

if ((${#modules[@]} == 0)); then
  echo "No changed custom Drupal modules"
  exit 0
fi

# Prepare Drupal BrowserTest output inside the web container as its DDEV user.
web_uid="$(ddev exec --raw -- id -u)"
web_uid="${web_uid//$'\r'/}"
if [[ ! "$web_uid" =~ ^[0-9]{1,8}$ ]]; then
  echo "DDEV web UID cannot be verified" >&2
  exit 1
fi
output_dir="/tmp/pcp-chonhac-browser-output-$web_uid"
ddev exec --raw -- mkdir -p "$output_dir"
ddev exec --raw -- chmod 700 "$output_dir"
ddev exec --raw -- test -d "$output_dir"
ddev exec --raw -- test -w "$output_dir"

for module in "${modules[@]}"; do
  if [[ ! "$module" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "Invalid custom Drupal module path" >&2
    exit 1
  fi
  echo "Running targeted tests for $module"
  for layer in Unit Kernel Functional; do
    dir="web/modules/custom/$module/tests/src/$layer"
    [[ -d "$dir" ]] || continue

    tests=()
    mapfile -d '' -t tests < <(find "$dir" -type f -name '*Test.php' -print0)
    ((${#tests[@]} > 0)) || continue

    echo "Running $layer tests for $module"
    # Preserve the actual PHPUnit exit status; never mask a failing test.
    ddev exec --raw -- env "BROWSERTEST_OUTPUT_DIRECTORY=$output_dir" \
      vendor/bin/phpunit -c web/core/phpunit.xml.dist "${tests[@]}"
  done
done
