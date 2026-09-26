# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and live Runtime/GitHub evidence remain authoritative over chat history. Completed chronology belongs in Tier-3 history, not here.

Last updated: 2026-09-26 during #314.

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md`.
3. Read this compact current-state snapshot.
4. Retrieve only the T2 topical documents and T3 episodes relevant to the current task.
5. Inspect live GitHub `main`, active issue/PR, local branch/worktree, Runtime/executor health and any current lease/job before mutation.
6. Fetch raw CI/log/transcript evidence only when the task requires diagnostics or audit.

Memory-tier rules and the proposed Context Composer contract are in `context-memory-architecture.md`. Historical platform lessons are indexed in `history/episodes.md`.

## Current platform snapshot

- GitHub `main` immediately before the #314 Phase-1 branch: `d2dc61e7d34082bb88925639c3ee8129b8f30056`.
- Last locally accepted service identities:
  - Runtime `1.0.55`;
  - ddev-executor `1.0.23`.
- PM-controlled routine merge is implemented and operationally proven. Developer agents never merge.
- Healthy-progress non-blocking remains mandatory: static task/profile/provider-failover counters alone are not Human Owner stop reasons while meaningful progress continues inside the approved resource envelope.
- Routine provider recovery remains Runtime/Router responsibility while eligible capacity exists.
- Dedicated PCP BuildKit isolation is implemented through `pcp-builder`; the user's globally selected/default builder is not replaced.
- Direct workspace + Dashboard job-owned live preview for Chợ Nhạc is implemented and accepted.
- Project-level **Current site** preview is implemented and accepted independently of an active WorkOrder.
- Current-site idle preview does not create an engineering job or hold the engineering project lease.
- Direct-job terminal cleanup must retire preview and safely return the exact clean job-owned branch to the configured existing local base branch before releasing the project lease.

For executable details, inspect code/tests on current `main`; historical rollout evidence is in `history/episodes.md`.

## Chợ Nhạc project state

Approved ProjectBaseline for new PCP-managed Chợ Nhạc work:

- revision: `mvp-v1-2026-09-22-design`;
- immutable baseline source: `afc0901a6c073f763c440df4d492778c12fec11a`;
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

### #313 — Tiered Context & Memory Architecture for PCP

Status: open umbrella initiative approved by the Human Owner.

Direction:

- T0 pinned governance;
- T1 compact active working state;
- T2 durable semantic/topical knowledge;
- T3 episodic history;
- T4 raw evidence;
- deterministic Context Composer before vector infrastructure;
- authority/freshness/supersession-aware retrieval;
- vector/hybrid RAG only after PCP-specific evaluation demonstrates material benefit.

### #314 — Phase 1: compact active state and define PCP memory tiers

Status: active documentation-only delivery for #313.

This branch/PR should:

- replace the old ~52 KB / 897-line append-heavy `current-state.md` with this compact T1 snapshot;
- add the T3 episodic index;
- add the tier/context contract;
- update the resume workflow;
- change no executable behavior.

Close #314 after exact-head CI and merge. #313 remains open for later deterministic Context Composer/evaluation phases.

### #282 — Release terminal PCP DDEV resources when legacy workspace is missing

Status: open; next concrete source-maintenance issue unless Human Owner reprioritizes.

Current gap:

- normal Runtime cleanup remains workspace-oriented;
- a terminal/audit-released legacy job whose Git workspace is already absent does not yet have a reusable bounded orphan-resource release API;
- the historical `eec59b1365` orphan was manually released with exact ownership gates, but that manual proof is not the implementation.

Planned direction:

1. bounded inspect/release operation that derives exact `cp-<job-prefix>` identity without requiring the Git workspace;
2. Runtime terminal/audit-release authorization;
3. exact ownership/reference/activity checks;
4. dry-run before mutation;
5. preserve blocked/failed/resumable/nonterminal work by default;
6. idempotent regression coverage and disposable local acceptance fixture.

Do not use global Docker/image prune or recreate a missing workspace to perform cleanup.

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
- #309 project-level Current site preview.

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

## Immediate next safe actions

1. Complete #314 through exact-head CI, PM review and merge; then close the Phase-1 child while keeping #313 open.
2. Unless reprioritized, implement #282 as the next concrete source-maintenance issue using the bounded orphan-resource design already recorded on that issue.
3. Keep #146 in calibration/watch mode; collect only naturally occurring routine-task evidence.
4. Under #313 Phase 2, design a deterministic Context Composer that always pins T0/T1 and retrieves bounded T2/T3 context by exact metadata/heading-aware lexical signals before considering embeddings.
5. Build a PCP-specific memory evaluation set before any vector-store decision. Include current-vs-historical, supersession, authority conflict, temporal reasoning, exact identity and abstention cases.
6. Keep shared/default BuildKit cache decisions separate from PCP-owned bounded GC and preserve unrelated Docker/DDEV resources.
