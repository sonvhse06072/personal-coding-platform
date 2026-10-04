# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
fresh Runtime/GitHub evidence remain authoritative over chat history. This file
is an index, not authority to change the approved baseline or protected scope.

Last updated: 2026-10-05 theo owner release-helper v4 audit lúc
`2026-10-04T18:20:13.259778+00:00`. V4 chưa POST /continue; một bounded no-POST recovery v5 đã được chuẩn bị.

## Resume order

1. Read root `AGENTS.md`, `docs/project/README.md`, then this snapshot.
2. Read only relevant T2 contracts and T3 episodes in `history/episodes.md`.
3. Check live issue/PR, exact source, Runtime health, active jobs, project lease
   and local Git before any mutation. Older snapshots are evidence, not live locks.

Memory-tier policy: `context-memory-architecture.md`.

## Accepted platform / local state

- Runtime `1.0.106`; Router/executor healthy; executor `1.0.31`.
- Owner audit v2 observed active engineering jobs = 0 and executor active_jobs = 0.
- Local PCP is clean `main@e7fb6d364f109a2ddee979d3a040367b03d87f73`.
  Later PCP handoff PRs are docs-only; do not restart just to obtain them.
- Chợ Nhạc is clean `main@aa8e68dd9aea6740de446151eb97615931de9b40`.
  Historical `ai/c02defa348fc` ref remains at
  `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba`.
- #463 / PR #464 is complete: planning source references are restricted to the
  sorted/deduplicated `ProjectBaseline.references` allowlist. Authority-only
  paths never become eligible references by implication.
- #466 / PR #468 is implemented, merged and locally accepted. Historical GET
  reads preserve template visual routes through non-executable snapshot models;
  executable WorkOrder / PM proposal validators remain strict. No repeat rollout,
  diagnostic or restart is needed.
- In-process replay proof is not described as an HTTP POST replay test. Digests
  from different probes are compared only with the same serialization contract.

## Chợ Nhạc approved frame

- Active baseline for new work: `pilot-v1-2026-10-04-dec033-r3`.
- Immutable authority source: `aa8e68dd9aea6740de446151eb97615931de9b40`.
- r3 preserves r2 source/authority and adds the authorized local-only
  `docs/26-local-demo-workflow.md` to requirements/quality-policy references.
  There are 27 reference paths; `docs/12-launch-metrics.md` remains authority-only.
- r2 at the same source, r1 at `132c2ef767b595833677e9672d655872e07ba9b7`,
  and the original `pilot-v1-2026-10-03-dec033` stay immutable/resolvable.
  Do not create r4, rewrite r3, or add references to fit a rejected proposal.
- Direct project root `/home/sonvh/chonhac`; configured base `main`;
  `workspace_mode=direct`, exclusive engineering lease enabled, AI prefix `ai`.
- DEC-033 remains the controlled-pilot execution decision. Historical DEC-025 and
  GH-42 execution are retired, not candidates for resume/reroute/recreation.
- PILOT-01 / GH #61 is accepted and merged through Chợ Nhạc PR #67 at the current
  authority source. The product head was `88dd4f60...`; final product diff was
  16 files / +223 / -56, within its <=25-file budget. Do not reimplement it.
- CI governance repairs #68/#69 and #70/#71 preserve documentation authority and
  isolated PostgreSQL 17 verification; the repository runner does not gain
  Docker/DDEV privileges.

## Historical reconciliation and lease — complete

Supersession snapshot `2026-10-04T16:20:55.930831+00:00` proved 29 exact supported
supersessions with zero model calls. Historical plan
`pm-5cd9ec06f74b4feba4db5a1507ab35f0` and the three rejected plans
`pm-095d6aea0fe94901bbf692fa7d113fc2`,
`pm-a72e960c0f3b458897831cff3fb51a30`,
`pm-ac6a52e6019947adab8744a7ada72011` are lifecycle=superseded.
PILOT-02..08 map to the approved seven successor WorkOrders; PILOT-01 has no
replacement because its product was merged. Source state/history is not rewritten
as implementation success. Mapping details:
`pilot-successor-reconciliation-map-b0748be-2026-10-04.md`.

The supported historical cancel was sent once. Audit v2 now proves:

