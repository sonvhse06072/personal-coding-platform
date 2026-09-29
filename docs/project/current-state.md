# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and live Runtime/GitHub evidence remain authoritative over chat history. Completed chronology belongs in Tier-3 history, not here.

Last updated: 2026-09-29 for #366 PM-001 launch crash-consistency repair.

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md`.
3. Read this compact current-state snapshot.
4. Retrieve only the T2 topical documents and T3 episodes relevant to the current task.
5. Inspect live GitHub `main`, active issue/PR, local branch/worktree, Runtime/executor health and any current lease/job before mutation.
6. Fetch raw CI/log/transcript evidence only when the task requires diagnostics or audit.

Memory-tier rules and the proposed Context Composer contract are in `context-memory-architecture.md`. Historical platform lessons are indexed in `history/episodes.md`.

## Current platform snapshot

- Checked-out launch baseline: `fb548c5ebb58e24b8a201f5a1b2c12846e928db9` (#365 merged via PR #371).
- Current checked-out source identities on `ai/366-orchestration-checkpoint-transitions`
  (not rolled out):
  - Runtime `1.0.72`;
  - Router `1.0.30`;
  - routing policy `19`;
  - ddev-executor remains `1.0.27`.
- PM-controlled routine merge is implemented and operationally proven. Developer agents never merge.
- Healthy-progress non-blocking remains mandatory: static task/profile/provider-failover counters alone are not Human Owner stop reasons while meaningful progress continues inside the approved resource envelope.
- On effective adaptive WorkOrders, `max_changed_files` is a semantic working target. Crossing it enters a bounded Product Manager reassessment; PM must be staffed with a different model from the Primary Developer and any approval is exact-diff-bound. Emergency overflow and actual sensitive/protected changed paths remain fail-closed boundaries. Legacy-hard WorkOrders retain strict file-count semantics.
- PM reassessment is repair-first for removable WorkOrder/out-of-scope implementation violations. Human Owner escalation requires a bounded necessity rationale showing why repair/revert/developer dialogue cannot resolve the boundary. A Human rejection of a PM-raised boundary requeues the same job for bounded repair without resetting workspace, diff, counters or WorkOrder.
- Protected diff signals such as dependency-manifest boundaries enter PM semantic reassessment before generic Router/Human escalation once deterministic verification passes. PM-directed repair returns immediately to the same Developer turn; generic Router cannot preempt that repair with the same protected signal.
- Routine provider recovery remains Runtime/Router responsibility while eligible capacity exists.
- Dedicated PCP BuildKit isolation is implemented through `pcp-builder`; the user's globally selected/default builder is not replaced.
- Direct workspace + Dashboard job-owned live preview for Chợ Nhạc is implemented and accepted.
- Project-level **Current site** preview is implemented and accepted independently of an active WorkOrder.
- Tiered Context & Memory Architecture is implemented through deterministic T0/T1 pinning plus bounded T2/T3 retrieval; vector/hybrid RAG is deferred because the current PCP benchmark passes without it.
- Current-site idle preview does not create an engineering job or hold the engineering project lease.
- Direct-job terminal cleanup must retire preview and safely return the exact clean job-owned branch to the configured existing local base branch before releasing the project lease.
- Terminal `completed/cancelled` jobs whose isolated Git workspace is already missing can now release exact orphaned PCP DDEV resources through a bounded inspect/revalidate/execute path; blocked/failed/nonterminal work remains ineligible.

For executable details, inspect code/tests on current `main`; historical rollout evidence is in `history/episodes.md`.

## Chợ Nhạc project state

Approved ProjectBaseline for new PCP-managed Chợ Nhạc work:

- revision: `mvp-v1-2026-09-27-governed`;
- immutable baseline source: `8383b0004ee649cb3ac0fef1e68f9ca40718005b`;
- document authority classes: Human Owner protected / delegated Design Owner / mutable execution / evidence-history;
- direct project root: `/home/sonvh/chonhac`;
- runtime mode: `workspace_mode: direct`;
- exclusive engineering lease: enabled;
- AI branch prefix: `ai`.

The immutable ProjectBaseline source is a governance baseline, not a claim that the live product repository must remain at that commit.

Last accepted live Current-site outcome from #309:

- Chợ Nhạc was clean on `main`;
- zero active engineering jobs;
- zero active Chợ Nhạc project leases;
- executor idle;
- Current site Frontend Ready at `https://chonhac.ddev.site:3100`;
- Backend URL `https://chonhac.ddev.site`.

