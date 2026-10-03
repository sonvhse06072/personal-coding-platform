# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
live Runtime/GitHub evidence remain authoritative over chat history. Completed
chronology belongs in Tier-3 history, not here.

Last updated: 2026-10-04 after completing PCP #440/#441 and identifying the
remaining PILOT-01 durable decision as a pre-fix classifier false positive.

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md`.
3. Read this compact current-state snapshot.
4. Retrieve only the T2 topical documents and T3 episodes relevant to the
   current task.
5. Inspect live GitHub `main`, active issue/PR, local branch/worktree,
   Runtime/executor health, active WorkOrder/job and project lease before
   mutation.
6. Fetch raw CI/log/transcript evidence only when diagnostics or audit require
   them.

Memory-tier rules are in `context-memory-architecture.md`. Historical reusable
lessons are indexed in `history/episodes.md`.

## Current platform snapshot

- PCP main after PR #443 targets Runtime `1.0.99`, ddev-executor `1.0.30`,
  Antigravity host bridge `1.13` and model registry version `11`.
- #438 targeted-verification shell repair is complete through PR #439 at
  `841890e60e486d6e4e823b9919e9e79de6cbf6a0`.
- #440 Antigravity Developer Activity coalescing is complete through PR #442 at
  `c2ee43c35042a58883d2f739c5efba7b528bd4db`: transport-level response
  deltas are not persisted; Runtime emits one bounded/redacted completed response.
- #441 is complete through PR #443 at
  `38454b56adf02459a197dbc5ccbde024462d964d`; Drupal
  `config/schema/*.schema.yml` metadata is no longer treated as a destructive
  database/content migration while true migration/schema paths remain protected.
- #400 repository-CI parity is complete. Chợ Nhạc PR #64 merged at
  `af1e24a60fc43cae0c417dc312e7a7839f284b6b`; protected workflow changes are
  authorized by DEC-034 and use bounded changed-module Unit/Kernel/Functional
  verification without requiring Docker/DDEV privilege on the self-hosted
  repository runner.
- #406 incident learning is complete through PCP PR #436 at
  `cf34010e18cc0580a965098456872127fee1953a`. Runtime creates stable,
  deterministic, model-free incident candidates only for repeated/expensive/
  platform anomalies and carries bounded references through telemetry,
  continuity and PM evidence.
- #421 visual-preview evidence is complete through:
  - Chợ Nhạc collector PR #65:
    `f81e0ca86fdc9471854cfb702c43f5902e416a50`;
  - Chợ Nhạc evidence-redaction PR #66:
    `aa51045dacf5afe41c0d7ce3564c7303cd56847d`;
  - PCP PR #437:
    `7b1cd6ee050440ae624a242678246f5252189195`.
- `visual_quality` is a bounded final verification phase after
  `frontend_quality`. It requires a direct workspace, exclusive lease,
  enabled frontend preview and 1..4 local `visual_routes`; Runtime owns preview
  lifecycle and ephemeral evidence requests.
- Chợ Nhạc visual evidence uses viewports 360/390/430/768/1024/1440 and captures
  route/viewport, HTTP/navigation, console/page errors, failed request paths,
  DOM landmarks, horizontal overflow and local screenshot hashes. Textual
  evidence redacts common secrets and strips embedded URL query/fragment data.
- Screenshot capture alone is not represented as multimodal review.
  `image_reviewed=false` forbids pixel-level/aesthetic claims by a text-only
  evaluator.
- PM planning can require configured `frontend_quality` and `visual_quality`
  phases for material user-facing UI WorkOrders.
- Chợ Nhạc targeted Runtime verification follows changed custom Drupal modules
  and runs their Unit/Kernel/Functional suites instead of hard-coding Show.
- `gemini-3.8-flash-medium` is correctly modeled as no-explicit-effort while
  registry-v10 persisted effort metadata remains backward-compatible for
  blocked-job recovery.
- Chợ Nhạc remains the first trusted-local project: exact direct workspace +
  `antigravity_host` + execute/repair may use bounded DDEV; plan/evaluate,
  Codex/OpenCode, direct Docker, sudo, remote/destructive Git, merge and deploy
  remain outside developer authority.
- PM-controlled merge remains enabled for Chợ Nhạc routine/standard WorkOrders
  under exact-head CI/review/protected-boundary gates. Developer agents never
  merge; production is never implied.
- The #146 efficiency implementation program is complete. Future efficiency
  work starts from natural telemetry/incident evidence in focused issues rather
  than keeping a perpetual umbrella or creating synthetic tasks.

For executable details, inspect code/tests on current `main`. Historical
rollout/incident rationale belongs in `history/episodes.md`.

## Chợ Nhạc project state

Approved ProjectBaseline for **new** PCP-managed Chợ Nhạc work:

- active revision: `pilot-v1-2026-10-03-dec033-r1`;
- immutable baseline source:
  `132c2ef767b595833677e9672d655872e07ba9b7`;
- r1 was activated by PCP PR #429 at
  `95f4d8a5522112efa4ad0f7e710be0641a5d9159` after the first #63 planning
  attempt exposed missing legitimate Profile source references;
- r1 adds protected `docs/14-cho-nhac-profile-implementation-plan.md` and
  `docs/15-account-email-verification-producer-plan.md` to requirements;
- the original `pilot-v1-2026-10-03-dec033` revision remains immutable and
  explicitly resolvable;
- PCP baseline activation merged through PR #425 at
  `ccdd1712ff8ea75a14a061b30122dc4988558630`;
- pre-existing GH-42 plan/jobs keep their stored
  `mvp-v1-2026-10-01-completion` baseline until explicitly superseded;
- protected completion authority includes the current MVP contract,
  permissions/access matrix, business rules and architecture documents pinned
  by `config/project-baselines.yml`;
- direct project root: `/home/sonvh/chonhac`;
- runtime mode: `workspace_mode: direct`;
- exclusive engineering lease: enabled;
- AI branch prefix: `ai`.

The immutable ProjectBaseline source is an authority boundary, not a claim that
the live product repository must remain at that commit.

Current implementation evidence:

- DEC-033 remains the canonical controlled-pilot execution decision.
- Active plan: `pm-5cd9ec06f74b4feba4db5a1507ab35f0`.
- Current WorkOrder: `GH-63-PILOT-01`.
- Preserved direct job: `c02defa348fc5b19a0bd021e2697571e`.
- Current branch: `ai/c02defa348fc`.
- Latest published checkpoint: 39 /
  `wo:blocked:001560a3cf097e489a0f737b6cdb5fd25765e57b0f8e56c897166f933e1f0c3d`.
- Current state: `waiting_human` after successful recovery from the old
  deterministic verifier block.
- Latest verification: passed in `targeted_tests`, `static_analysis`, and
  `frontend_quality`.
- Latest independent review verdict: pass with zero findings.
- Current PM decision trigger: `destructive_migration`, diagnosed as a
  path-classifier false positive from
  `web/modules/custom/cho_nhac_show/config/schema/cho_nhac_show.schema.yml`;
  developer/reviewer evidence found no destructive schema/data migration.
- Progress remains 0/8 completed; PILOT-02..PILOT-08 are untouched/pending.
- The earlier `pm_reassessment_failed` / Flash Medium effort incident is
  repaired at the platform layer and is no longer the current blocker.
- Checkpoint-39 activity identified the current failure as a PCP verification
  wrapper defect rather than a Chợ Nhạc product/test defect: `ddev drush cr`
  passes, then the changed-module runner fails before PHPUnit with
  `modules: unbound variable`.
- PCP #438 repairs the nested DDEV shell boundary by using raw argv execution
  while preserving working-tree changed-module detection relative to `HEAD`.
  Do not resume PILOT-01 until the accepted #438 fix is present in the locally
  running platform and the old wrapper fingerprint can no longer execute.
- Dashboard activity authority for the job remains the job Activity view backed
  by `/v1/dashboard/jobs/{job_id}/events`; authenticated `JobView` intentionally
  omits internal checkpoint/progress/activity details.
- Do not reroute merely because the job is blocked. Preserve the same
  job/workspace/counters and recover only after the platform verifier is fixed.
- Chat PM has approved PILOT-01 scope but **generated PILOT-02..PILOT-08 must not
  be released unchanged**. After PILOT-01 is accepted/merged, create a successor
  ProjectBaseline pinned to the then-current governed Chợ Nhạc main (including
  the accepted PILOT-01 and current verification/visual tooling), then create
  one successor supervised plan for the seven remaining slices using the
  replan contract in Chợ Nhạc #63.
- Frontend-heavy successor WorkOrders should use the newly available
  `frontend_quality -> visual_quality` contract with concrete bounded routes
  only when those routes are renderable by the WorkOrder.

Historical DEC-025 and GH-42 execution are retired. Do not recreate, reroute or
resume them.

## Active PCP follow-up work

There are currently **no open PCP implementation issues**.

#438/#439, #440/#442 and #441/#443 are completed. The #146 efficiency umbrella
and its final children #400/#406/#421 remain closed. New PCP work should start
only from a fresh concrete Runtime/GitHub defect rather than reopening these
incident repairs.

## Recently completed reusable work

Completed implementation chronology does not remain in T1. Important recent
examples now belong in `history/episodes.md` and GitHub/Runtime history:

- exact-diff protected-signal authorization (#387 / PR #388);
- collaboration budget/continuation/recheck/handoff hardening
  (#389, #391, #393, #395, #397 and their PRs);
- PM approval-output contract correction (#401 / PR #402);
- deterministic verification/Kernel DB/retry-loop hardening
  (#404 / PR #405);
- Chợ Nhạc GH-42 WO-01 / PR #44;
- PHP-runtime capability advertisement (#399);
- trusted-local Chợ Nhạc developer execution (#426 / PR #427);
- frontend_quality exposure to PM planning (#430 / PR #431);
- changed-module Drupal targeted verification (#432 / PR #433);
- Flash Medium capability / reviewer-context recovery (#434 / PR #435);
- Chợ Nhạc repository-CI parity (#400; Chợ Nhạc PR #64 / DEC-034);
- deterministic incident-learning candidate / PM triage (#406 / PR #436);
- automatic visual-preview evidence loop (#421 / PR #437) plus Chợ Nhạc
  collector/redaction PRs #65/#66.

## Global operational gates

- Normal engineering flow: issue -> bounded WorkOrder -> deterministic
  verification/review -> PR/exact-head CI -> PM review -> eligible PM merge.
- Never force push.
- Developer agents never merge.
- Human Owner retains protected scope/architecture/security/destructive-data/
  production/governance/material-budget authority.
- A Human Owner request is a high-authority input to PM reasoning, not an
  automatic guarantee that the proposed tactic is optimal. PM should verify,
  assess and recommend before material execution when alternatives matter.
- Routine reversible in-scope actions should not create needless owner approval
  loops.
- Production deployment is never implied by PR merge.
- Runtime durable execution state is authoritative; never hand-edit it to bypass
  the state machine.
- Do not restart/rebuild platform services while engineering work is active.
- Direct-workspace operations must preserve Human Owner changes; never
  reset/stash/clean/discard them to make automation succeed.
- Broad Docker/system/image/volume prune remains prohibited.
- Time-sensitive claims such as active jobs, leases, branch/HEAD, PR/CI and
  service health must be checked live before acting.
- The approved ProjectBaseline stays pinned until an explicitly approved
  successor revision is activated.
- PM merge evaluation must stop when the final exact diff introduces a genuine
  Human Owner decision boundary, even if earlier versions of the diff were
  approved.

## Immediate next safe actions

1. Keep PILOT-01 at its preserved `waiting_human` checkpoint while #441 is
   merged and rolled into the local platform; do not reroute, recreate the job,
   or release generated PILOT-02.
2. Fast-forward local PCP `main` after #441 and restart PCP once. Verify:
   - Runtime `1.0.99`;
   - ddev-executor `1.0.30`;
   - Antigravity bridge `1.13`;
   - model registry `11`.
3. Confirm the running scope classifier no longer reports
   `destructive_migration` for
   `web/modules/custom/cho_nhac_show/config/schema/cho_nhac_show.schema.yml`.
4. The existing durable Human decision was created before #441 and does not
   rewrite itself on rollout. Resolve it only against the exact unchanged
   PILOT-01 diff/decision key. An approval, if the Human Owner chooses it, must
   explicitly record that this is clearance of the diagnosed classifier false
   positive and is **not** authorization for destructive migration/data writes.
5. After the exact decision is resolved, allow the same job/workspace/counters
   to continue through delivery and exact-head Chợ Nhạc CI. Do not reroute or
   reset provider state.
6. When PILOT-01 is accepted/merged, stop at the supervised checkpoint. Do
   **not** continue generated PILOT-02.
7. Create/activate a successor Chợ Nhạc ProjectBaseline pinned to the governed
   post-PILOT-01 main, then intake one supervised successor plan for exactly the
   seven remaining slices using #63's replan contract.
8. Keep staging/production, public recruitment legal approval, Availability
   salvage, Professional Reviews, Band and payment/ticket commerce outside this
   pilot path.
