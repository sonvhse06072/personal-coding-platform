# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
live Runtime/GitHub evidence remain authoritative over chat history. Completed
chronology belongs in Tier-3 history, not here.

Last updated: 2026-10-02 after GH-42 WO-02 platform-blocker diagnosis and
bounded source-continuity repair preparation.

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

- PCP source after #415 targets Runtime `1.0.92` while ddev-executor remains
  `1.0.29`: it includes #399 PHP-runtime capability advertising and repairs
  source-relative exact-diff / PM-reassessment snapshot handling for stale
  intent-to-add paths.
- The deployed local Runtime/service identities are time-sensitive. The current
  live rollout remains Runtime `1.0.90` / ddev-executor `1.0.29` until the
  stable WO-03 blocker checkpoint rolls out the merged platform fixes.
- PM-controlled merge is enabled for Chợ Nhạc routine/standard WorkOrders under
  the existing exact-head/verification/review/protected-boundary gates (#416).
  Developer agents never merge; complex/critical or unresolved protected
  decisions remain Human Owner gates.
- Exact-diff baseline-covered protected authorization is implemented for the
  bounded `security_boundary_change` case. It does not authorize new auth,
  credential transport, trust-boundary, production, destructive-data, scope or
  governance changes.
- Bounded collaboration now supports adaptive-budget consultations, same-worker
  continuation after a resolved consultation, recheck of an eligible resolved
  round, max-round PM handoff context preservation and compatibility hydration
  for older handoffs.
- Approval output contracts remain strict: an approval action has no unresolved
  blocking risk; non-blocking caveats belong in PM summary/developer guidance,
  not `unresolved_risks`.
- Healthy-progress non-blocking remains mandatory. Static profile/task counters
  alone are not Human Owner stop reasons while work is making meaningful
  progress inside the approved resource envelope.
- Direct workspace + exclusive Chợ Nhạc engineering lease + job-owned live
  preview and project-level Current-site preview remain the accepted local
  workspace model.
- Tiered Context & Memory Architecture is implemented with deterministic
  T0/T1 pinning and bounded T2/T3 retrieval. Vector/hybrid RAG remains deferred
  until a measured retrieval gap exists.
- Human Owner approved the #406 Incident Learning Loop / PM advisory-triage
  direction. The design is approved but implementation is not yet complete.
  It must extend existing TaskOutcome/continuity/tiered-memory mechanisms rather
  than add an always-on retrospective agent.

For executable details, inspect code/tests on current `main`. Historical
rollout/incident rationale belongs in `history/episodes.md`.

## Chợ Nhạc project state

Approved ProjectBaseline for new PCP-managed Chợ Nhạc work:

- active revision: `mvp-v1-2026-10-01-completion`;
- immutable baseline source:
  `6038857e33d3717321a54e35743fa8b9dbeba8d2`;
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

- Chợ Nhạc GH-42 is the active MVP implementation umbrella;
- plan: `pm-c63bc4f63c084dd1ac4eed9cf80ec87a`;
- WO-01 `GH-42-WO-01-show-domain-api` completed; PR #44 merged at
  `e8ccde0f9854fa86a9fa37fe9504fb63c90a477f`;
- WO-02 `GH-42-WO-02-show-frontend` completed; PR #45 merged at
  `dc8d60ae0c8ce913146e1c417d11ca37b20874ee`;
- WO-03 `GH-42-WO-03-availability` is the active preserved WorkOrder, job
  `c7011f370eb153acb7786b5a3e3cbff8`, currently blocked at
  `pm_reassessment_failed`;
- WO-03 deterministic static/targeted/full/frontend verification passed, while
  independent review correctly requested bounded repairs for scheduling-hint
  semantics, schedule-dependent cache invalidation and HTTP privacy/access
  coverage;
- the immediate blocker is PCP #415: PM isolated-clone patch materialization
  failed on a stale intent-to-add path before a PM repair decision could run;
- WO-04 through WO-08 remain dependency-ordered successors.

Before acting on WO-02, verify the live WorkOrder/job/branch/lease rather than
guessing an identity from WO-01.

WO-02 frontend guardrails:

- scope is public Show discovery/detail plus Booker Show management/create/edit;
- do not add Apply/Invite/Availability behavior before the corresponding later
  vertical slices are active;
- reuse the approved Drupal authenticated-session + CSRF boundary; do not invent
  a sign-in route, token transport or new auth mechanism;
- frontend renders server DTO/state and submits actions; it does not derive
  authorization, capacity or lifecycle transitions locally;
- `frontend/` changes require the configured Node 24 frontend-quality phase:
  typecheck, lint, unit tests, build and Playwright/browser verification;
- if backend-only verification becomes repeatedly expensive for a frontend-only
  diff, treat that as evidence for layered-verification calibration rather than
  weakening required final evidence ad hoc.

Historical DEC-025 PCP orchestration remains retired. Do not recreate, reroute
or resume it.

## Active PCP follow-up work

### #399 — advertise unavailable PHP runtime to coding agents

Status: implemented in source; rollout pending a stable checkpoint.

Container-backed Codex/OpenCode invocations now advertise `php_runtime=false`
through the existing invocation-capability contract. Project verification
metadata maps PHP-dependent phases to Runtime/DDEV ownership, and developer /
evaluator prompts forbid repeated impossible PHP/PHPCS/PHPUnit/PHPStan attempts
without treating skipped checks as PASS. Antigravity host capability remains
unchanged pending separate host-runtime evidence.

### #400 — Chợ Nhạc authoritative Kernel verification follow-up

Status: open for remaining repository-CI alignment.

Runtime/DDEV verification for the live Show Kernel target was corrected during
WO-01. Repository GitHub CI still needs an explicitly governed decision/update
if broader Kernel coverage is to become a protected workflow requirement.
Do not infer GitHub-CI coverage from Runtime verification or vice versa.

### #406 — incident learning loop and PM advisory triage

Status: Human Owner-approved design direction; implementation pending.

Use one bounded deterministic incident candidate for recurring/expensive/
platform failures and one PM classification at a meaningful checkpoint. Prefer
executable prevention over prose. Promote only reusable conclusions through the
existing T1/T2/T3/T4 memory lifecycle.

### #146 — efficiency initiative

Status: calibration/watch.

Use natural project evidence. Do not create synthetic work merely to collect
samples. Open narrow child issues for concrete recurring efficiency defects.

## Recently completed reusable work

Completed implementation chronology does not remain in T1. Important recent
examples now belong in `history/episodes.md` and GitHub/Runtime history:

- exact-diff protected-signal authorization (#387 / PR #388);
- collaboration budget/continuation/recheck/handoff hardening
  (#389, #391, #393, #395, #397 and their PRs);
- PM approval-output contract correction (#401 / PR #402);
- deterministic verification/Kernel DB/retry-loop hardening
  (#404 / PR #405);
- Chợ Nhạc GH-42 WO-01 / PR #44.

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

1. Merge and roll out PCP #415 / Runtime `1.0.92` only while WO-03 remains
   stably blocked and no engineering worker is active; preserve the exact
   Chợ Nhạc job/workspace/source/diff/counters.
2. Ensure local PCP source also contains #416 so Chợ Nhạc routine/standard
   delivery uses constrained PM-controlled merge instead of routine manual
   merge attention.
3. After health/version proof, resume the exact WO-03 job with no reroute or
   counter reset. PM reassessment should materialize the source-relative exact
   diff and route the existing AVL-001/002/003 findings to bounded repair.
4. Do not reinterpret AVL-001/002/003 as a new Human Owner product decision:
   they are repairs inside the already-approved Availability/discovery/privacy
   contract.
5. Keep #400 bounded to its remaining repository-CI follow-up; implement #406
   only through reviewed continuity/TaskOutcome/tiered-memory changes.
6. Keep deterministic context-memory evaluation in CI and do not add vector
   infrastructure without a measured retrieval gap.
