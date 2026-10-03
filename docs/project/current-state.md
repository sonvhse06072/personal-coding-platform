# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
live Runtime/GitHub evidence remain authoritative over chat history. Completed
chronology belongs in Tier-3 history, not here.

Last updated: 2026-10-03 after Chợ Nhạc DEC-033 pilot reset, unified
ProjectBaseline activation and trusted-local developer rollout preparation.

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

- PCP main after PR #427 targets Runtime `1.0.94` and Antigravity host
  bridge `1.13`; ddev-executor remains `1.0.29`.
- Chợ Nhạc is the first project with
  `runtime.developer_permission_mode: trusted_local`.
- Trusted-local execution is deliberately narrow: exact direct Chợ Nhạc
  workspace + `antigravity_host` + execute/repair only. The developer keeps the
  normal terminal sandbox but receives a temporary `unsandboxed(ddev)` grant
  so it can run authoritative Drupal/PHP/Node verification through DDEV.
- Plan/evaluate, Codex/OpenCode, other projects/workspaces, direct Docker, sudo
  and remote/destructive Git remain bounded. PM/Runtime still own scope,
  deterministic final verification, review, merge and deploy gates.
- PR #427 merged as `c5cf4af4eb9072854c967a4a21928c2a9aca0412`
  after exact-head structure/Router/Runtime/ddev-executor CI passed.
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

Approved ProjectBaseline for **new** PCP-managed Chợ Nhạc work:

- active revision: `pilot-v1-2026-10-03-dec033`;
- immutable baseline source:
  `132c2ef767b595833677e9672d655872e07ba9b7`;
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

- DEC-033 is the canonical successor execution decision.
- Chợ Nhạc #63 is the single controlled-pilot execution umbrella for new work.
- The old GH-42 plan `pm-c63bc4f63c084dd1ac4eed9cf80ec87a` is preserved
  history, not the successor pilot critical path.
- WO-01 `GH-42-WO-01-show-domain-api` completed; PR #44 merged at
  `e8ccde0f9854fa86a9fa37fe9504fb63c90a477f`.
- WO-02 `GH-42-WO-02-show-frontend` completed; PR #45 merged at
  `dc8d60ae0c8ce913146e1c417d11ca37b20874ee`.
- WO-03 `GH-42-WO-03-availability`, job
  `c7011f370eb153acb7786b5a3e3cbff8`, remains blocked at
  `pm_reassessment_failed`; its latest evaluator findings are bounded
  Availability kernel/functional verification plus cleanup of one zero-test
  frontend file.
- Availability remains KEEP as Chợ Nhạc #62, but is outside the first pilot
  critical path.
- Before #63 intake: preserve WO-03 diff/evidence, cancel its Runtime job to
  release the direct-project lease, supersede WO-03..WO-08, and keep WO-01/02
  as completed historical checkpoints.

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

1. Roll local PCP to main containing PR #427 only while GH-42 WO-03 remains
   stably blocked and no engineering worker is active.
2. Verify deployed identities: Runtime `1.0.94`, Antigravity bridge `1.13`,
   ddev-executor `1.0.29`.
3. Preserve exact WO-03 status/diff/untracked-file evidence for Chợ Nhạc #62.
4. Cancel exact job `c7011f370eb153acb7786b5a3e3cbff8` after preservation so
   the direct-project lease can be restored/released; do not resume it again.
5. Explicitly supersede GH-42 WO-03 through WO-08. Leave WO-01/WO-02 completed.
6. Confirm the old plan has no ready active successor WorkOrder and close #42 as
   superseded execution scope.
7. Intake Chợ Nhạc #63 with planning profile `complex`, execution mode
   `supervised`, and revision `pilot-v1-2026-10-03-dec033`.
8. At each supervised WorkOrder checkpoint, Chat PM reviews durable evidence and
   releases the next ready set; developers may use trusted-local DDEV internally.
9. Keep staging/production and DEC-025 operator actions outside autonomous
   developer authority.
