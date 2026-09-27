# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and live Runtime/GitHub evidence remain authoritative over chat history. Completed chronology belongs in Tier-3 history, not here.

Last updated: 2026-09-27 for #322 governance hardening.

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md`.
3. Read this compact current-state snapshot.
4. Retrieve only the T2 topical documents and T3 episodes relevant to the current task.
5. Inspect live GitHub `main`, active issue/PR, local branch/worktree, Runtime/executor health and any current lease/job before mutation.
6. Fetch raw CI/log/transcript evidence only when the task requires diagnostics or audit.

Memory-tier rules and the proposed Context Composer contract are in `context-memory-architecture.md`. Historical platform lessons are indexed in `history/episodes.md`.

## Current platform snapshot

- GitHub `main` after the missing-workspace cleanup merge: `9a477d15c0a51054779a41f40b24230aa230484d`.
- Last locally accepted service identities:
  - Runtime `1.0.56`;
  - ddev-executor `1.0.24`.
- PM-controlled routine merge is implemented and operationally proven. Developer agents never merge.
- Healthy-progress non-blocking remains mandatory: static task/profile/provider-failover counters alone are not Human Owner stop reasons while meaningful progress continues inside the approved resource envelope.
- On effective adaptive WorkOrders, `max_changed_files` is a working target with bounded emergency headroom; actual sensitive/protected changed paths remain independent decision boundaries. Legacy-hard WorkOrders retain strict file-count semantics.
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

1. Keep #146 in calibration/watch mode and collect only naturally occurring routine-task evidence.
2. Keep the deterministic context-memory evaluation in CI; treat a future recall/stale-authority regression or sustained corpus growth as evidence to reopen vector/hybrid retrieval evaluation.
3. Do not add a vector database or embedding provider without a new measured retrieval gap.
4. Keep shared/default BuildKit cache decisions separate from PCP-owned bounded GC and preserve unrelated Docker/DDEV resources.
5. For future terminal-resource cleanup, use the bounded Runtime/executor cleanup path; never use broad Docker/DDEV prune as a substitute.
