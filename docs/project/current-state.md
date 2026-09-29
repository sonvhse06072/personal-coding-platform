# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and live Runtime/GitHub evidence remain authoritative over chat history. Completed chronology belongs in Tier-3 history, not here.

Last updated: 2026-09-30 for #369 blocked-plan evidence-pack PM repair.

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md`.
3. Read this compact current-state snapshot.
4. Retrieve only the T2 topical documents and T3 episodes relevant to the current task.
5. Inspect live GitHub `main`, active issue/PR, local branch/worktree, Runtime/executor health and any current lease/job before mutation.
6. Fetch raw CI/log/transcript evidence only when the task requires diagnostics or audit.

Memory-tier rules and the proposed Context Composer contract are in `context-memory-architecture.md`. Historical platform lessons are indexed in `history/episodes.md`.

## Current platform snapshot

- Checked-out launch baseline: `df1dae3ce7c4a6ed78430358c13b5dd1cb4bddf9`
  (#368 merged via PR #374; #367 via PR #373; #366 via PR #372; #365 via PR #371).
- Runtime `1.0.74` / executor `1.0.28` rollout and the #367/#368 bounded live
  dogfood are accepted. Parent #362 and child #369 confirm the WO-362-5 gate open;
  #370 remains held. No service restart is part of #369 implementation.
- Current working-tree source identities on `ai/369-blocked-plan-evidence-pack`
  (unstaged/uncommitted; not rolled out):
  - Runtime `1.0.75`;
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

### #362 / #369 — Compact blocked-plan evidence pack

Status: WO-362-5 PM-001/PM-002 repairs implemented locally on
`ai/369-blocked-plan-evidence-pack`, pending second independent PM review. Exact base is
`df1dae3ce7c4a6ed78430358c13b5dd1cb4bddf9`. Only #369 is in this patch;
#370 supervised continuation remains unimplemented and held.

The authenticated plan-progress projection now adds `blocked_evidence` derived
from the existing active WorkOrder rows and append-only checkpoints in the same
repeatable-read snapshot. It selects terminal checkpoints for completed prior
WorkOrders, the newest block checkpoint matching the exact current WorkOrder/job,
the bounded checkpoint history for that same exact job, and the preceding
completed/merged terminal checkpoint. A superseded `accepted` checkpoint is not
last known-good. The bounded pack exposes exact
checkpoint/job/branch identity, the latest useful allowlisted verification and
reviewer/PM outcomes, untouched pending WorkOrders and one advisory action from
`repair`/`reroute`/`human_decision`/`replan`/`retry_delivery`. The current block
reason outranks historical PM evidence; hard budget stops advise Human Owner
review and CI infrastructure failure advises preserved delivery retry.
Unrecognized free-form reasons are
hash-identified instead of echoed. Raw logs, prompts, result blobs and arbitrary
checkpoint JSON remain excluded.

The Dashboard snapshot exposes the same read model. The existing parent-ticket
renderer includes the compact blocked diagnosis while retaining the one-comment,
transition-driven generation/dedupe, 12 KiB body limit and independent publisher.
These reads contain no resume/reroute/state/checkpoint/GitHub mutation path.
Completed checkpoint history remains append-only and pending dependencies remain
unlaunched. Runtime is versioned `1.0.75`; no executor boundary or version changes.

Validation uses existing service images with the current checkout/config mounted
read-only and separate disposable PostgreSQL containers with no external network.
No live plan/job/provider/project workspace was used. Focused blocked/checkpoint/
Dashboard/handoff tests: `94` passed. #365-#368 orchestration/intake/handoff
regressions: `245` passed. PostgreSQL checkpoint/launch/intake/handoff tests:
`66` passed without skips. Existing executor managed-comment tests: `43` passed.
Full Runtime including PostgreSQL: `922` passed without skips. Repository
structure: `103` passed; Python compilation and `git diff --check` pass. Suites
report the existing Starlette/AnyIO dependency deprecation warning. The
PostgreSQL handoff regression confirms the same managed comment ID survives a
blocked progress generation.

Handoff artifact: `/tmp/issue-369-pm-review.patch`, containing all tracked changes
against HEAD. Keep unstaged/uncommitted/unpushed. No PCP restart/rebuild, live
fixture, GitHub mutation or Chợ Nhạc mutation occurred. Local tests are not remote
CI; independent PM review, commit/push/PR and exact-head CI remain future gates.

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

1. PM-review the repaired #369 patch and `/tmp/issue-369-pm-review.patch`. Keep it unstaged/uncommitted/unpushed; exact-head CI remains a later mandatory merge gate. Leave running PCP services and Chợ Nhạc untouched. Do not begin #370.
2. Keep #146 in calibration/watch mode and collect only naturally occurring routine-task evidence.
3. Keep the deterministic context-memory evaluation in CI; treat a future recall/stale-authority regression or sustained corpus growth as evidence to reopen vector/hybrid retrieval evaluation.
4. Do not add a vector database or embedding provider without a new measured retrieval gap.
5. Keep shared/default BuildKit cache decisions separate from PCP-owned bounded GC and preserve unrelated Docker/DDEV resources.
6. For future terminal-resource cleanup, use the bounded Runtime/executor cleanup path; never use broad Docker/DDEV prune as a substitute.
