# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and live Runtime/GitHub evidence remain authoritative over chat history. Completed chronology belongs in Tier-3 history, not here.

Last updated: 2026-09-30 for #370 supervised WorkOrder continuation source review.

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md`.
3. Read this compact current-state snapshot.
4. Retrieve only the T2 topical documents and T3 episodes relevant to the current task.
5. Inspect live GitHub `main`, active issue/PR, local branch/worktree, Runtime/executor health and any current lease/job before mutation.
6. Fetch raw CI/log/transcript evidence only when the task requires diagnostics or audit.

Memory-tier rules and the proposed Context Composer contract are in `context-memory-architecture.md`. Historical platform lessons are indexed in `history/episodes.md`.

## Current platform snapshot

- Exact #370 implementation base: `c573764a3a17330df98af1db2911567650104196`
  (#365-#369 and the #377 atomicity repair are prerequisites on this base).
- The accepted live platform before this uncommitted source work runs Runtime
  `1.0.76` and executor `1.0.28`. The #367/#368 bounded live dogfood was
  accepted; the #369 live acceptance exposed and led to #377.
- Current working-tree source identities on `ai/370-supervised-workorder-continuation`
  (unstaged/uncommitted; not rolled out):
  - Runtime `1.0.77`;
  - Router `1.0.30`;
  - routing policy `19`;
  - ddev-executor `1.0.28`.
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

### #362 / #370 — Supervised WorkOrder continuation

Status: #370 source implementation is validated locally on
`ai/370-supervised-workorder-continuation` and pending independent PM exact-patch
review. This session performs no live dogfood. Live
fixtures #11 and #12, running PCP services and Chợ Nhạc remain untouched.

ExecutionPlans now accept caller-owned `autonomous` or `supervised` execution
mode; missing legacy mode remains autonomous and the planning model cannot
select it. Canonical intake rejects a supervised request if deterministic intake
classification selects direct execution. Autonomous direct and plan execution
retain their existing behavior.

The existing `cp_plan_orchestrations` row owns a supervised between-WorkOrder
gate. After an exact durable `completed` or `merged` checkpoint makes pending
dependencies ready, the plan persists `supervised_hold` with a monotonic
generation, exact checkpoint ID/key/WorkOrder, sorted complete ready set and a
deterministic `plan:continue:` SHA-256 key over that canonical identity. It does
not hold before WO-1, during a child/operator/merge/block/repair gate, at a plan
decision boundary or after plan completion. No successor Runtime job exists
while held.

Authenticated exact continuation locks and revalidates the durable row,
atomically changes the same generation from `held` to `released`, and invokes
the normal orchestrator tick. It never creates a child directly. Exact released
retries remain read-only idempotent success while that generation is current
and return without invoking an orchestration tick, including after the released
child runs, waits for an operator or merge, blocks, or completes. Mismatches and
stale generations conflict. Released
state survives restart and a busy direct-project lease, allowing the existing
launch path to retry without a second continuation. A later terminal checkpoint
creates a newer generation. Runtime progress, Dashboard and the single managed
parent GitHub progress comment share this durable identity.

Supervision releases only the plan checkpoint gate. Existing Human Owner
decision boundaries, operator actions, PM exact-head merge, production/security/
architecture/destructive-data authority, dependency readiness, one-at-a-time
policy, lease, routing, budget, verification and delivery gates remain
authoritative. Runtime source is `1.0.77`; Router, routing policy and executor
versions are unchanged. Issue-specific PostgreSQL/API tests: `15` passed; the
required focused planning/intake/orchestrator/checkpoint/progress/Dashboard/
control matrix: `407` passed; full Runtime with PostgreSQL: `948` passed;
repository structure: `103` passed; Python compilation and `git diff --check`
passed. The only warning is the existing Starlette/AnyIO deprecation. Local
tests are not remote CI; independent PM review, exact-head CI, merge, controlled
rollout and live dogfood remain later gates. The handoff artifact is
`/tmp/issue-370-pm-review.patch`.

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
- #365-#368 durable WorkOrder checkpoints, lifecycle emission, canonical intake
  and one-comment parent progress publication (merged via PRs #371-#374; rollout
  and bounded live dogfood accepted).

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

1. Independently PM-review `/tmp/issue-370-pm-review.patch`. Keep the tree unstaged/uncommitted/unpushed. Preserve live fixtures #11/#12, running PCP services and Chợ Nhạc. Exact-head CI, merge, rollout and live dogfood remain later gates.
2. Keep #146 in calibration/watch mode and collect only naturally occurring routine-task evidence.
3. Keep the deterministic context-memory evaluation in CI; treat a future recall/stale-authority regression or sustained corpus growth as evidence to reopen vector/hybrid retrieval evaluation.
4. Do not add a vector database or embedding provider without a new measured retrieval gap.
5. Keep shared/default BuildKit cache decisions separate from PCP-owned bounded GC and preserve unrelated Docker/DDEV resources.
6. For future terminal-resource cleanup, use the bounded Runtime/executor cleanup path; never use broad Docker/DDEV prune as a substitute.
