# Current Project State and Handoff

Status: mutable continuity document. Repository docs and executable evidence are authoritative over chat history. Durable architecture/product/policy decisions remain in their topical source-of-truth documents.

Last updated: 2026-09-17

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md` and this file.
3. Read `docs/project/efficiency-model.md` and `docs/project/provider-policy.md` for active #146 calibration/follow-up work.
4. Inspect the active issue/PR and current branch diff before editing.

## Platform baseline

- Efficiency initiative #146 source phases A-F are implemented; calibration and evidence-driven follow-ups remain.
- Constrained PM-controlled merge #98 is implemented and operationally proven.
- Low-touch routine-path validation #162 is complete via the clean R3 run with zero avoidable Human Owner intervention.
- PM routine in-scope merge authority is approved; Developer agents never merge and production remains Human Owner-controlled.
- Last verified deployed service labels remain Runtime `1.0.44`, Router `1.0.21`, ddev-executor `1.0.15`, routing policy v12 until a later guarded rollout proves otherwise.
- Continuity B1 and Human Attention delivery-recovery accounting were locally activated and validated. Do not repeat those rollouts solely to recreate evidence.
- #215 legacy adaptive recovery and #219 effective-budget reconciliation are merged and were proven live by the preserved DEC-025C job resuming on the same durable job/workspace/counters.
- #221 bounded input-token owner recovery is merged on `main` at `2f4babbe33dfcf96fe6d6ef500243d2a0baec020`. Merge alone does not activate or resume DEC-025C; the job must remain blocked until guarded local activation and a newly materialized exact Human Owner action.

## #162 operational validation: complete

The dedicated non-production repository `sonvhse06072/pcp-validation-fixture` remains the clean acceptance fixture.

R3 exact evidence:

- approved baseline revision: `validation-v2-2026-09-16-r3`;
- fixture source before R3: `6395655ec311692493d9e93c2573b1bd946c7331`;
- plan: `pm-79996418ddf046ed90bbae6f45ab5207`;
- WorkOrder: `FIXTURE-GH-7-R3-TEST`;
- job: `c04c0af200d95d6583de70616e8ea7d3`;
- branch: `ai/c04c0af200d9`;
- verified implementation head: `310d007e626267568534fe56d1da15d0bb40e47f`;
- fixture PR: `pcp-validation-fixture#9`;
- PM merge commit: `3ecd9ce66260245089efe2533080d1b5191b810c`;
- orchestration/WorkOrder: `completed`;
- first-pass success: true;
- engineering repairs: 0;
- delivery retries: 0;
- provider failures/failovers: 0;
- Human Owner interventions: 0;
- avoidable blocks: 0.

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

## Efficiency initiative #146

Issues #147, #148, #149, #150, #151, #98, #153 and #162 are closed `completed`. Keep #146 open while collecting naturally occurring task evidence rather than manufacturing validation-only jobs. Calibration should compare estimate vs actual usage, first-pass success, repair/retry categories, verification runs, review yield, wall time, provider/model share and Human Attention metrics.

DEC-025C has supplied two useful real-world follow-ups:

1. #215 introduced bounded compatibility recovery for a genuinely pre-adaptive persisted WorkOrder; #219 corrected the temporary effective adaptive envelope so that recovery could use the Router-advertised emergency limits rather than stale historical counters.
2. After that path was active, DEC-025C made additional progress and exposed #221: legitimate cache-aware input-token usage can cross the current 2M complex-profile ceiling while Definition of Done is incomplete. This remains an explicit Human Owner circuit-break decision rather than automatic token-ceiling growth.

## Legacy adaptive recovery #215 / effective-budget fix #219

#215 / PR #216 is merged at `6bc1f1a13c02acc6d747329c332a777535b75733`. It preserves the same deterministic job, source, workspace, diff, immutable WorkOrder snapshot and durable counters while allowing a narrowly proven pre-adaptive job to adopt current adaptive semantics.

#219 / PR #220 is merged at `d078f5e3ce8e47555b12e459cdce4fa43114cae0`. It reconciles the temporary effective route used for legacy adoption with the Router-advertised adaptive emergency envelope while preserving explicit legacy-hard behavior outside that narrow path.

Live DEC-025C evidence after these changes proves the recovery path progressed beyond the old model/test/wall/repair ceilings. Do not repeat the old manual budget-extension choreography or create a replacement job.

## Bounded input-token owner recovery #221: source merged, local activation pending

#221 / PR #222 is closed `completed`. The final reviewed PR head `26cd99d46e7bdbadea7eca5cef4c0b54f1b7f3cd` passed workflow run #390 across structure, Router, Runtime and ddev-executor. PM merged the exact head into `main` at `2f4babbe33dfcf96fe6d6ef500243d2a0baec020`.

