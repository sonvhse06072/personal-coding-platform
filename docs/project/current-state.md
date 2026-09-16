# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-16

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md` and this file.
3. Read `docs/project/efficiency-model.md` and `docs/project/service-secret-upgrades.md` for the active #162 work.
4. Inspect the active issue/PR and current branch diff before editing.

## Current source baseline

- Efficiency initiative #146 source phases A-F are implemented. Operational proof is tracked by #162.
- PM routine in-scope merge authority is approved; Developer agents never merge and production remains Human Owner-controlled.
- Runtime target/deployed version: `1.0.44`; Router: `1.0.21`; ddev-executor: `1.0.15`; routing policy v12.
- #165/#166 established mandatory operator shell isolation for pasted blocks that can fail.
- #167/#168 fixed host-secret loading in `platform-test`.
- #169/#170 fixed local/container test portability; #171/#172 corrected the rebuild procedure required to consume baked Runtime tests.
- #173/#174 recorded successful rollout health/test/DEC-025C preservation.
- #175/#176 added a service-secret migration/status guard and documented existing-install migrate-before-restart ordering.
- `chonhac` remains `autonomy.allow_auto_merge_low_risk: false`; never enable it merely to exercise auto-merge.

## #162 rollout evidence already complete

The safety-gated rollout/rebuild completed with no active Runtime jobs, no active ddev-executor jobs and no active Antigravity runs.

Verified deployed identities before the later service-secret remediation restart:

- Antigravity host bridge `1.10`, safety settings intact;
- Router `1.0.21`, routing policy v12;
- Coding Runtime `1.0.44`;
- ddev-executor `1.0.15`, GitHub delivery configured;
- n8n healthy at that point.

`ddev platform-test` passed completely after the corrected Runtime tests were rebuilt:

- Router: `76 passed`;
- Runtime: `289 passed`;
- ddev-executor: `34 passed`.

The preserved `chonhac` DEC-025C state survived rollout unchanged. A direct read-only `cp_control_actions` query also confirmed recovery action `abXzvyU2pvALZ5YpovNveDcr` remained pending, unexpired, result null and never mutated.

Do not repeat the earlier no-cache rollout rebuild sequence unless later service-image source actually requires it.

## Active #162 blocker: #177 credential guard semantics and n8n health

The first trust-boundary check after #174 revealed that the existing local install had not previously loaded `PLATFORM_INTERNAL_TOKEN` into deployed Runtime. #175/#176 added a canonical migration/status procedure.

Human Owner then executed the #176 remediation safely:

- local platform source synced to merge `f52add265f05d19708c387e4ac67428cf15052a3`;
- fresh active-work gate passed: Antigravity `active_runs=0`, ddev-executor `active_jobs=0`, Runtime no in-flight jobs;
- `scripts/scope-service-secrets.sh` completed successfully;
- local `.env.coding-runtime.local` and `.env.ddev-executor.local` both contain a real `PLATFORM_INTERNAL_TOKEN` and the values match;
- global `.ddev/.env` has no `PLATFORM_INTERNAL_TOKEN`;
- immediate pre-restart job gate passed;
- `ddev restart` completed successfully and deployed versions remained Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`.

Two post-restart observations remain unresolved:

1. `scripts/service-secret-status.sh` reported every presence/absence boolean false. Root cause is now identified as a host-side guard bug: it used `ddev exec ... sh -lc ... sh "$variable"` and relied on a `$1` positional contract that does not survive DDEV command parsing as assumed. Both positive and negative checks therefore failed. This does **not** prove the migrated token files are wrong.
2. `ddev platform-status` reported `n8n DOWN`. Treat this independently from the guard bug. It may be startup timing or a real n8n failure; do not infer the cause without read-only health/log evidence.

Issue #177 is the active bounded follow-up. Branch `ai/fix-secret-status-177` changes the guard to pass one validated command string to `ddev exec`, never prints secret values, and adds regression coverage rejecting the broken positional-argument pattern.