- job `c02defa348fc5b19a0bd021e2697571e` is `cancelled`;
- exact generation-9 lease is `released`, with recorded update
  `2026-10-04T16:47:00.470307+00:00`; owner identity is retained;
- preview absent; `resource_quiesce` is quiesced=false/data_removed=false;
- `direct_base_restore` succeeded to clean `main@aa8e68dd...`, reused=false;
- progress/result and all five immutable plan rows are preserved;
- full pre-cancel checkpoint hash is reproduced by restoring the pre-existing
  blocked `resource_quiesce` on a RAM copy and removing the new restore field.
  Matched case: `RESTORE_PREEXISTING_BLOCKED_QUIESCE`.
- The hash is `639bf30eb2b7e796d5a5eafe8ffd315375c65491f844f42e12e0ccb16136344c`.
  No reconstruction was written to the database.

Owner artifact `chonhac_post_cancel_audit_v2.json` SHA256:
`b7e11836b7c5a1ab7339fb36e727445a4695ac719871f30e40436f46f312d76b`.
Acceptance and conditional next action are recorded in Chợ Nhạc #63 comment
`5982524270`. Do not repeat cancel, alignment, supersession, intake or checkpoint
probes. The old audit's pop-both-fields comparison was invalid for a field that
already existed and was overwritten; its STOP did not imply rollback.

## Approved candidate — held, not yet released

Plan: `pm-b0748be27f8446a0813c2d1fe7d697fd`.
Content approval: #63 comment `5981710459`;
review details: `pilot-successor-pm-review-b0748be-2026-10-04.md`;
contract/fixture ownership: `pilot-successor-review-2026-10-04.md`.
These are execution evidence, not added ProjectBaseline references.

The owner audit v2 confirms unchanged plan digest
`f667ffe9d27fc3824f550089cf09269b0cfa7ccc58654d8c9e8a30e91ac7ab7d`,
active `supervised_hold`, generation 1, held, checkpoint 45, seven exact pending
agent rows and zero child jobs. Ready set contains only
`AP-MVP-01-artist-profile-data-curation`.
Checkpoint key: `plan:supervision-initial:pm-b0748be27f8446a0813c2d1fe7d697fd`.
The exact continuation identity must be verified from Runtime immediately before
using the supported `/continue` endpoint; a held/readable plan is not execution.

The seven sequential WorkOrders / issues / adaptive file targets are:

1. `AP-MVP-01-artist-profile-data-curation` — #48 / 45 / complex.
2. `AP-MVP-02-artist-profile-public-experience` — #49 / 55 / complex.
3. `EE-0-01-event-backend-domain-api-access` — #56 / 90 / critical.
4. `EE-0-02-public-event-discovery-detail` — #57 / 55 / complex.
5. `EE-0-03-studio-event-management-participation-program` — #58 / 65 / complex.
6. `AP-MVP-03-generalized-verified-performance` — #50 / 45 / complex.
7. `EE-0-04-event-engagement-analytics` — #59 / 35 / critical.

Keep all 42 acceptance criteria, linear dependencies, risk flags/profile floors,
concrete visual routes and local fixture ownership. #50 has frontend_quality
before visual_quality and only EventParticipation as a live pilot provider.
No Booking provider/query/contribution, public recruitment, Reviews, Band domain,
Audience identity/feedback, payment or staging/production seed/deployment.

## Next exact release gate

PM accepts historical lease retirement and conditionally authorizes only the
candidate's generation 1 / checkpoint 45 / ready AP-MVP-01. No `/continue` has
been called by PM in this handoff. This does not authorize later generations.

Owner control inventory at `2026-10-04T17:44:58.825827+00:00` confirms all six
v1 competing-plan flags were false positives: four validation-fixture plans and
two Chợ Nhạc plans have completed orchestration and nine completed WorkOrders,
no pending rows. Runtime `active_plans()` excludes completed orchestration even
when the immutable proposal remains ready and lifecycle remains active. Do not
supersede, cancel or edit these completed history records. Exact IDs/evidence and
helper review are recorded in Chợ Nhạc #63 comment `5982766542`.

