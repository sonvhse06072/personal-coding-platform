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
- Rollout health/tests, DEC-025C preservation, service-boundary validation, n8n health and the Phase-E rollout continuity event are complete.
- Do not repeat the rollout rebuild or rollout continuity event unless later source/config requires it.

## #162 current stage: ProjectBaseline follow-up #190

The dedicated non-production repository `sonvhse06072/pcp-validation-fixture` is provisioned and registered. Fixture blocker #181, registration #184/#185, and project-registry reload defect #186/#187 are complete.

One historical direct validation job, `b2fb7ae243734ef9bbfc344934c3911c`, reached independent review and failed because malformed reviewer fallback output could exceed the ReviewFinding schema. #188/#189 fixed that defect. Preserve the failed job/workspace as historical evidence; do not resume or mutate it.

Further validation must use the real orchestration path:

`POST /v1/plans -> ExecutionPlan -> tracked WorkOrder -> orchestrator-created job -> verification/review -> PR/CI -> constrained PM merge`

Pre-mutation inspection found that `pcp-validation-fixture` had no approved ProjectBaseline. #190 tracks that bounded governance gap.

The Human Owner approved initial baseline revision `validation-v1-2026-09-16` on 2026-09-16. The approved frame is dedicated non-production PCP validation only, preserving the existing generic PHP+DDEV fixture, enforcing its existing deterministic checks and CI, and keeping the immediate task test-only: add whitespace-only Greeter regression coverage without changing public behavior.

Fixture issue #3 / PR #4 added `PROJECT-BASELINE.md` and merged after CI at exact fixture commit `ba3207af0ce28b607b1d3dd9eb00bc69072ac234`.

PCP branch `ai/fixture-project-baseline-190` registers that exact commit as active approved revision `validation-v1-2026-09-16`, adds regression coverage for the pinned baseline contract, and updates this handoff.

The Runtime caches the ProjectBaseline registry in-process. After the registry PR merges and local source is synchronized, activation requires a fresh no-active-work gate before a bounded Runtime restart/recreate so the new baseline is read. A full no-cache rebuild is not required solely for this config activation.

After activation, re-check platform health and the preserved DEC-025C state, then re-check fixture cleanliness/base branch/deterministic baseline before creating the validation plan. Do not create another direct legacy fixture job and do not record a duplicate rollout continuity event.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `fixture_project_baseline_registration_in_progress`.
- Parent validation: `#162`; initiative: `#146`; active follow-up: `#190`.
- Earlier rollout/preservation/service-boundary/n8n/continuity gates: complete.
- Fixture provisioning/registration/readiness: complete.
- #186/#187 project-registry reload defect: complete.
- #188/#189 review fallback defect: complete.
- Historical direct validation job: `b2fb7ae243734ef9bbfc344934c3911c`, failed and preserved.
- Approved fixture baseline: `validation-v1-2026-09-16`.
- Fixture baseline source commit: `ba3207af0ce28b607b1d3dd9eb00bc69072ac234`.
- PCP baseline registration: in progress on `ai/fixture-project-baseline-190`.
- Legitimate orchestrated validation plan/job: not yet created.
- Production deployment: not performed.
<!-- PCP:CONTINUITY:END -->

## Preserved `chonhac` DEC-025C

- plan `pm-gh-5650852312`;
- WorkOrder `DEC-025C-1-recovery-tooling-r2`;
- job `eec59b13651c54559c10ce204380a68e`;
- branch `ai/eec59b13651c`;
- workspace `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`;
- status `blocked`;
- result remains `reassessment_stopped` / `repair budget exhausted` / `hard_budget_guard`;
- preserved usage remains model calls `21 / 22`, tool calls `65 / 160`, test runs `14 / 14`, wall time `93.168 / 110` minutes, repair iterations `4 / 4`.

The existing pending recovery action remains preserved. Never manually mutate durable job/action state or counters.

## Global operational gates

- Normal flow: issue -> `ai/*` branch -> deterministic tests/CI -> PR -> eligible PM merge.
- Never force push.
- Developer agents never merge.
- Human Owner retains protected architecture/security/production/governance authority.
- Production deployment is never implied by PR merge.
- Do not restart/rebuild platform services while engineering work is active.
- Runtime durable state is authoritative; never edit durable state to bypass the state machine.
- Potentially failing Human Owner command blocks must remain isolated from the parent interactive shell.

## Immediate next safe actions

1. Finish #190 through exact-head CI and reviewed PCP PR.
2. Synchronize local PCP source, run a fresh idle gate, and activate the merged baseline with a bounded Runtime restart/recreate only if the gate passes.
3. Re-check platform health and preserved DEC-025C state after activation.
4. Re-check fixture `main`, duplicate/open-PR state, local cleanliness and deterministic baseline.
5. Create exactly one authenticated `POST /v1/plans` request for `Add whitespace-only Greeter regression test` and verify it becomes a tracked WorkOrder/orchestrator-created job.
6. Do not manually merge the fixture validation PR; allow constrained PM merge after verification/review/CI.
7. Capture telemetry, Human attention, PM-merge audit and continuity evidence in #162 and #146.