Before any new mutation, re-read the live Chợ Nhạc branch/HEAD/worktree and Runtime lease/job state. Do not infer present state solely from this last-accepted snapshot.

Historical DEC-025 PCP orchestration is retired. Do not recreate, reroute or resume it; remaining/future DEC-025 evidence is Human Owner-managed in the Chợ Nhạc repository/operator workflow.

## Active PCP work

### #362 / #366 — Atomic WorkOrder lifecycle checkpoints

Status: WO-362-2 implemented locally on
`ai/366-orchestration-checkpoint-transitions`. PM blocked the first patch on
PM-001 only; the bounded repair is implemented and verified locally, pending PM
re-review. Dependency #365 merged via PR #371; parent #362 remains open.

#366 reuses #365 append-only checkpoint validation in a single store transaction
with exact WorkOrder locking, expected-source validation, lifecycle mutation and
attention retirement. Conflicts/failures roll everything back. Checkpoints cover
agent start, agent/operator waiting-human, accepted PR, no-PR/operator completion,
confirmed manual/PM merge, all existing block paths and same-job review-repair
reopening. Keys use durable identity and persisted source versions; later repair
or block episodes remain distinct. Evidence is whitelisted and bounded to 16 KiB.
Dependency evidence uses the existing graph as if the target state had committed;
accepted PRs do not unlock children, and merge unlock is atomic with its checkpoint.
Read-only `/progress` and `/orchestration`, state vocabulary, deterministic jobs,
recovery, supersession, notifications, leases and merge authority are preserved.

PM-001 adds an internal durable launch reservation, bound to exact plan/WorkOrder/
deterministic job, in the same insert as job creation. Startup skips held jobs;
only durable started proof releases them. Reconciliation recovers pre-execution
launches idempotently. Before workspace side effects, a locked claim enters the
existing in-flight state; genuine interrupted jobs still require explicit resume.
Standalone queued startup and public intake are unchanged. No replacement jobs,
new public states, budget resets or new decision gates are introduced.

Parent #362 has six sequential
children: #365 persistence/projection, #366 transition emission, #367 large-ticket
intake, #368 GitHub publication, #369 blocked evidence pack, #370 supervised
continuation/dogfood. Later children remain pending and must start from merged
main after their preceding dependency passes PM review/CI/merge. Parent #362
remains open through #370 acceptance.

Repair verification: focused launch/transition/store/orchestrator/API/recovery/
engine/contract/lease tests `188` passed; `17` new launch/startup cases and all `20`
existing checkpoint PostgreSQL tests passed (`37` real PostgreSQL tests total).
Full Runtime `754` passed; structure `103` passed; `git diff --check` passed.
Runtime reports one existing
dependency deprecation warning. PostgreSQL coverage includes
atomic commit, rollback before/after checkpoint insertion and on evidence overflow,
conflict/stale-identity rejection, dependency safety, concurrent exact retries,
attention rollback, repeated recovery episodes and store recreation. It uses
opt-in `PCP_CHECKPOINT_TEST_DSN` against a disposable database.
The reviewed `/tmp/issue-366-pm-review.patch` remains unchanged (SHA-256
`7731e92013f8961679f80185b19cdf1bc417fdedded5db94c28677fd9f8b8183`).
The repair artifact is `/tmp/issue-366-pm-review-delta.patch`, relative to that
exact reviewed tree, not HEAD. Local verification is not remote CI evidence.
No staging, commit, push, PCP restart/rebuild, Runtime job creation or Chợ Nhạc
mutation. Test execution uses read-only source mounts in disposable containers;
real PostgreSQL coverage uses a separate disposable database only.
The container-pytest workflow used the existing Runtime image with checkout
`config/` at `/config`; structure tests used a process-local Git safe-directory
override. Router/policy and executor source are unchanged; their suites were not
rerun. #367–#370 remain unimplemented.

