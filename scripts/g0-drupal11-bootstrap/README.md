# PCP G0 Drupal 11 fixture bootstrap bundle

This bundle is **prepared in this ChatGPT session**, independent of Codex. It does **not** contain Drupal Core, vendor packages, a Composer lock, a deployed DDEV container, or a ready GitHub repository. Official Drupal Core and dependencies are installed only when `bootstrap.sh` runs against an empty, named fixture target on WSL.

The bootstrap script is fail-closed, one-use and only writes inside `$HOME/pcp-g0-fixtures/pcp-g0-drupal-fixture`. It checks the DDEV JSON registry and the unique DDEV name, will not overwrite an existing path, and will REFUSE any local DDEV start while Chợ Nhạc or another project is active. This strict gate is intentional: DDEV projects share router resources, so no user WSL startup is authorized while Chợ Nhạc is running. It does not sync/restart PCP.

Review the script first. Run `bash bootstrap.sh` only on a SEPARATELY ISOLATED runner/VM or once DDEV lists no other active project and the Owner explicitly confirms a safe maintenance window. Do not stop or restart Chợ Nhạc to satisfy the gate. A successful result includes actual Drupal Core, Composer lock, Unit/Kernel tests, PHPCS, a local seed Git commit, and optional private `sonvhse06072/pcp-g0-drupal-fixture` GitHub repository if GitHub CLI is already authenticated. On failure, it leaves only its new fixture for diagnosis and stops rather than retrying.

Owner decision: https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6094931078
