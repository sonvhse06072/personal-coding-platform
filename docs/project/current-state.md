# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-16

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md` and this file.
3. Read `docs/project/efficiency-model.md` and `docs/project/service-secret-upgrades.md` for active #162 work.
4. Inspect the active issue/PR and current branch diff before editing.

## Platform baseline

- Efficiency initiative #146 source phases A-F are implemented; operational proof is tracked by #162.
- PM routine in-scope merge authority is approved; Developer agents never merge and production remains Human Owner-controlled.
- Deployed platform remains Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`, routing policy v12.
- Rollout health/tests, DEC-025C preservation, service-secret migration, deployed trust boundary, direct n8n health and Phase-E rollout continuity event are complete.
- `ddev platform-test` evidence after rollout: Router `76 passed`, Runtime `289 passed`, ddev-executor `34 passed`.
- Do not repeat rollout rebuild, secret migration/restart, or rollout continuity event unless later source/config actually requires it.

## #162 current stage: dedicated routine fixture

The previous `example-drupal` placeholder had no local or discoverable GitHub backing repository, so #181 stopped fail-closed before any routine job.

The Human Owner has now created dedicated private repository `sonvhse06072/pcp-validation-fixture`. It is explicitly non-production and isolated from real projects.

Fixture bootstrap issue/PR in that repository:

- issue `pcp-validation-fixture#1`;
- bootstrap PR `pcp-validation-fixture#2`;
- merged commit `553e4c595551ea0d0ee73d0094c943f88b5bba97`;
- GitHub Actions validation passed on PHP 8.3: style gate, PHP syntax gate and full self-contained tests.

Fixture design:

- generic PHP DDEV project with docroot `web`;
- Drupal-style module surface `web/modules/custom/pcp_validation`;
- no production data, deployment logic, migrations, secrets or external-service dependency;
- no Composer/Packagist dependency resolution;
- deterministic style checker and self-contained test runner;
- baseline behavior already supports empty/whitespace-only names while initial tests intentionally omit that regression case, providing a safe future test-only routine diff with no public behavior change.

PCP issue #184 is the active source step: register project id `pcp-validation-fixture` at `${CODING_PROJECTS_ROOT}/pcp-validation-fixture`, base `main`, auto-merge low-risk enabled, production deploy disabled, and enforcing DDEV preflight/targeted/static/full verification. Do not create the routine WorkOrder until #184 is merged and local clone/baseline readiness passes.

`chonhac` remains `autonomy.allow_auto_merge_low_risk: false`; never enable or repurpose it merely for this proof. `default` remains unsuitable because its current PHPCS/PHPStan gates are non-enforcing and it has no full-test stage.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `validation_fixture_provisioned_registration_in_progress`.
- Parent validation: `#162`; initiative: `#146`; fixture blocker: `#181`; registration: `#184`.
- Rollout/preservation/trust/n8n/Phase-E rollout event: complete.
- Dedicated fixture repo: `sonvhse06072/pcp-validation-fixture`.
- Fixture bootstrap merge: `553e4c595551ea0d0ee73d0094c943f88b5bba97`; CI green.
- PCP project registration: in progress through #184; no local clone/baseline yet.
- Routine validation job: not created.
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

Recovery action `abXzvyU2pvALZ5YpovNveDcr` is `budget_extend` for `max_repair_iterations +1`, pending and unexpired after rollout. Do not manually mutate DB/job state, reset counters, replace this job, or backport newer semantics into it.

## Global operational gates

- Normal flow: issue -> `ai/*` branch -> deterministic tests/CI -> PR -> PM merge when eligible.
- Never force push.
- Developer agents never merge or receive GitHub delivery credentials.
- Human Owner retains protected architecture/security/production/governance authority.
- Production deployment is never implied by PR merge.
- Do not restart/rebuild platform services while an engineering job is active.
- Runtime durable state is authoritative; never edit DB/job state to bypass the state machine.
- Provider/control-plane credentials remain service-scoped and never enter prompts/docs/logs.
- Potentially failing Human Owner command blocks must run in a subshell or standalone script so controlled non-zero exits cannot terminate the parent Ubuntu/WSL shell.

## Immediate next safe actions

1. Complete #184 through reviewed CI/PR.
2. Human Owner fast-forwards PCP `main`, then clones `sonvhse06072/pcp-validation-fixture` to `${CODING_PROJECTS_ROOT}/pcp-validation-fixture`.
3. Prove local fixture is clean, `main` matches origin, and DDEV targeted/static/full baseline passes.
4. If readiness passes, close #181 and create exactly one small routine WorkOrder: add a whitespace-only regression test without changing public behavior.
5. Do not manual-merge that validation PR; let constrained PM merge handle it after verification/review/CI.
6. Capture telemetry, Human attention, PM-merge audit and continuity evidence in #162 and #146.
