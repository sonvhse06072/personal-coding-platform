# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
fresh Runtime/GitHub evidence remain authoritative over chat history. This file
is an index, not authority to change the approved baseline or protected scope.

Last updated: 2026-10-05 theo owner release-helper v2 audit lúc
`2026-10-04T17:56:22.670521+00:00` (00:56:22 ngày 05/10, giờ Việt Nam).
Control inventory đã qua; quota-observation gate STOP trước /continue.

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

Use `chonhac_release_ap_mvp_01_once_v3.py`. It retains v2's completed-row/job
consistency checks and IDs on control-inventory failure. It adds a bounded call
to the installed `ActiveQuotaTelemetryService.refresh()` once in the initial
preflight, after health/history/control gates and source-identity checks. This is
normal telemetry collection, not an availability/profile override. It writes
standard quota snapshot/collector-result records; it is NOT a read-only helper
mode. It does not call service.start(), store.init(), background polling or a
model. The inner release preflight does not refresh again; `--collect` remains
read-only and never refreshes or posts continuation.

The source-pinned collector retains provider observation timestamps, TTLs,
false availability and reserve policy. A successful refresh may still return
stale/absent provider observations and never implies permission to release.
V3 reports before/after quota scope IDs, timestamps and all three Router-selected
roles even when capacity validation stops. It never substitutes Codex, invents a
quota observation, treats an expired window as recovered, or relaxes a gate.
The final quota recheck also retains the failing role/key; any failure keeps
continuation uncalled. No additional historical audit/inventory/cancel script is
needed; the bounded release helper rechecks its prerequisites.

Helper SHA256: `6d59b3d55acf79229d1e0b8c4b257b9467b2c81d3b28c6042896ac853c0f13cb`.
142 unittest passed: 115 retained regressions plus 27 new quota/service/reporting
cases. Provider/DB/Router I/O was mocked; the uploaded quota timestamps were used
as a fixture, but synthetic role choices are not claimed as observed choices.
No v3 execution, live refresh or release has been observed in this PM step.
The original marker path, exact generation/continuation, all contract/budget/
review gates and later-generation exclusion remain unchanged.

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
