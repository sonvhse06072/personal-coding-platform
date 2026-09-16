# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-17

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md` and this file.
3. Read `docs/project/efficiency-model.md` and `docs/project/provider-policy.md` for active #146 calibration work.
4. Inspect the active issue/PR and current branch diff before editing.

## Platform baseline

- Efficiency initiative #146 source phases A-F are implemented.
- Constrained PM-controlled merge #98 is implemented and operationally proven.
- Low-touch routine-path validation #162 is complete via a clean zero-avoidable-intervention R3 run.
- PM routine in-scope merge authority is approved; Developer agents never merge and production remains Human Owner-controlled.
- Last verified deployed service labels remain Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`, routing policy v12.
- Continuity B1 was locally activated from exact PCP source `45e83ec97dbd8a03944d5b85e7a9c5218028d0fe`; the Human Owner confirmed both activation blocks passed completely, including no-active-work gates, full platform tests, Runtime/executor authority-boundary checks, executor PCP delivery-token dry-run authorization, and exact DEC-025C/pending-action preservation.
- Human Attention delivery-recovery accounting was locally activated from exact PCP source `6894775862c35e271e159a4202d5a6d27b33c8f7`; full platform tests and deployed `control_actions_attention` wiring passed, historical R2 remained unmodified with no synthetic backfill, and DEC-025C plus its pending action remained exactly preserved.
- Do not repeat R3, B1 or Human Attention rollout/rebuild validation merely to recreate already captured evidence.

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

## Efficiency initiative #146: implementation complete, calibration remains

Issues #147, #148, #149, #150, #151, #98, #153 and #162 are closed `completed`. Keep #146 open while collecting naturally occurring routine-task evidence rather than manufacturing validation-only jobs. Calibration should compare estimate vs actual usage, first-pass success, repair/retry categories, verification runs, review yield, wall time, provider/model share and Human Attention metrics.

### Continuity B1: source merged and locally activated

- #201 / PR #202 refreshed the handoff after R3.
- #203 / PR #204 added constrained automatic application for `pr_merged` continuity proposals only.
- PR #204 exact head `40805c8b0ffb35806b2c42035ca9e13a778291e9` passed workflow run `35139240879` (run #367) across structure, Router, Runtime and ddev-executor.
- PR #204 merged at `cb8668fefc328f8ab664cfbce223a9231cbba742`; #205 / PR #206 then recorded the activation gate, producing PCP main `45e83ec97dbd8a03944d5b85e7a9c5218028d0fe`.
- Human Owner subsequently confirmed both local B1 activation blocks passed fully: source sync, no-active-work gates, full platform tests, Runtime GitHub-authority absence, executor continuity authority, invalid-payload fail-closed probe, PCP delivery-token dry-run authorization, and DEC-025C/action preservation.
- Runtime still receives no GitHub/source-write credential. ddev-executor constrains continuity mutation to the configured PCP repository and exactly `docs/project/current-state.md`, through `ai/continuity/*` PR + CI + exact-head merge.
- B1 remains deliberately advisory after the engineering merge and currently auto-applies only `pr_merged`.

### Human Attention delivery-recovery fix: source merged and locally activated

Operational R2 evidence exposed a telemetry correctness gap: task telemetry correctly recorded `delivery_retries=2`, but successful owner-executed `retry_delivery` controls were absent from `cp_attention_events` and the Human Attention summary therefore remained zero.

#207 / PR #208 fixes that bounded gap without changing recovery semantics or retry counters:

- successful owner-executed `retry_delivery` and `recheck_ci` actions become `routine_operational` Human Attention events with `avoidable=true`;
- durable `action_id` is the event-key authority, so replay is idempotent and can repair missing telemetry without double-counting;
- owner wait is measured from durable control-action creation to successful execution;
- only sanitized identifiers/type/channel metadata is stored;
- `budget_extend`, protected human decisions, provider/reroute/operator controls and task retry/repair counters remain unchanged by this slice;
- attention persistence is downstream observability only and cannot roll back an already-successful control action.

PR #208 exact head `40ab0cf6b5149ff79465091a202eeb0f3ed4dd24` passed workflow run `35142013882` (run #371) across all four jobs and merged at `a0b886ba68c34ec81bb374a9eaa7c145db0f2b6c`; #209 / PR #210 then recorded the activation gate and produced PCP main `6894775862c35e271e159a4202d5a6d27b33c8f7`.

The Human Owner subsequently confirmed the local activation block passed fully: exact-source/idle gates, full platform tests, deployed `control_actions_attention` module and orchestrator wiring, idempotence/source semantics, unchanged historical R2 attention with zero `owner_delivery_recovery` backfill, exact DEC-025C/action preservation, and final idle/source gates. The next naturally occurring successful owner `retry_delivery` or `recheck_ci` action should provide live accounting evidence; do not manufacture one solely for validation.

## Provider optimization #153: complete

Issue #153 is closed `completed`; do not open another routing-preference PR for the same behavior.

Implemented evidence:

- PR #155 made the existing `openrouter_qwen3_coder_free` / North Mini Code resource the first preferred executor for healthy `fast` and `standard` routes and gave standard the bounded preferred-order bonus needed for that preference to be effective;
- #155 regression coverage proves fallback when OpenRouter provider/model is unavailable, privacy rejection when training providers are disallowed, quota-pressure fallback, and critical/security exclusion;
- OpenRouter remains excluded from critical execution/planning and Product Manager staffing; complex use remains bounded to reviewer eligibility rather than routine complex execution;
- Phase E telemetry persists selected provider/model and TaskOutcome and aggregates provider/model task share plus accepted-task success for calibration;
- R3 supplied positive clean first-pass evidence for the existing OpenRouter executor, but a single task is not treated as statistically meaningful calibration.

Do not activate a second OpenRouter model merely to increase free-model count. Current OpenRouter Runtime failure semantics remain provider-wide, so multiple active models under the same provider would not produce an effective PCP fallback. A multi-model OpenRouter pool requires an intentional model-level health/failover redesign and tests first.

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

1. Complete #213 through its one-file docs-only PR and normal CI/merge.
2. Keep #146 in calibration mode and collect naturally occurring routine-task evidence. Do not create synthetic jobs solely to satisfy a sample-size threshold.
3. Periodically inspect the existing telemetry summary/calibration endpoints for provider/model share, accepted success, first-pass success, repair/retry categories, verification/review spend, wall time/cost and Human Attention. Historical evidence may refine estimates only after the configured meaningful sample size is reached.
4. Close #146 only when the naturally occurring sample is sufficient to evaluate the initiative success trends; if calibration exposes a concrete regression or optimization opportunity, open a new bounded issue from that evidence rather than widening an already-completed phase.
5. Telegram terminal operations remains approved but lower priority until the efficiency/calibration work above is sufficiently mature.
