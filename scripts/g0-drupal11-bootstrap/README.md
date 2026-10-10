# PCP G0 Drupal 11 fixture bootstrap bundle

This bundle is **prepared in this ChatGPT session**, independent of Codex. It does **not** contain Drupal Core, vendor packages, a Composer lock, a deployed DDEV container, or a ready GitHub repository. Official Drupal Core and dependencies are installed only when `bootstrap.sh` runs against an empty, named fixture target on WSL.

The bootstrap script is fail-closed, one-use and only writes inside `$HOME/pcp-g0-fixtures/pcp-g0-drupal-fixture`. It checks the DDEV JSON registry and the unique DDEV name, will not overwrite an existing path, and will REFUSE any local DDEV start while Chợ Nhạc or another project is active. This strict gate is intentional: DDEV projects share router resources, so no user WSL startup is authorized while Chợ Nhạc is running. It does not sync/restart PCP.

Review the script first. Run `bash bootstrap.sh` only on a SEPARATELY ISOLATED runner/VM or once DDEV lists no other active project and the Owner explicitly confirms a safe maintenance window. Do not stop or restart Chợ Nhạc to satisfy the gate. A successful result includes actual Drupal Core, Composer lock, Unit/Kernel tests, PHPCS, a local seed Git commit, and optional private `sonvhse06072/pcp-g0-drupal-fixture` GitHub repository if GitHub CLI is already authenticated. On failure, it leaves only its new fixture for diagnosis and stops rather than retrying.

Owner decision: https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6094931078

**v3 correction (2026-10-10):** A first isolated GitHub-hosted trial of v2 found `ddev list --json` unsupported by DDEV 1.25.4. v3 uses `ddev list -j` and has a regression gate. Keep previous archives obsolete. A hosted validation job must still demonstrate actual Drupal Unit/Kernel/Composer/PHPCS results; PHP lint/offline-only success is not enough.

**v4 correction (2026-10-10):** The isolated Drupal 11.4.9 runner installed Composer and Coder successfully, but PHPCS rejected namespaced class files starting with `@file`. v4 removes those docblocks and adds a dedicated regression. Real Kernel/Unit verification remains pending on a new hosted run. Previous v1-v3 ZIPs are obsolete.

**v5 correction (2026-10-10):** Require Drupal core-dev test dependencies and assert `vendor/bin/phpunit` exists. The preceding hosted run passed Composer/PHPCS but could not start PHPUnit without core-dev. Real Unit/Kernel acceptance still requires a fresh hosted proof. All v1-v4 ZIPs are obsolete.

**v6 correction (2026-10-10):** Allow Composer to reconcile locked development packages only within this fresh fixture using `--with-all-dependencies`, per the exact GitHub-hosted Composer solver error. Real Drupal Unit/Kernel evidence is still required; older v1-v5 ZIPs are obsolete.
