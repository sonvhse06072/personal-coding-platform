#!/usr/bin/env bash
# G0D-01: bootstrap one new, non-production Drupal 11 fixture. Never touch Chợ Nhạc.
set -Eeuo pipefail

fail() { printf 'G0D-01 STOP: %s\n' "$*" >&2; exit 2; }
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
[[ -n "${HOME:-}" && -d "$HOME" ]] || fail 'HOME is not a directory'
PARENT="$HOME/pcp-g0-fixtures"
TARGET="$PARENT/pcp-g0-drupal-fixture"
PROJECT='pcp-g0-drupal-fixture'
REMOTE='sonvhse06072/pcp-g0-drupal-fixture'

# Abort BEFORE any user-machine mutation if our single allowed target collides.
[[ ! -e "$TARGET" && ! -L "$TARGET" ]] || fail 'Fixture target already exists; refuse overwrite'
[[ ! -L "$PARENT" ]] || fail 'Parent is a symlink; refuse'
[[ ! -e "$PARENT" || -d "$PARENT" ]] || fail 'Parent is not a directory'
[[ ! -e "$PARENT" || "$(cd "$PARENT" && pwd -P)" == "$PARENT" ]] || fail 'Parent canonical path mismatch'
[[ "$(id -u)" != 0 ]] || fail 'Run as the regular WSL user, not root'
for tool in ddev git python3; do
  command -v "$tool" >/dev/null 2>&1 || fail "Missing required tool: $tool"
done
[[ -d "$BASE/template" && -f "$BASE/check_ddev_name.py" ]] || fail 'Fixture overlay templates or parser unavailable'
case "$BASE/" in
  "$HOME/chonhac/"*|"$HOME/.coding-platform/"*) fail 'Do not run the fixture bundle from a managed project/workspace' ;;
esac
if [[ -d "$HOME/personal-coding-platform-v1/.git" ]]; then
  # Read PCP state, do not fetch/pull/checkout or alter its checkout.
  [[ -z "$(git --no-optional-locks -C "$HOME/personal-coding-platform-v1" status --porcelain=v1)" ]] || fail 'PCP Git checkout is dirty; stop before build'
fi
[[ -n "$(git config --get user.name || :)" ]] || fail 'Git author name missing'
[[ -n "$(git config --get user.email || :)" ]] || fail 'Git author email missing'

# Read project registry once; fail if the name is in use OR an unrelated
# DDEV project is active. Never start a fixture beside Chợ Nhạc on one router.
DDEV_JSON="$(ddev list --json)" || fail 'Cannot read DDEV registered projects'
if ! printf '%s' "$DDEV_JSON" | python3 "$BASE/check_ddev_name.py" "$PROJECT"
then
  fail 'DDEV registry unavailable, collision, or other active project; no fixture created'
fi

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  if gh repo view "$REMOTE" >/dev/null 2>&1; then
    fail 'GitHub target repository already exists; refuse to modify it'
  fi
fi

# Bounded allowed mutation starts here, confined to this one new fixture directory.
mkdir -p -- "$PARENT"
mkdir -- "$TARGET" || fail 'Cannot create unique fixture target'
cd -- "$TARGET"
printf 'G0D-01: starting new fixture at %s\n' "$TARGET"
ddev config --project-name="$PROJECT" --project-type=drupal11 --docroot=web --php-version=8.4
ddev start -y
ddev composer create-project 'drupal/recommended-project:^11'
ddev composer require --dev 'drupal/coder:^8'
# Never overwrite user files: target was initially nonexistent and is only created here.
mkdir -p web/modules/custom
cp -R -- "$BASE/template/web/modules/custom/pcp_g0_fixture" web/modules/custom/
mkdir -p .github/workflows
cp -- "$BASE/template/.github/workflows/validation.yml" .github/workflows/validation.yml
cp -- "$BASE/template/PROJECT-BASELINE.md" PROJECT-BASELINE.md
cp -- "$BASE/template/README-FIXTURE.md" README.md
cat -- "$BASE/template/.gitignore.extra" >> .gitignore

# Real checks; failed verification always stops execution.
ddev composer validate --strict
for file in web/modules/custom/pcp_g0_fixture/src/EventLabelNormalizer.php \
            web/modules/custom/pcp_g0_fixture/tests/src/Unit/EventLabelNormalizerTest.php \
            web/modules/custom/pcp_g0_fixture/tests/src/Kernel/EventLabelServiceTest.php; do
  ddev exec php -l "$file"
done
ddev exec vendor/bin/phpcs --standard=Drupal web/modules/custom/pcp_g0_fixture
ddev exec bash -lc "export SIMPLETEST_DB='mysql://db:db@db/db'; export SIMPLETEST_BASE_URL='http://web'; vendor/bin/phpunit -c web/core/phpunit.xml.dist web/modules/custom/pcp_g0_fixture/tests/src/Unit"
ddev exec bash -lc "export SIMPLETEST_DB='mysql://db:db@db/db'; export SIMPLETEST_BASE_URL='http://web'; vendor/bin/phpunit -c web/core/phpunit.xml.dist web/modules/custom/pcp_g0_fixture/tests/src/Kernel"
[[ -f composer.lock ]] || fail 'Composer lock missing'
[[ -f web/core/tests/bootstrap.php ]] || fail 'Drupal test bootstrap missing'

git init -b main
git add -A
git diff --cached --check
# Fail closed if ignored/generated secrets accidentally staged.
if git diff --cached --name-only | grep -E '(^vendor/|^web/core/|^web/sites/[^/]+/files/|\.sql(\.gz)?$|(^|/)\.env($|\.)|^web/sites/[^/]+/settings[^/]*\.php$)'; then
  fail 'Unsafe file staged for commit'
fi
git commit -m 'chore(fixture): seed isolated Drupal 11 G0 benchmark baseline'
SHA="$(git rev-parse HEAD)"
git branch benchmark/direct "$SHA"
git branch benchmark/pcp "$SHA"
[[ "$(git rev-parse benchmark/direct)" == "$SHA" ]] || fail 'Direct branch baseline mismatch'
[[ "$(git rev-parse benchmark/pcp)" == "$SHA" ]] || fail 'PCP branch baseline mismatch'
[[ -z "$(git status --porcelain=v1)" ]] || fail 'New fixture Git status is not clean'

printf 'G0D-01 LOCAL VERIFIED: seed=%s\n' "$SHA"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh repo create "$REMOTE" --private --source=. --remote=origin --push
  git push -u origin benchmark/direct benchmark/pcp
  printf 'G0D-01 GitHub seed pushed (CI NOT YET VERIFIED): https://github.com/%s\n' "$REMOTE"
else
  printf '%s\n' 'G0D-01 LOCAL_ONLY: gh CLI unavailable/unauthenticated; no remote repository created'
fi
printf 'G0D-01 local deterministic checks passed; seed=%s, GitHub CI unverified, 0 A/B trials performed\n' "$SHA"