After #177 merges, its host-side guard change requires only a local source fast-forward, **not** another platform rebuild. Re-run the corrected strict guard first. If n8n remains down, collect read-only n8n status/logs before considering any restart.

Phase-E `rollout` continuity event has **not** been recorded yet. The routine fixture job has **not** been created yet.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `rollout_validation_blocked_by_guard_bug_and_n8n_health`.
- Parent validation: `#162`; initiative: `#146`.
- Rollout health/tests/DEC-025C preservation: complete.
- Canonical service-secret migration: completed locally; Runtime/executor internal token files present and matching; global env clean.
- Latest restart: completed; Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`.
- Active source follow-up: `#177` fixes `service-secret-status.sh` DDEV command parsing.
- Independent operational observation: `n8n DOWN` after the remediation restart; diagnosis pending.
- Phase-E rollout event: not recorded.
- Routine `example-drupal` job: not created.
- Production deployment: not performed.
<!-- PCP:CONTINUITY:END -->

## `example-drupal` validation fixture policy

`config/projects.yml` registers `example-drupal` with:

- base branch `develop`;
- `autonomy.allow_auto_merge_low_risk: true`;
- production deploy disabled;
- DDEV preflight (`ddev start -y`, `ddev drush cr`);
- PHPCS targeted verification;
- PHPStan static analysis;
- PHPUnit full tests;
- cleanup via DDEV stop.

Local fixture existence/cleanliness/remote/baseline have not yet been proven because trust-boundary/n8n gates stopped first. If `example-drupal` is unsuitable, stop and record the blocker; never fall back to `chonhac` merely to exercise auto-merge.

## Preserved `chonhac` DEC-025C

GitHub ticket: `chonhac` GH-5.

- plan `pm-gh-5650852312`;
- WorkOrder `DEC-025C-1-recovery-tooling-r2`;
- job `eec59b13651c54559c10ce204380a68e`;
- branch `ai/eec59b13651c`;
- workspace `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`;
- status `blocked`;
- result `reassessment_stopped` / `repair budget exhausted` / `hard_budget_guard`;
- model calls `21 / 22`;
- tool calls `65 / 160`;
- test runs `14 / 14`;
- wall time `93.168 / 110` minutes;
- repair iterations `4 / 4`.

Recovery action `abXzvyU2pvALZ5YpovNveDcr` is `budget_extend` for `max_repair_iterations +1`, pending and unexpired after rollout. Do not manually mutate DB/job state, reset counters, replace this job, or backport newer semantics into it.

## Global operational gates

- Normal flow: issue -> `ai/*` branch -> deterministic tests/CI -> PR -> PM merge when eligible.
- Never force push.
- Developer agents never merge or receive GitHub delivery credentials.
- Human Owner retains protected architecture/security/production/governance authority.
- Production deployment is never implied by PR merge.
- Do not restart/rebuild Runtime/Router/ddev-executor/DDEV/n8n while any engineering job is active; require stable blocked/terminal Runtime state plus zero executor/Antigravity active work.
- Runtime durable state is authoritative; never edit DB/job state to bypass the state machine.
- Provider/control-plane credentials remain service-scoped and never enter prompts/docs/logs.
- Potentially failing Human Owner command blocks must run in a subshell or standalone script so controlled non-zero exits cannot terminate the parent Ubuntu/WSL shell.

## Immediate next safe actions

1. Complete #177 through reviewed PR/CI.
2. Human Owner fast-forwards local `main`; no rebuild is needed for the host-side guard fix.
3. Re-run `scripts/service-secret-status.sh --strict` and `ddev platform-status` without printing secret values.
4. If the corrected credential boundary passes but n8n is still down, collect read-only `ddev logs -s n8n` and container/status evidence; do not restart again until the cause is known and active-work gate is rechecked.
5. Once trust boundary and n8n are healthy, record the Phase-E `rollout` continuity event.
6. Verify local `example-drupal` repository and deterministic baseline.
7. Create exactly one small routine validation WorkOrder with deterministic non-empty diff and no manual merge.
8. Capture telemetry, Human attention, PM-merge audit and continuity evidence in #162 and #146.