PM review found one fail-closed gap before merge: the token recovery helper validated the token reason/counters but did not itself require the freshly fetched job to remain `blocked`. The final head adds that explicit status gate and a regression test proving an otherwise matching in-flight job cannot receive the mutation.

Merged behavior remains intentionally narrow:

- autonomous Router/profile `max_input_tokens` remains unchanged; complex remains 2,000,000;
- only `max_input_tokens` gains an explicit owner recovery action in this slice;
- action increment is fixed at +1,000,000 tokens;
- platform hard maximum is 4,000,000 tokens, matching the existing critical-profile ceiling;
- direct input-token exhaustion and `reassessment_stopped` with `hard_budget_guard`/`hard_budget_overrun` map only when live counters prove `used >= limit`;
- the action is not offered if one increment cannot restore runnable headroom or the 4M hard maximum is already reached;
- execution re-fetches and revalidates the exact live blocked token state before mutation;
- usage/counters are never reset; the same job/workspace/source/diff and immutable WorkOrder are preserved;
- the durable Telegram budget authorization survives a later fresh route without changing Router autonomous defaults;
- no `max_output_tokens` or cost extension is added;
- rollout/startup alone must not auto-resume the job. Human Owner execution of the newly materialized exact action remains required.

Regression coverage reproduces the live DEC-025C state and covers advisory shape, exact +1M mutation, same-job resume, second authorization to 4M, hard-max/headroom fail-closed behavior, stale/in-flight state rejection, non-token reassessment preservation and fresh-route authorization overlay.

## Preserved `chonhac` DEC-025C

- plan: `pm-gh-5650852312`;
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`;
- job: `eec59b13651c54559c10ce204380a68e`;
- branch: `ai/eec59b13651c`;
- workspace: `/home/sonvh/.coding-platform/workspaces/eec59b13651c54559c10ce204380a68e`;
- approved `chonhac` source baseline remains `b143fbb001c2006ec82570619802b607085fbeb0`;
- last verified status before #221 local activation: `blocked`;
- top-level result: `reassessment_stopped`;
- nested reassessment: `action=stop`, `reason=input-token budget exceeded`, signal `hard_budget_overrun`;
- cache-aware durable `progress.input_tokens = 2,274,574`;
- effective `max_input_tokens = 2,000,000`.

This is not the historical cache-accounting bug. Existing telemetry already preserves gross/cached input usage and charges cache-miss input tokens; later Antigravity attempts legitimately contributed uncached usage that pushed the durable counter above 2M.

Operational constraint before local activation/action: do not execute historical budget actions, manually resume, mutate database/counters, force-complete, or create a replacement plan/job. Pending/used control actions remain durable evidence and must not be edited, backfilled or replayed manually.

## Global operational gates

- Normal flow: issue -> `ai/*` branch -> deterministic tests/CI -> PR -> eligible PM merge.
- Never force push.
- Developer agents never merge; PM may merge eligible in-scope work after required gates.
- Human Owner retains protected architecture/security/production/governance/material-budget authority.
- Production deployment is never implied by PR merge.
- Do not restart/rebuild platform services while engineering work is active.
- Runtime durable state is authoritative; never edit durable state to bypass the state machine.
- Potentially failing Human Owner command blocks must remain isolated from the parent interactive shell.

## Immediate next safe actions

1. Keep DEC-025C blocked and verify there is no other active engineering work before local rollout.
2. Fast-forward the local PCP repository to exact `main` `2f4babbe33dfcf96fe6d6ef500243d2a0baec020`; do not merge/rebase local source into the rollout target.
3. While DEC remains blocked, run the required deterministic PCP/platform source checks before any restart.
4. Only if source, idle and test gates pass, restart/rebuild once as required to load the merged Runtime source. Do not perform a second restart while work is active.
5. Verify deployed Runtime includes `control_actions_input_tokens` and that the same DEC job/workspace/source/branch/counters remain preserved, still blocked, with `input_tokens=2,274,574` and initial effective `max_input_tokens=2,000,000`.
6. Allow Runtime/notification flow to materialize a new exact `max_input_tokens +1,000,000` owner action. Do not execute or replay an old action. Merge/startup alone must not resume the job.
7. Human Owner deliberately executes only the newly materialized exact action. Then verify effective `max_input_tokens=3,000,000`, `input_tokens` remains 2,274,574, the same job/workspace/source continues, no durable counter decreases, and normal orchestration resumes.
8. If a later legitimate token stop occurs, a second explicit authorization may advance the same job to at most 4,000,000; never higher.
9. Keep #146 open for naturally occurring calibration evidence; do not create synthetic jobs solely to satisfy sample-size thresholds.
