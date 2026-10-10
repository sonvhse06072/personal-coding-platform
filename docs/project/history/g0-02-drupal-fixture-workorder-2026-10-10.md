# WorkOrder G0D-01 — Disposable Drupal 11 fixture bootstrap

**Decision:** [DEC-G0-FIXTURE-01 approved by Owner](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6094931078), scoped to original [proposal](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6094477546). **Tracking:** PCP [#595](https://github.com/sonvhse06072/personal-coding-platform/issues/595), program #593. **Status (2026-10-10):** ChatGPT PM has prepared a local-only bootstrap artifact with offline checks, **but has NOT executed DDEV/Composer/Drupal Unit/Kernel/CI or created the fixture repository**. The Codex WSL session is dedicated to Chợ Nhạc and is not an executor for this WorkOrder. This T3 document is an authorized execution contract, not evidence that any fixture/repository/DB exists and not authority to bypass runtime gates.

## 1. Exact stage and trust boundary

Stage **F-DRUPAL only**. Do not create F-NEXT, spawn comparator trials, dispatch PCP jobs, register ProjectBaselines, modify PCP project configuration or begin G1 as part of this WorkOrder. Deliver a **new, private, non-production Git repository** containing only official Drupal 11 recommended-project starter code and small self-authored sample module/test/CI. **No existing user project, data, Drupal DB, secret, media or project workspace may be copied or modified.**

- Reserved new directory: `$HOME/pcp-g0-fixtures/pcp-g0-drupal-fixture`.
- Proposed private GitHub repository: `sonvhse06072/pcp-g0-drupal-fixture`.
- DDEV project seed name: `pcp-g0-drupal-fixture` (check collision); Drupal type `drupal11`, PHP `8.4`, docroot `web`; empty, fixture-owned DB.
- Git root baseline branch: `main`. Later two delivery bases `benchmark/direct` and `benchmark/pcp` **must point to the same exact source baseline commit**. Do not run or merge A/B branches yet. Avoid single-branch race where one merge makes the other PR empty or changes task source.
- No global Composer/PHP/Node/Codex installation or downgrade, no unrestricted `--dangerously-bypass-approvals-and-sandbox` in PCP, no force push, production write or changing external Owner projects.
- The Owner approved fixture creation/limited future registration, **not** arbitrary Docker/socket/credential grants. Running normal DDEV within this brand-new fixture is permitted, never altering the shared Chợ Nhạc containers/volumes.

## 2. Preflight — fail closed

1. Check no existing file, symlink, directory or Git remote occupies either reserved target. If the target exists, **STOP without deleting or overwriting**. Check no DDEV project name collision. Use the current ordinary WSL user; do not acquire or print secrets.
2. Confirm DDEV >=1.25.4, Docker/DDEV availability, sufficient disk headroom, Git identity and `gh` authentication **without printing any token**. If GitHub CLI absent/unconnected, create local-only source and report remote-delivery blocker; never improvise credentials.
3. Confirm `git -C /home/sonvh/personal-coding-platform-v1 status --short` is clean/read-only. Do **not** pull, restart, checkout or alter that PCP repository in this WorkOrder. Do not touch `/home/sonvh/chonhac` or `~/.coding-platform/workspaces`.
4. Existing projects `KCCI`, `academic_management`, `cck`, `environmentaljobs`, `ipropaganda`, `lovenote`, `riebedebie`, `pcp-validation-fixture` are out of scope regardless of Git cleanliness.
5. Record start event in the local report **without exposing credentials, private paths beyond the reserved fixture, or unredacted provider usage**.

## 3. Official starter & reproducible baseline

Use <https://ddev.readthedocs.io/en/stable/users/quickstart/#drupal> and <https://www.drupal.org/docs/develop/using-composer/manage-dependencies> as the starting procedure. In the new, empty directory only:

```bash
ddev config --project-name=pcp-g0-drupal-fixture --project-type=drupal11 --docroot=web --php-version=8.4
ddev start -y
ddev composer create-project 'drupal/recommended-project:^11'
```

This is a *reference sequence*, not permission to run commands before the preflight. `ddev composer create-project` knows how to scaffold an essentially empty DDEV project. Use a stable **Drupal 11** package and **commit its generated `composer.lock`**; never leave `11.x-dev`, latest-floating npm/composer dependencies or modified Composer security controls in the final fixture. Composer 2.7+ is required for Drupal 11. Any update/Composer package install must be restricted to this new fixture.

Add only the development dependencies needed to run a real **Drupal Unit and Kernel PHPUnit** test and PHPCS. `drupal/core-dev` is the official Drupal PHPUnit dev dependency; use a compatible release, lock versions and run `ddev composer validate`. Do **not** create a fake `DrupalTestCase` namespace or substitute a plain PHP runner for Kernel acceptance. For Drupal 11 Kernel tests, apply `#[RunTestsInSeparateProcesses]` where current core requires it, and supply a dedicated disposable database connection for test execution; never use an existing project DB. Do not install a public/admin-ready website unless strictly required for the tests; Unit/Kernel should not require a preexisting site.

## 4. Initial fixture contents and *separate* future benchmark task

Within `web/modules/custom/pcp_g0_fixture` create only:
- `pcp_g0_fixture.info.yml` and `pcp_g0_fixture.services.yml` for a tiny service with no network/external dependency;
- `src/EventLabelNormalizer.php`: initial deterministic baseline handling ordinary nonempty labels and trimming outer ASCII whitespace;
- `tests/src/Unit/EventLabelNormalizerTest.php`: initial positive coverage for basic and surrounding-whitespace inputs;
- `tests/src/Kernel/EventLabelServiceTest.php`: a real bootstrapped Drupal 11 Kernel test proving the module's service is accessible, with separate-process attribute if needed.

Create a short `PROJECT-BASELINE.md` in the fixture, recording: Owner G0 decision link, goals/non-goals, source/architecture, exact test/CI acceptance, private empty-data/security/budget constraints, and next single task contract. **Task G0D-T01 is *not* part of bootstrap acceptance:** extend the normalizer to collapse runs of internal ASCII spaces/tabs/newlines to a single space, preserving already-tested cases, with both Unit + Kernel coverage. Both arms must receive the **same final approved task statement and exact initial source SHA**. Do not implement G0D-T01 during scaffolding or pre-seed its passing implementation/test and then count it as agent work. Keep files minimal and don't add Drupal contrib modules or data fixtures for unrelated cases.

Create `.github/workflows/validation.yml` **inside the new fixture only**, triggering on pull requests to all branches; test against a pinned supported PHP/Composer environment with `composer validate`, PHPCS on this module, PHP syntax, Unit+Kernel PHPUnit (no skipped/fake PASS). The fixture's CI must verify identical final acceptance gates for both `benchmark/direct` and `benchmark/pcp`. If GitHub Actions cannot run an actual Kernel test safely with an isolated DB, record a CI blocker rather than silently skipping it. Do not modify PCP's workflow.

## 5. Deterministic verification, delivery, and stop

Before publishing:
- `ddev composer validate` passes; `composer.lock` is present and consistent; Drupal Core and `Drupal\KernelTests\KernelTestBase` truly resolve; Unit and Kernel PHPUnit pass with executed assertions and 0 skipped/errored tests.
- PHPCS and PHP lint pass without `|| true` or weakened standards.
- Verify that only the fixture DDEV identity/empty DB was touched, and no sample files contain secrets or private project code. Files such as `vendor/`, `web/sites/default/files/`, untracked DB, .env keys, generated test artifacts must be excluded from Git. Never print credentials.
- Commit **one reviewable initial baseline** to local `main` with generated locks. Create local `benchmark/direct` and `benchmark/pcp` refs from the same exact commit but **do not launch trials**.
- If `gh` is safely authenticated, create only `sonvhse06072/pcp-g0-drupal-fixture` as **private** (if absent) and push those baseline refs. No extra repo, no force push. If `gh` is unavailable, **stop at local source ready**, record it as a limitation; do not ask for/store credentials.
- Avoid retries without a new diagnosis. On infrastructure/network/Composer/DDEV failure, preserve partial new fixture for inspection, describe the exact failure and stop; never auto-delete/recreate it or make a replacement project to bypass the issue.

**DoD output to Owner/PM:** private repo URL if pushed (or LOCAL_ONLY), local fixture path, initial Git commit full SHA, baseline revision candidate, installed Drupal/PHP/DDEV/Composer/Codex versions, the actual `composer.lock` presence/version, passing DDEV/Unit/Kernel/PHPCS/CI evidence, branch/ref identities, duration and resource observations; explain any blocker. Keep result concise and include **zero real A/B pairs so far**.

## 6. Explicit downstream gates — not part of this WorkOrder

After verified fixture source exists, ChatGPT PM may propose a **separate exact-source protected PR** for only:
`config/projects.yml` (new fixture ID, isolated workspace, `base_branch: benchmark/pcp`, no production deployment), and
`config/project-baselines.yml` (new approved immutable revision pointing to the exact fixture commit plus `PROJECT-BASELINE.md`).
Owner approval evidence: [#595 decision](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6094931078), with `Owner-Approval-Issue` and `Approved-Protected-Paths` in that PR description. Never overwrite existing approved baseline revisions. Required review, CI and guarded local deployment are independent gates.

Only after the registered baseline is **deployed** and clean single-writer/lease identities validated may #595 run one real PCP-vs-direct G0D-T01 trial. It must use separate checkouts/DDEV names/empty DBs, same model+reasoning/CLI+toolchain for normalized pairing. Observed host Codex `0.162.0` and Runtime Codex `0.160.0` must be captured separately and are **not** a controlled matched pair; no global CLI downgrade is authorized. Stage F-NEXT and repair follow only on first-stage safety/quality Go. **No G0 product Go and no G1 #596 permissions from fixture prep alone.**

**Official references:** <https://ddev.readthedocs.io/en/stable/users/quickstart/#drupal>, <https://docs.ddev.com/en/stable/users/usage/developer-tools/>, <https://www.drupal.org/docs/develop/automated-testing/phpunit-in-drupal/running-phpunit-tests>, <https://api.drupal.org/api/drupal/core%21tests%21Drupal%21KernelTests%21KernelTestBase.php/class/KernelTestBase/11.x>.


## 7. ChatGPT-session handoff and no-touch guard (Owner 2026-10-10)

The Human Owner explicitly requires execution to continue **inside this ChatGPT PM conversation**, not through the Codex session that is working on Chợ Nhạc. The PM **must not send any control, code changes or automation to Chợ Nhạc** during PCP fixture work, including PM Bridge/Guardian commands, Runtime jobs, DB/DDEV/preview/test/lease actions, or GitHub writes in that project. The previous blocked historical job remains untouched. This is a conversational PM execution restriction, not evidence a permanent Runtime denylist or released project lease exists.

**Artifact prepared in the ChatGPT sandbox:** `pcp-g0-drupal-bootstrap.zip`, SHA-256
`55b786eca8e1d3f3372f91d1950814314a31f9f6a6629dcc0972a119834735d8`. It contains an allowlisted new-path `bootstrap.sh` (official DDEV/Drupal 11 Composer starter), `check_ddev_name.py`, Unit + Kernel fixture PHP source/test templates, a PHP 8.4 GitHub-hosted PR CI workflow, a candidate baseline and offline regression tests. **Artifact is available in the originating ChatGPT conversation, not yet a GitHub file or an installed WSL project.**

**Executed offline evidence:** 11/11 sandbox regression tests PASS, three PHP files pass syntax lint, baseline normalizer-only PHP smoke PASS. Tests prove bounded static script behavior (existing target and symlink refuse overwrite, DDEV name collision fails closed), not actual Drupal Kernel/Coder/Composer/CI acceptance. Sandbox has PHP and Python but lacks Composer, DDEV and user WSL filesystem. Do not mislabel the fixture as bootstrapped until full real evidence exists.

**Pending local execution without Codex:** One ordinary WSL operator execution of the reviewed artifact's `bootstrap.sh` in its extracted new directory, after a DDEV name/target check. The script creates only `$HOME/pcp-g0-fixtures/pcp-g0-drupal-fixture`; no copy from existing projects, no global PCP source sync, no Chợ Nhạc actions and no project registry mutation. A new DDEV project uses shared host/router infrastructure, so confirm adequate resources and keep existing Chợ Nhạc services untouched; if strict host-wide no-disruption cannot be assured, hold local DDEV startup and use a separately isolated machine/runner.

**Availability limitation:** connected GitHub tools support repository file/branch/PR writes but do not expose a create-repository or WSL terminal operation. Therefore, the private fixture repository can only be created when authenticated `gh` runs as the User's normal WSL identity (or a separately enabled capability is connected). No model invocation, PCP benchmark job, security permission or G0 investment decision is unlocked by the offline artifact alone.