Owner release-helper v2 at `2026-10-04T17:56:22.670521+00:00` passed the control
inventory (17 plans, no competing plan, no candidate job), then stopped with
`SELECTED_ROLE_QUOTA_UNOBSERVED` at deterministic Router/WorkOrder-budget
validation. `continue_subprocess_started=false`; this attempt did not release.
The audit's provider_state contained only `quota:codex_chatgpt_plus` at pressure
0.16. Antigravity snapshots expired at 17:56:15/16 UTC, before that audit. The
artifact does not include the exact later routing input or selected role/model,
so do not claim a particular model was chosen or that all provider quota is gone.
Collector `status=ok` and `last_success_at` do not renew upstream `captured_at`.

Owner release-helper v3 at `2026-10-04T18:11:07.668846+00:00` ran one
standard quota refresh with zero helper model calls, passed the global control
inventory, and still stopped before `/continue`. Router selected `codex_terra`
for planner/executor with fresh observed `quota:codex_chatgpt_plus` pressure
0.16. Evaluator was `openrouter_qwen3_coder_free`; v3 stopped only because
`quota:openrouter_free` was unobserved. Candidate remained held and no marker/
child job was created by that STOP.

That last gate was stricter than checked-in Runtime/Router semantics. The
OpenRouter free registry contract explicitly states
`free_tier.authoritative_remaining_available: false`: PCP has no authoritative
remaining-quota observation to demand for that selected model. Router defaults a
missing ProviderState to healthy/available; an actual provider failure is recorded
durably and routed through bounded provider failover. Do not infer unlimited
OpenRouter capacity from this: it only means absence of an impossible
authoritative remaining-quota signal is not itself a pre-release blocker.

Use `chonhac_release_ap_mvp_01_once_v4.py`. V4 preserves v3's one standard
quota refresh, exact completed-plan proofs, generation/continuation identity,
contract/budget/review validation, reserve policy, marker and no-later-generation
boundary. Selected models still require fresh observed quota unless their exact
checked-in model contract says authoritative remaining allowance is unavailable.
Any explicit observed unavailable/unhealthy/stale/reserve state still blocks,
including for OpenRouter. Model/quota-group mismatches fail closed. No provider
is forced and no Runtime/provider policy is changed.

V4 SHA256:
`fb5e2085e18da668624c44c7bf43de60cc3646be9cc6e03c007ae612488e1444`.
19 focused v4 regressions PASS, including the exact v3 role selection projection,
missing Codex observation/refused reserve, explicit OpenRouter unavailable
enforcement and unchanged mutation surface. These are mocked/helper checks, not
WSL release evidence. Decision/evidence is also in Chợ Nhạc #63 comment
`5982969505`. No extra historical audit/inventory/cancel is required.

Owner v4 subsequently passed its full outer preflight and created the original durable attempt marker, but the inner release audit stopped **before POST**. Its structured result proves `continue_post_attempted=false`, `continue_post_acknowledged=false`, and `runtime_may_execute_models_after_release=false`. The sole failure was an exact health mismatch: Runtime `/health` reported `degraded` / executor `down` while the direct executor health probe in the same audit was `ok`, version `1.0.31`, active_jobs=0; active engineering jobs also remained 0. Git stayed clean on Chợ Nhạc `main@aa8e68dd...`. V4 result SHA256: `bef0672fa55df1eafea56cc7c41629a1b9b1779f56e6b45be3bd29712ceb6845`.

Do **not** delete the v4 attempt marker and do not rerun `--release-once`. Use only the evidence-pinned recovery helper `chonhac_release_ap_mvp_01_resume_v5.py`. V5 requires the exact v4 result hash plus exact original marker identity, creates a second O_EXCL resume marker, and re-runs all release gates. It treats only the observed Runtime-executor mismatch as retryable health noise, and even then requires two consecutive fully healthy/idle samples; router failure, executor failure, active work, version drift, quota/reserve/policy failure remain blocking. V5 SHA256: `e9eac8cfedff283ccb2aaf2f1ae3562d9243e6d88df65e53edd4eec4263a8e65`; 15 focused helper checks PASS. No WSL v5 execution has been observed yet.

Before that single control-plane request:

- recheck the proven historical/plan evidence, exact candidate digest/hold,
  current Git and remote base, healthy idle Runtime/executor and released lease;
