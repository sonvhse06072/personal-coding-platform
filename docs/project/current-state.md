# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
live Runtime/GitHub evidence remain authoritative over chat history. Completed
chronology belongs in Tier-3 history, not here.

Last updated: 2026-10-03 after Chợ Nhạc PILOT-01 blocker diagnosis and PCP
anti-loop/model-capability verification repairs through Runtime 1.0.95.

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

- PCP main after PR #435 targets Runtime `1.0.95`, Antigravity host
  bridge `1.13` and model registry version `11`; ddev-executor remains
  `1.0.29`.
- PR #431 exposes configured `frontend_quality` to PM WorkOrder planning so
  frontend-heavy slices can require typecheck/lint/unit/build/Chromium evidence.
- PR #433 makes Chợ Nhạc targeted Drupal verification change-aware: Runtime
  runs Unit/Kernel/Functional tests for changed custom modules instead of
  hard-coding Show tests.
- PR #435 corrects `gemini-3.8-flash-medium` as a no-explicit-effort model,
  preserves legacy registry-v10 low/medium/high choices as ignored metadata,
  omits stale effort at the Antigravity adapter, and preserves actionable
  reviewer findings across PM/provider failures on resume.
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

- DEC-033 is the canonical successor execution decision.
- Chợ Nhạc #63 is the controlled-pilot execution umbrella.
- The old GH-42 plan `pm-c63bc4f63c084dd1ac4eed9cf80ec87a` is retired
  history. WO-01/WO-02 remain completed evidence; WO-03 evidence was preserved
  under #62, its Runtime job was cancelled, and WO-03..WO-08 were superseded.
- First #63 intake plan `pm-1c670cfa6e1542579b9d4aefc70e4eb0` failed only
  because the original DEC-033 baseline omitted a legitimate protected Profile
  reference. Pilot baseline r1 repaired that omission.
- Active #63 plan:
  `pm-5cd9ec06f74b4feba4db5a1507ab35f0`.
- Current WorkOrder: `GH-63-PILOT-01`.
- Current preserved job:
  `c02defa348fc5b19a0bd021e2697571e`.
- PILOT-01 deterministic verification passed targeted_tests, static_analysis
  and frontend_quality. Independent review produced one bounded actionable
  finding: `DEC031-CACHE-01`, requiring the mutable DEC-031 gate's config
  cacheability to propagate through generic ShowPosition access.
- The job then blocked at `pm_reassessment_failed` because PCP registry v10
  incorrectly invoked `gemini-3.8-flash-medium --effort low`, which the host
  CLI does not support. This was a platform failure, not a Chợ Nhạc code or
  provider-quota failure.
- PCP #434 / PR #435 merged at
  `e9da10dc03cf25fb3861b804dab485112474a2d8`. Runtime 1.0.95 can consume the
  persisted v10 choice, omit unsupported effort, and reconstruct the persisted
  reviewer finding as the primary developer repair instruction.
- Recovery for PILOT-01 is therefore **same job, same workspace, reroute=false**.
  Do not create a replacement job and do not clear the reviewer finding.
- Diagnostic caveat: authenticated `GET /v1/jobs/{job_id}` returns the bounded
  `JobView` and intentionally omits internal `checkpoint` and `progress`.
  Null jq lookups under `.checkpoint` are therefore not evidence that durable
  reviewer findings were lost; Runtime resume consumes the internal stored
  checkpoint directly.
- Chat PM reviewed the generated eight-WorkOrder plan. PILOT-01 is approved to
  continue; generated PILOT-02..PILOT-08 must not be released unchanged after
  the first supervised checkpoint because their child-issue detail, working
  file targets and frontend verification contracts are under-specified.
- #63 now contains the governed successor replan contract for exactly the seven
  remaining semantic slices. Replan only after PILOT-01 is accepted/merged.

Historical DEC-025 and GH-42 execution are retired. Do not recreate, reroute or
resume them.

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

1. While PILOT-01 remains stably blocked and no engineering worker is active,
   fast-forward local PCP main to include:
   - PR #431 / `0d1aacf6a864fa8314fb375de7ba515b51670c18`;
   - PR #433 / `834b3cf96cc0498685481f5306978f6c726074a1`;
   - PR #435 / `e9da10dc03cf25fb3861b804dab485112474a2d8`.
2. Restart PCP services at this stable blocker and verify Runtime `1.0.95`,
   Antigravity bridge `1.13`, ddev-executor `1.0.29`, and model registry
   `11`.
3. Resume exact job `c02defa348fc5b19a0bd021e2697571e` with
   `reroute=false` and `reset_transient_provider_failures=false`.
4. The first developer repair instruction must retain
   `DEC031-CACHE-01`; the former `--effort low` error is operational context
   only.
5. Let the same job repair the gate cacheable dependency, rerun deterministic
   verification/review/PM reassessment and deliver normally.
6. Review exact diff/evidence and merge PILOT-01 only if all gates pass.
7. At the resulting supervised hold, **do not continue generated PILOT-02**.
   Create one successor supervised plan for the seven remaining slices using
   the replan contract in Chợ Nhạc #63; once ready, supersede pending
   PILOT-02..PILOT-08 from the old plan.
8. Keep staging/production, public recruitment legal approval, Availability
   salvage, Reviews, Band and payment/ticket commerce outside this pilot path.

