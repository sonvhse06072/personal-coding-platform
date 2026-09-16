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

## #162 current stage: approved fixture baseline activation

The dedicated non-production repository `sonvhse06072/pcp-validation-fixture` is provisioned and registered. Fixture blocker #181, registration #184/#185, and project-registry reload defect #186/#187 are complete.

One historical direct validation job, `b2fb7ae243734ef9bbfc344934c3911c`, reached independent review and failed because malformed reviewer fallback output could exceed the ReviewFinding schema. #188/#189 fixed that defect. Preserve the failed job/workspace as historical evidence; do not resume or mutate it.

Further validation must use the real orchestration path:

`POST /v1/plans -> ExecutionPlan -> tracked WorkOrder -> orchestrator-created job -> verification/review -> PR/CI -> constrained PM merge`

The Human Owner approved initial fixture baseline revision `validation-v1-2026-09-16` on 2026-09-16. Fixture #3 / PR #4 added the approved `PROJECT-BASELINE.md` and merged at fixture commit `ba3207af0ce28b607b1d3dd9eb00bc69072ac234`.

PCP #190 / PR #191 is complete. PR #191 merged to PCP `main` at `0c3a4760404e52828206f3b4625a6c0f00c7998a`, registering the exact fixture commit above as active approved revision `validation-v1-2026-09-16` with regression coverage for the pinned baseline contract.

The Runtime caches the ProjectBaseline registry in-process. The next operational gate is therefore local source synchronization followed by a fresh no-active-work gate. Only if that gate passes should Runtime be restarted/recreated so the new baseline registry is read. A full no-cache rebuild is not required solely for this config activation.

After activation, re-check platform health and the preserved DEC-025C state, then re-check fixture cleanliness/base branch/deterministic baseline before creating the validation plan. Do not create another direct legacy fixture job and do not record a duplicate rollout continuity event.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `fixture_project_baseline_registered_activation_pending`.
- Parent validation: `#162`; initiative: `#146`.
- Earlier rollout/preservation/service-boundary/n8n/continuity gates: complete.
- Fixture provisioning/registration/readiness: complete.
- #186/#187 project-registry reload defect: complete.
- #188/#189 review fallback defect: complete.
- #190/#191 approved fixture ProjectBaseline registration: complete.
- Historical direct validation job: `b2fb7ae243734ef9bbfc344934c3911c`, failed and preserved.
- Approved fixture baseline: `validation-v1-2026-09-16`.
- Fixture baseline source commit: `ba3207af0ce28b607b1d3dd9eb00bc69072ac234`.
- PCP baseline registration merge: `0c3a4760404e52828206f3b4625a6c0f00c7998a`.
- Active operational gate: load the merged baseline into Runtime after a fresh idle gate.
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

1. Synchronize local PCP source to current `main`.
2. Run a fresh idle gate; preserve DEC-025C and historical failed fixture evidence unchanged.
3. If the gate passes, restart/recreate Runtime so the cached ProjectBaseline registry reloads.
4. Re-check platform health and preserved DEC-025C state after activation.
5. Re-check fixture `main`, duplicate/open-PR state, local cleanliness and deterministic baseline.
6. Create exactly one authenticated `POST /v1/plans` request for `Add whitespace-only Greeter regression test` and verify it becomes a tracked WorkOrder/orchestrator-created job.
7. Do not manually merge the fixture validation PR; allow constrained PM merge after verification/review/CI.
8. Capture telemetry, Human attention, PM-merge audit and continuity evidence in #162 and #146.