- inspect other plans so the `/continue` endpoint's internal global tick does not
  unexpectedly select another runnable plan; read-only checks are not a global
  atomic lock against concurrent operators;
- validate all seven contracts against installed baseline/project capabilities;
- use a deterministic Router evaluation for AP-MVP-01 with fresh quota and the
  canonical WorkOrder task/repository hints; apply the actual WorkOrder budget
  policy rather than hand-editing profile/risk/provider choices;
- keep false availability, reserve threshold and review policy intact. The owner
  snapshot had Codex pressure 0.16, Gemini 0.99912 and Claude/GPT 1.0 unavailable,
  but it must not be reused as current capacity. Older quota windows are not
  evidence of present capacity. Router may report preferred reviewer independence
  unavailable under its existing fallback policy; never label that cross-provider
  independence as satisfied.

Use one durable pre-request attempt marker. A marker alone does not prove a POST
occurred; a timeout does not prove no mutation. Preserve structured failures and
use read-only collect after uncertainty, never delete the marker/repeat intake.
The supported `/continue` may launch a real child job and consume model quota.
Runtime owns that launch/routing/workspace; the helper must not create a job or
write a lease directly. Verify only the deterministic AP-MVP-01 child identity.
After release, a new AI checkout and dirty worktree may be legitimate progress;
do not apply pre-release clean-main assumptions to running implementation.

## Active separate platform follow-up

PCP #474: fix `_quiesce_stable_manual_job` detection of persisted orchestrated
jobs. Raw `cp_jobs` does not contain top-level work_order_id; durable identity is
in checkpoint metadata. Existing tests used synthetic top-level fields and did
not cover this Storage shape. Current source is not fixed by this docs update.

The accepted Chợ Nhạc incident is a direct-workspace preserve/no-op, not data
removal. #474 does not require restarting/replanning this accepted successor.
Do not generalize that safety conclusion to isolated-workspace cleanup. The
issue still requires a bounded implementation and real-shaped regressions.

## Standing execution / quality boundaries

- Normal flow: bounded issue/WorkOrder -> implementation/evidence -> deterministic
  checks and required review -> exact-head CI -> PM review -> eligible PM merge.
- Developers never merge; force push and production deployment remain forbidden.
- Human Owner retains protected scope/architecture/security/destructive-data/
  production/governance/material-resource decisions. CI alone is not approval.
- Preserve durable history, counters, anomaly circuit breakers and adaptive
  healthy-progress behavior. Never use SQL/state rewrites, reset, clean, stash,
  quota overrides or endless retries to remove an operational gate.
- Never restart/rebuild while engineering work is active. No broad Docker/image/
  volume prune. Routine in-frame work should not create avoidable owner loops.
- Trusted-local Chợ Nhạc execution remains scoped to direct workspace plus
  antigravity_host execute/repair. Plan/evaluate, Codex/OpenCode, Docker/sudo,
  remote/destructive Git, merge and deploy do not gain authority by this handoff.
- Runtime owns preview/visual evidence. Visual quality follows frontend quality,
  exact lease and 1..4 renderable local routes. Screenshot capture alone is not
  multimodal/pixel review; image_reviewed=false forbids aesthetic claims.
- Current changed-module Drupal verification covers Unit/Kernel/Functional;
  CI, supported phases, authority rules and anti-loop behavior are not weakened.
- Helper tests must exercise real-shaped collector -> gate -> failure reporting,
  missing fields, false-vs-zero, timeout/partial outcomes and refusal-before-write.

Completed platform chronology belongs in T3 and GitHub, not active blockers.
Relevant completed references include #146, #387/#388, #389/#391/#393/#395/#397,
#399, #400 (Chợ Nhạc #64 / DEC-034), #401/#402, #404/#405, #406/#436,
#421/#437 (Chợ Nhạc #65/#66), #426/#427, #430/#431, #432/#433, #434/#435,
#438/#439, #440/#442, #441/#443, #446/#447, #451/#452, #453/#454,
#455/#456, #457/#458, #459, #461/#462, #463/#464 and #466/#468.
Failed/non-orchestrated planning attempts and the original intake attempt marker
remain evidence; `usage=null` never proves a model call did not occur.
