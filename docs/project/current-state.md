# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
live Runtime/GitHub evidence remain authoritative over chat history. Completed
chronology belongs in Tier-3 history, not here.

Last updated: 2026-10-04 after accepting and merging Chợ Nhạc PILOT-01 and
closing the related PCP/CI incident chain.

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

- PCP main currently targets Runtime `1.0.100`; PCP #451 targets Runtime
  `1.0.101` so newly registered supervised plans hold before their first
  WorkOrder launch. ddev-executor remains `1.0.30`, Antigravity host bridge
  `1.13`, model registry version `11`.
- PCP #446 / PR #447 is complete at
  `645200e1f0e1ea1902569f471a53d5b90699ece6`: canonical WorkOrder diff
  identity is source-commit-relative across Runtime-created commits,
  `no_effect` is turn-local, and reviewer/PM response-only semantic turns are
  not mislabeled as no-effect.
- #438 targeted-verification shell repair is complete through PR #439 at
  `841890e60e486d6e4e823b9919e9e79de6cbf6a0`.
- #440 Antigravity Developer Activity coalescing is complete through PR #442 at
  `c2ee43c35042a58883d2f739c5efba7b528bd4db`: transport-level response
  deltas are not persisted; Runtime emits one bounded/redacted completed response.
- #441 is complete through PR #443 at
  `38454b56adf02459a197dbc5ccbde024462d964d`; the
  `destructive_migration` path heuristic no longer treats Drupal
  `config/schema/*.schema.yml` metadata as a destructive database/content
  migration while true migration/schema paths remain protected.
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

- active revision: `pilot-v1-2026-10-04-dec033-r2`;
- immutable baseline source:
  `aa8e68dd9aea6740de446151eb97615931de9b40`;
- r2 is the post-PILOT-01 successor baseline authorized by the #63 replan
  boundary and tracked by PCP #449. It preserves the exact r1
  authority/reference categories while pinning the governed Chợ Nhạc main that
  includes PILOT-01 plus DEC-035/DEC-036 CI governance repairs;
- r1 remains immutable at
  `132c2ef767b595833677e9672d655872e07ba9b7` and explicitly resolvable;
- r1 was activated by PCP PR #429 at
  `95f4d8a5522112efa4ad0f7e710be0641a5d9159` after the first #63 planning
  attempt exposed missing legitimate Profile source references;
- r1 added protected `docs/14-cho-nhac-profile-implementation-plan.md` and
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
- Historical generated plan:
  `pm-5cd9ec06f74b4feba4db5a1507ab35f0`.
- PILOT-01 / GH #61 is accepted and merged.
- Chợ Nhạc PR #67 merged as
  `aa8e68dd9aea6740de446151eb97615931de9b40`.
- Exact product head validated before merge:
  `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba`.
- Current-base CI run 69 passed documentation authority, Composer,
  isolated PostgreSQL 17 Unit/Kernel/Functional verification, PHPCS and the
  controlled self-repair probe.
- Final PILOT-01 product diff remained 16 files / +223 / -56, within #61's
  <=25-file budget and without Event/payment/deployment scope expansion.
- Preserved historical direct job:
  `c02defa348fc5b19a0bd021e2697571e`.
- Preserve that job/workspace/counters as incident/work evidence; do not spend
  further model quota attempting to complete an already-merged product diff.
- Chợ Nhạc #68/#69 fixed PR documentation-authority range semantics by using
  merge-base-to-head while preserving the fail-closed checker.
- Chợ Nhạc #70/#71 restored PostgreSQL-backed repository CI after one-time
  PostgreSQL 17 provisioning on the self-hosted Chonhac-CI host. Repository CI
  still does not gain Docker/DDEV authority and uses isolated per-job clusters.
- Generated PILOT-02..PILOT-08 remain untouched/pending and must **not** be
  released from the old plan.
- Create a successor ProjectBaseline pinned to governed Chợ Nhạc main
  `aa8e68dd9aea6740de446151eb97615931de9b40` (or a later explicitly reviewed
  governance-only main if one is intentionally included), then create one
  successor supervised plan for exactly the seven remaining slices using the
  replan contract in Chợ Nhạc #63.
- Frontend-heavy successor WorkOrders should use
  `frontend_quality -> visual_quality` with concrete bounded routes only when
  those routes are renderable by the WorkOrder.

Historical DEC-025 and GH-42 execution are retired. Do not recreate, reroute or
resume them.

## Active PCP follow-up work

PCP #451 is the single focused active Runtime repair required before successor
pilot intake: newly registered `execution_mode=supervised` plans must create a
durable initial supervision hold before any WorkOrder job is created/enqueued.

The PILOT-01 incident repairs #438/#439, #440/#442, #441/#443 and #446/#447 are
completed. Chợ Nhạc CI incidents #68/#69 and #70/#71 are also resolved.

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

1. Complete PCP #451 with exact-head CI, merge, then roll local PCP to Runtime
   `1.0.101` only while no executor/model process is active.
2. Verify active Chợ Nhạc baseline remains
   `pilot-v1-2026-10-04-dec033-r2` at
   `aa8e68dd9aea6740de446151eb97615931de9b40`.
3. Do **not** resume, reroute or continue the historical PILOT-01 job merely to
   make Runtime state look completed; preserve it as incident/work evidence.
4. Do **not** release generated PILOT-02 from plan
   `pm-5cd9ec06f74b4feba4db5a1507ab35f0`.
5. Intake one supervised successor plan for exactly #48/#49/#56/#57/#58/#50/#59
   using r2. Confirm the new plan is at initial `supervised_hold` with zero
   WorkOrder jobs before reviewing/releasing it.
6. After the successor plan exists and exact replacement WorkOrder identities
   are known, supersede the old PILOT-01..PILOT-08 orchestration through the
   supported API; link PILOT-02..08 to their replacements and retire PILOT-01
   without replacement because it is already merged.
7. Keep staging/production, public recruitment legal approval, Availability
   salvage, Professional Reviews, Band and payment/ticket commerce outside this
   pilot path.
