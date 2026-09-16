# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-17

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md` and this file.
3. Read `docs/project/efficiency-model.md` and `docs/project/provider-policy.md` for active #146/#153 work.
4. Inspect the active issue/PR and current branch diff before editing.

## Platform baseline

- Efficiency initiative #146 source phases A-F are implemented.
- Constrained PM-controlled merge #98 is implemented and operationally proven.
- Low-touch routine-path validation #162 is complete via a clean zero-avoidable-intervention R3 run.
- PM routine in-scope merge authority is approved; Developer agents never merge and production remains Human Owner-controlled.
- Last verified deployed service labels remain Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`, routing policy v12.
- Rollout health/tests, DEC-025C preservation, service-boundary validation, direct n8n health and the Phase-E rollout continuity event are complete.
- Do not repeat rollout/rebuild/validation work merely to recreate #162 evidence.

## #162 operational validation: complete

The dedicated non-production repository `sonvhse06072/pcp-validation-fixture` is provisioned, registered and uses an explicitly approved ProjectBaseline.

Important historical validation evidence remains preserved:

- historical direct fixture job `b2fb7ae243734ef9bbfc344934c3911c` failed because reviewer fallback output could exceed the ReviewFinding schema; #188/#189 fixed it; do not resume or mutate that job;
- R2 plan `pm-a38174598db14b97a1a1888eab32bff4` / job `99e69711b2545c3fabdc2f42013a7bd1` proved the PM merge path after exposing and recovering delivery defects #196 and #198; R2 required Human Owner recovery and is not the clean acceptance proof;
- R3 is the clean acceptance proof.

R3 exact evidence:

- approved baseline revision: `validation-v2-2026-09-16-r3`;
- fixture baseline/source before R3: `6395655ec311692493d9e93c2573b1bd946c7331`;
- plan: `pm-79996418ddf046ed90bbae6f45ab5207`;
- WorkOrder: `FIXTURE-GH-7-R3-TEST`;
- job: `c04c0af200d95d6583de70616e8ea7d3`;
- branch: `ai/c04c0af200d9`;
- verified implementation head: `310d007e626267568534fe56d1da15d0bb40e47f`;
- fixture PR: `pcp-validation-fixture#9`;
- PM merge commit: `3ecd9ce66260245089efe2533080d1b5191b810c`;
- orchestration/WorkOrder: `completed`;
- PM merge audit: `merged`, `requires_human=false`;
- first-pass success: true;
- engineering repairs: 0;
- delivery retries: 0;
- provider failures/failovers: 0;
- Human Owner interventions: 0;
- avoidable blocks: 0;
- control actions: none;
- blocked/error events: 0;
- continuity event: `pr_merged` with `authority=pm_controlled_merge`.

Issue #162 and fixture issue #7 are closed `completed`. No R4 is required for #162.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `pr_merged`.
- Project/job: `pcp-validation-fixture` / `c04c0af200d95d6583de70616e8ea7d3`.
- Runtime state: `completed`; outcome: `accepted`.
- WorkOrder: `FIXTURE-GH-7-R3-TEST`; branch: `ai/c04c0af200d9`.
- Human attention: interventions `0`, avoidable `0`, owner wait `0.0` seconds.
- Execution evidence: first-pass `True`, repairs `0`, provider failures `0`, quota failures `0`.
- Merge evidence: PR `9`, merge commit `3ecd9ce66260245089efe2533080d1b5191b810c`, authority `pm_controlled_merge`.
- This section is mutable execution state only. Durable architecture/policy changes still require their normal reviewed Git path.
<!-- PCP:CONTINUITY:END -->

## Efficiency initiative #146: implementation complete, calibration/follow-up remains

Issues #147, #148, #149, #150, #151 and #98 are closed `completed`; #162 now provides the clean operational routine-path proof.

Keep #146 open while collecting real routine-task evidence rather than manufacturing validation-only jobs. Calibration should use naturally occurring work and compare estimate vs actual usage, first-pass success, repair/retry categories, verification runs, review yield, wall time, provider/model share and Human Attention metrics.

Continuity B1 source implementation is now complete:

- #201 / PR #202 refreshed this handoff after R3;
- #203 / PR #204 added constrained automatic application for `pr_merged` proposals only;
- PR #204 exact head `40805c8b0ffb35806b2c42035ca9e13a778291e9` passed fresh workflow run `35139240879` (run #367) across structure, Router, Runtime and ddev-executor;
- PR #204 merged to PCP `main` at `cb8668fefc328f8ab664cfbce223a9231cbba742`;
- Runtime still receives no GitHub/source-write credentials; ddev-executor constrains continuity mutation to the configured PCP repository and exactly `docs/project/current-state.md`, through `ai/continuity/*` PR + CI + exact-head merge;
- application is deliberately advisory after the engineering merge and currently auto-applies only `pr_merged`.

The B1 source is merged but has not yet been locally activated. Do not treat the new continuity applicator as deployed until a fresh no-active-work gate, exact-source synchronization, DDEV rebuild/restart, full platform tests, credential-boundary verification and DEC-025C preservation check pass.

One remaining telemetry correctness gap should be handled after B1 activation: owner-executed operational recovery such as `retry_delivery` is not currently represented in Human Attention events, so R2 could report attention zero while task telemetry correctly reported delivery retries.

## Provider optimization #153

Issue #153 remains open and is the next approved feature-oriented optimization after continuity/attention correctness work.

Current safe direction:

- prefer the already integrated/smoke-proven OpenRouter North Mini Code resource for eligible fast/standard routine execution where capability/privacy/health gates allow it;
- preserve stronger-model routing for critical/security/architecture work;
- do not add a second active OpenRouter model pool until provider-wide vs model-level health/failover semantics are intentionally redesigned and tested;
- use real telemetry before widening complex-role eligibility.

R3 provides positive first-pass evidence for the existing OpenRouter executor, but one successful task is not a statistically meaningful calibration sample.

## Preserved `chonhac` DEC-025C

- plan `pm-gh-5650852312`;
- WorkOrder `DEC-025C-1-recovery-tooling-r2`;
- job `eec59b13651c54559c10ce204380a68e`;
- branch `ai/eec59b13651c`;
- workspace `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`;
- status `blocked`;
- result remains `reassessment_stopped` / `repair budget exhausted` / `hard_budget_guard`;
- preserved usage remains model calls `21 / 22`, tool calls `65 / 160`, test runs `14 / 14`, wall time `93.168 / 110` minutes, repair iterations `4 / 4`.

The existing pending recovery action `abXzvyU2pvALZ5YpovNveDcr` remains preserved with no result. Never manually mutate durable job/action state or counters and never resume it as part of #146 follow-up work.

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

1. Synchronize local PCP source to the exact current `main` only after a fresh no-active-work gate.
2. Rebuild/restart the platform from the merged B1 source, then run platform health/tests, verify the secret boundary and confirm DEC-025C/pending action remain unchanged.
3. Verify the executor-side PCP GitHub delivery credential can authorize the new continuity repository path without exposing the token; do not create a manual continuity PR merely as a smoke test.
4. After B1 activation passes, open and implement a bounded Human Attention follow-up so owner-executed routine operational recovery is represented in attention telemetry without conflating provider/delivery retry counters with engineering repair.
5. Resume #153 with a small North Mini Code fast/standard routing-preference slice and routing/telemetry tests; do not activate a multi-model OpenRouter pool yet.
6. Collect naturally occurring routine-task calibration evidence under #146; close #146 only after the sample is meaningful enough to evaluate trends.
7. Telegram terminal operations remains approved but lower priority until the efficiency/calibration work above is sufficiently mature.
