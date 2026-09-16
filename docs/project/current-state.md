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
- #179/#180 recorded completed trust-boundary/n8n health evidence; merge commit `bed45048adc5b78d53dda52305b97909ed44d881`.
- #181 is the active blocker: provision or explicitly select a real dedicated non-production GitHub-backed fixture before the #162 routine auto-merge proof.
- `chonhac` remains `autonomy.allow_auto_merge_low_risk: false`; never enable it merely to exercise auto-merge.

## #162 rollout, preservation, trust and continuity evidence complete

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

The existing-install service-secret migration was completed after a fresh no-active-work gate. Runtime/executor scoped files share the same real `PLATFORM_INTERNAL_TOKEN`, global `.ddev/.env` contains no platform credential, and the corrected deployed strict boundary returned `ok:true`:

- coding-runtime: internal token present; GitHub delivery and Telegram bot credentials absent;
- ddev-executor: internal token and GitHub delivery present; Runtime API credential absent;
- n8n: Runtime API credential present; GitHub delivery and internal executor credential absent.

A Phase-E external continuity event was then recorded through authenticated `POST /v1/continuity/events` with `event_type=rollout`, `project_id=personal-coding-platform`, `status=external_event`, and successful rollout/trust/DEC-025C detail. Authenticated read-back through `/v1/continuity/proposal?project_id=personal-coding-platform` returned the same latest rollout event. This gate is complete; do not record a duplicate event merely to resume a later chat.

Do not repeat the earlier no-cache rollout rebuild or secret migration/restart unless later service-image/config source actually requires it.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `rollout_complete_fixture_missing`.
- Parent validation: `#162`; initiative: `#146`.
- Rollout health/tests/DEC-025C preservation: complete.
- Service-secret migration and deployed trust boundary: complete; strict guard `ok:true`.
- n8n: direct `/healthz` healthy.
- Phase-E rollout continuity event: recorded and durably readable.
- Preferred routine fixture: blocked because `/home/sonvh/example-drupal` is not a Git repository and no accessible GitHub repository named `example-drupal` was found.
- Active bounded blocker: `#181` provision/select a real dedicated non-production GitHub-backed fixture.
- Routine validation job: not created.
- Production deployment: not performed.
<!-- PCP:CONTINUITY:END -->

## Routine validation fixture blocker #181

`config/projects.yml` registers `example-drupal` with the desired proof contract:

- base branch `develop`;
- `autonomy.allow_auto_merge_low_risk: true`;
- production deploy disabled;
- DDEV preflight (`ddev start -y`, `ddev drush cr`);
- enforcing PHPCS targeted verification;
- enforcing PHPStan static analysis;
- PHPUnit full tests;
- cleanup via DDEV stop.

However, local readiness stopped fail-closed before any routine job was created:

- `${CODING_PROJECTS_ROOT}/example-drupal` resolved to `/home/sonvh/example-drupal`;
- that path is not a Git repository;
- GitHub discovery found no accessible/owned repository named `example-drupal`, so the registration currently has no discoverable backing repo.

Do not fall back to `chonhac`; its auto-merge opt-in is intentionally false. Do not use `default` for the #162 proof in its current form: required PHPCS/PHPStan commands are non-enforcing (`|| true`) and no full-test stage is configured.

Issue #181 requires a real dedicated non-production fixture to be provisioned or explicitly selected. Before any routine WorkOrder, prove:

1. the fixture exists locally and is clean;
2. its backing GitHub repository is accessible;
3. the configured base branch matches origin;
4. production deployment is disabled and low-risk PM auto-merge is explicitly enabled;
5. deterministic enforcing preflight/targeted/static/full baseline passes;
6. there is a small safe non-security/non-architecture/non-dependency/non-migration/non-production implementation surface for a non-empty diff.

Do not weaken verification to make the proof pass and do not create the validation job until #181 readiness is complete.

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

1. Complete docs-only #182 so this handoff is durable; do not restart/rebuild the platform.
2. Resolve #181 by provisioning or explicitly selecting a dedicated non-production GitHub-backed validation fixture; do not use `chonhac` merely to exercise auto-merge.
3. Register the fixture through normal reviewed config if needed, with production deployment disabled and enforcing deterministic verification.
4. Human Owner clones/prepares the chosen fixture locally only after its repository/source is explicitly known, then run the fixture readiness/baseline gate.
5. If readiness passes, create exactly one small routine validation WorkOrder with deterministic non-empty diff and no manual merge.
6. Let the system proceed through implementation, layered verification, proportional review, PR/CI and constrained PM merge without Human Owner merge intervention.
7. Capture telemetry, Human attention, PM-merge audit and continuity evidence in #162 and #146.
