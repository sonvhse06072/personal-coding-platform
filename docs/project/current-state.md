# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-16

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md` and this file.
3. Read `docs/project/efficiency-model.md` and `docs/project/service-secret-upgrades.md` for active #162 work.
4. Inspect the active issue/PR and current branch diff before editing.

## Current source baseline

- Efficiency initiative #146 source phases A-F are implemented; operational proof is tracked by #162.
- PM routine in-scope merge authority is approved; Developer agents never merge and production remains Human Owner-controlled.
- Deployed platform remains Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`, routing policy v12.
- #165/#166 established mandatory operator-shell isolation for pasted blocks that can fail.
- #167/#168 fixed host-secret loading in `platform-test`.
- #169/#170 fixed local/container test portability; #171/#172 corrected the rebuild procedure for baked Runtime tests.
- #173/#174 recorded successful rollout health/test/DEC-025C preservation.
- #175/#176 added the service-secret migration/status guard and documented existing-install migrate-before-restart ordering.
- #177/#178 fixed the guard's DDEV command parsing; merge commit `a2ff829aaa3501db6170a5a7f401749456387522`, exact-head CI #334 green.
- `chonhac` remains `autonomy.allow_auto_merge_low_risk: false`; never enable it merely to exercise auto-merge.

## #162 rollout and preservation evidence complete

The safety-gated rollout/rebuild completed with zero active Runtime jobs, zero active ddev-executor jobs and zero active Antigravity runs.

Verified deployed identities:

- Antigravity host bridge `1.10`, safety settings intact;
- Router `1.0.21`, routing policy v12;
- Coding Runtime `1.0.44`;
- ddev-executor `1.0.15`, GitHub delivery configured;
- n8n direct `/healthz` healthy.

`ddev platform-test` passed after corrected tests were rebuilt:

- Router `76 passed`;
- Runtime `289 passed`;
- ddev-executor `34 passed`.

The preserved `chonhac` DEC-025C state survived rollout unchanged. A direct read-only `cp_control_actions` query confirmed recovery action `abXzvyU2pvALZ5YpovNveDcr` remained pending, unexpired, result null and never mutated.

Do not repeat the earlier no-cache rollout rebuild unless later service-image source actually requires it.

## Trust/secret boundary gate complete

The existing local install originally lacked the newly introduced Runtime-side `PLATFORM_INTERNAL_TOKEN`. The Human Owner safely completed the canonical remediation after a fresh no-active-work gate:

- `scripts/scope-service-secrets.sh` completed successfully;
- Runtime/executor scoped files contain the same real `PLATFORM_INTERNAL_TOKEN`;
- global `.ddev/.env` contains no platform credential;
- a normal `ddev restart` reloaded the migrated service env;
- deployed versions remained Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`.

After #177/#178 corrected the host-side probe semantics, the deployed strict boundary passed on local main `a2ff829aaa3501db6170a5a7f401749456387522`:

- coding-runtime: internal token present; GitHub delivery and Telegram bot credentials absent;
- ddev-executor: internal token and GitHub delivery present; Runtime API credential absent;
- n8n: Runtime API credential present; GitHub delivery and internal executor credential absent;
- corrected guard returned `ok:true` and strict mode exited 0;
- `CORE_CREDENTIAL_GATE=PASS` and `TRUST_AND_N8N_GATE=PASS`.

In the same run, `ddev platform-status` printed `n8n DOWN`, but the immediate direct in-container `/healthz` probe returned `{"status":"ok"}`. Preserve the direct health evidence for this gate; do not treat that single status line as a demonstrated outage. No extra restart is required from this observation alone.

The secret migration and trust-boundary remediation are complete. Future sessions must not repeat migration/restart unless a later source/config change actually requires it.

Phase-E `rollout` continuity event has **not** been recorded yet. The routine validation job has **not** been created yet.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `rollout_trust_boundary_completed`.
- Parent validation: `#162`; initiative: `#146`.
- Rollout health/tests/DEC-025C preservation: complete.
- Service-secret migration: complete; scoped Runtime/executor internal token present and matching; global env clean.
- Trust boundary: strict corrected guard `ok:true`; Runtime/executor/n8n scopes match intended authority boundaries.
- n8n: direct `/healthz` returned `status=ok`; one `platform-status` line reported DOWN in the same run and is treated as a transient/false-negative observation, not an established outage.
- Source follow-ups #175 and #177: complete via PRs #176 and #178.
- Phase-E rollout event: not recorded yet.
- Routine `example-drupal` job: not created yet.
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

Local fixture existence/cleanliness/remote/baseline have not yet been proven. If `example-drupal` is unsuitable, stop and record the blocker; never fall back to `chonhac` merely to exercise auto-merge.

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

1. Complete #179 as this mutable continuity update only; no platform restart/rebuild.
2. Record the Phase-E `rollout` continuity event through authenticated Runtime API now that health/tests/preservation/trust gates are complete.
3. Verify local `example-drupal` repository existence, cleanliness, `develop`/remote alignment and configured deterministic baseline.
4. If fixture readiness passes, create exactly one small routine validation WorkOrder with deterministic non-empty diff and no manual merge.
5. Let the system proceed through implementation, layered verification, proportional review, PR/CI and constrained PM merge without Human Owner merge intervention.
6. Capture telemetry, Human attention, PM-merge audit and continuity evidence in #162 and #146.