### #146 — Efficiency initiative

Status: open for calibration/watch only.

Source phases A-F and clean low-touch validation are complete. Do not create synthetic jobs merely to close this umbrella.

Re-evaluate when at least one comparable natural project/task-type/role cohort reaches the configured minimum sample size (currently 5). Exclude validation fixtures, rollout/operator probes and deliberately adversarial recovery runs.

If calibration reveals a recurring concrete efficiency defect, open a narrow child issue rather than expanding #146 directly.

## Recently completed initiatives

The following are complete and no longer belong in active-state chronology:

- #224 healthy-progress executable alignment;
- #228 autonomous provider recovery;
- retired DEC-025C PCP orchestration;
- UI-CL-1 routing/review/repeated-failure/CI/supersession hardening;
- #277/#281 DDEV/BuildKit resource-hygiene initiative;
- #297 direct workspace + job-owned live preview;
- #309 project-level Current site preview;
- #313/#314/#317 tiered context/memory architecture, T1 compaction and deterministic Context Composer/evaluation;
- #282 bounded missing-workspace terminal DDEV resource release.
- #354 governed same-job delivered-PR review repair.
- #358 durable review-repair churn circuit breaker (merged via PR #361).
- #363 legacy auto-required verification (merged via PR #364).

Their reusable lessons and primary references are in `history/episodes.md`. Git/issue/PR/Runtime history remains the detailed audit source.

## Global operational gates

- Normal engineering flow: issue -> bounded branch -> deterministic verification/CI -> PR -> PM review -> eligible PM merge.
- Never force push.
- Developer agents never merge.
- Human Owner retains protected scope/architecture/security/destructive-data/production/governance/material-budget authority.
- Production deployment is never implied by PR merge.
- Runtime durable execution state is authoritative; never hand-edit durable state to bypass the state machine.
- Do not restart/rebuild platform services while engineering work is active.
- Direct-workspace operations must preserve Human Owner changes; never reset/stash/clean/discard them to make automation succeed.
- Project-level idle preview must yield to the exact direct engineering lease before job workspace mutation.
- Potentially failing Human Owner shell blocks must run in an isolated function/subshell/process so they do not terminate the parent shell.
- Broad Docker/system/image/volume prune remains prohibited; cleanup must be bounded to proven PCP-owned resources.
- Time-sensitive claims such as active jobs, leases, branch/HEAD, PR/CI and service health must be checked live before acting.
- Approved ProjectBaseline authority stays pinned to its immutable revision/source commit until an explicitly approved successor revision is activated; newer project HEAD alone does not advance project-frame authority.
- PM merge evaluation treats `human_owner_protected` baseline document changes as a Human Owner decision boundary; delegated design authority remains bounded by its governing decision.

## Immediate next safe actions

1. Re-review the #366 PM-001 delta with PM. Keep it unstaged/uncommitted/unpushed; CI remains a later mandatory merge gate. Leave running PCP services and Chợ Nhạc untouched. Do not begin #367 before #366 dependency completion.
2. Keep #146 in calibration/watch mode and collect only naturally occurring routine-task evidence.
3. Keep the deterministic context-memory evaluation in CI; treat a future recall/stale-authority regression or sustained corpus growth as evidence to reopen vector/hybrid retrieval evaluation.
4. Do not add a vector database or embedding provider without a new measured retrieval gap.
5. Keep shared/default BuildKit cache decisions separate from PCP-owned bounded GC and preserve unrelated Docker/DDEV resources.
6. For future terminal-resource cleanup, use the bounded Runtime/executor cleanup path; never use broad Docker/DDEV prune as a substitute.
