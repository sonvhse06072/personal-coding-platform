# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-16

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md` and this file.
3. Read `docs/project/efficiency-model.md` and `docs/project/service-secret-upgrades.md` for active #162 work.
4. Inspect the active issue/PR and current branch diff before editing.

## Platform baseline

- Efficiency initiative #146 source phases A-F are implemented; operational proof remains #162.
- PM routine in-scope merge authority is approved; Developer agents never merge and production remains Human Owner-controlled.
- Deployed platform remains Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`, routing policy v12.
- Rollout health/tests, DEC-025C preservation, service-secret migration, deployed trust boundary, direct n8n health and Phase-E rollout continuity event are complete.
- `ddev platform-test` rollout evidence: Router `76 passed`, Runtime `289 passed`, ddev-executor `34 passed`.
- Do not repeat rollout rebuild, service-secret migration or rollout continuity event unless later source/config actually requires it.

## #162 current stage: first routine validation job blocked by #186

Dedicated private non-production fixture `sonvhse06072/pcp-validation-fixture` is provisioned and ready:

- fixture issue `pcp-validation-fixture#1` and bootstrap PR `pcp-validation-fixture#2` complete;
- fixture bootstrap merge `553e4c595551ea0d0ee73d0094c943f88b5bba97`;
- GitHub CI passed style, PHP syntax and full self-contained tests;
- PCP issue #184 / PR #185 registered project id `pcp-validation-fixture` with base `main`, low-risk PM auto-merge enabled and production deploy disabled;
- PCP registration merge `f42f132a44f29aac55e234358b0e2e4387304950`;
- local fixture path `/home/sonvh/pcp-validation-fixture` exists, is clean and matches origin `main` at the fixture merge commit;
- local DDEV baseline passed targeted style, static PHP syntax and full deterministic tests; cleanup left the repository clean;
- issue #181 is closed complete.

The intended single routine validation task remains test-only: add a regression case for whitespace-only `Greeter` input, preserving existing public behavior. Do not create a second or substitute validation task.

The first `./scripts/create-job.sh pcp-validation-fixture ...` attempt returned HTTP 422 before a job row was created. Source inspection identified Runtime project-registry caching as the cause: `project_config()` reads `projects_doc()`, which was process-cached, while ddev-executor reads the bind-mounted `projects.yml` live. After config-only project registration, Runtime and executor could therefore disagree until Runtime restart.

Issue #186 is the active bounded defect: make Runtime project-registry reads observe reviewed bind-mounted `projects.yml` changes without restart. Branch `ai/reload-project-registry-186` contains the fix and regression test. Do not retry the routine validation job until #186 is merged and the Runtime code change is safely loaded.

The #186 branch must remain narrow:

- remove only the `projects_doc()` process cache; keep model/baseline caches unchanged;
- preserve unknown-project and unresolved-path fail-closed behavior;
- regression-test adding a project to the same registry file without `clear_config_cache()` or process restart;
- no PM-merge, auth, state-machine, cancellation, decision, cleanup, verification or production behavior changes;
- Runtime API version remains `1.0.44` for this patch; post-load acceptance is behavioral (the newly registered fixture becomes visible and job creation proceeds) rather than version-only identity.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `fixture_ready_project_registry_reload_blocked`.
- Parent validation: `#162`; initiative: `#146`.
- Rollout/preservation/trust/n8n/Phase-E rollout event: complete.
- Dedicated fixture: provisioned, registered, cloned locally and deterministic baseline green.
- Fixture blocker #181: closed complete.
- First routine job attempt: HTTP 422 before job creation; no validation job exists from that attempt.
- Active bounded defect: `#186` Runtime project registry cache mismatch.
- Active branch: `ai/reload-project-registry-186`.
- Routine validation job: not yet created successfully.
- Production deployment: not performed.
<!-- PCP:CONTINUITY:END -->

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

Recovery action `abXzvyU2pvALZ5YpovNveDcr` is `budget_extend` for `max_repair_iterations +1`, pending and unexpired after rollout. Never manually mutate DB/job state, counters or this action.

## Global operational gates

- Normal flow: issue -> `ai/*` branch -> deterministic tests/CI -> PR -> PM merge when eligible.
- Never force push.
- Developer agents never merge or receive GitHub delivery credentials.
- Human Owner retains protected architecture/security/production/governance authority.
- Production deployment is never implied by PR merge.
- Do not restart/rebuild platform services while any engineering job is active.
- Runtime durable state is authoritative; never edit DB/job state to bypass the state machine.
- Provider/control-plane credentials remain service-scoped and never enter prompts/docs/logs.
- Potentially failing Human Owner command blocks must run in a subshell or standalone script so controlled non-zero exits cannot terminate the parent Ubuntu/WSL shell.

## Immediate next safe actions

1. Finish #186 through exact-head CI and reviewed PR, with no out-of-scope Runtime API changes.
2. Before loading the Runtime code change locally, re-run the no-active-work safety gate; preserve DEC-025C unchanged.
3. Rebuild/restart only as required to load the Runtime source patch, then run `ddev platform-test` and verify trust/preservation gates remain intact.
4. Retry exactly one `pcp-validation-fixture` routine job for the whitespace-only regression test.
5. Do not manual-merge its fixture PR; allow constrained PM merge to proceed after verification/review/CI.
6. Capture telemetry, Human attention, PM-merge audit and continuity evidence in #162 and #146.
