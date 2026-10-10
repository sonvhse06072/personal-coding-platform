# Current Project State and Handoff

Status: **Tier-1 mutable working-state index**. This is not a chronological incident log, an approved ProjectBaseline amendment, or proof of a live Runtime/local lock. Repository governance and approved ProjectBaseline revisions remain authoritative; read GitHub/Runtime/local evidence again before any mutation.

Last reconciled: **2026-10-10**, G0-01 #594 audited and CLOSED after [PR #612](https://github.com/sonvhse06072/personal-coding-platform/pull/612) merged with 4/4 exact-head CI. G0-02 #595 is **IN PROGRESS / not G0 Go**. [DEC-G0-FIXTURE-01](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6094931078) received **explicit scoped Owner approval on 2026-10-10** for new data-free Drupal→Next fixtures, not G1 trust changes. [G0D-01 Drupal WorkOrder](history/g0-02-drupal-fixture-workorder-2026-10-10.md) prepared; **no fixture created, no actual A/B trials yet**. GitHub main/issue/PR and fresh Guardian Runtime/Executor/Router health verified, with Chợ Nhạc GH-89 job + actual direct worktree observed by PM diagnostic. **The direct-project lease table and current Codex single-writer ownership remain unproven**; do not treat clean PCP local main or zero PCP active jobs as proof of Chợ Nhạc lease release. See `docs/project/history/g0-01-architecture-audit-2026-10-10.md`.

## Resume order

1. Read AGENTS.md and docs/project/README.md for repository authority and required boundaries.
2. Read this compact T1 snapshot and the relevant T2 source, not all historical project documentation.
3. Retrieve the relevant T3 episode from docs/project/history/episodes.md only when its lesson applies.
4. Revalidate exact live GitHub issue/PR/head/CI and Runtime job/plan/lease/local Git state before review, repair, merge, continuation or rollout.
5. Read exact code/diff/tests for the active WorkOrder; fetch T4 logs only to diagnose a specific problem.

Memory/retrieval contract: docs/project/context-memory-architecture.md. The existing Context Composer is scripts/context_memory.py (standalone deterministic tool); do not assume Runtime prompts automatically use it.

## Current product and operating frame

- PCP is a **personal engineering operating system**, not a SaaS product. Owner-approved direction 2026-10-09: incremental refactor focused on accepted autonomous delivery, resource/model optimization, bounded self-healing, doc/context governance, trusted developer parity, and later provider/skill adaptation. Product direction: docs/project/business-strategy.md; architecture target: docs/project/architecture.md; staged plan: docs/project/roadmap.md. **Approved targets are not deployed features or new permissions**.
- Human Owner retains protected scope, architecture, security, destructive data, production, governance and material resource decisions. PM may perform routine in-scope work/merges only after their existing gates pass.
- Git/project documents hold durable approved knowledge. ProjectBaseline pins approved authority to an exact source commit; newer GitHub main is executable-source evidence, **not** implicit baseline approval.
- Router selects staffing and bounded budgets; Runtime/PostgreSQL owns durable job/checkpoint/orchestration state; GitHub provides auditable development/remote PM control; Guardian supplies strictly allow-listed out-of-band actions.
- Do not turn Chợ Nhạc application issues into PCP roadmap items unless a repeatable platform defect or material reusable capability gap is demonstrated.

## PCP GitHub source and rollout evidence

- **Current GitHub source (2026-10-10):** `main@3076d5fd8f924003f229747957857253d3872fd0` after [PR #614](https://github.com/sonvhse06072/personal-coding-platform/pull/614), 4/4 exact-head CI PASS. Earlier protected product-doc reconciliation [PR #592](https://github.com/sonvhse06072/personal-coding-platform/pull/592) was also merged after 4/4 CI. GitHub merge does **not** implicitly amend a pinned ProjectBaseline or prove updated local deployment.
- **2026-10-10 Guardian [6093920625](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093920625):** Runtime **1.0.141**, Executor **1.0.35**, Router **1.0.31**, n8n/Antigravity **1.13** and credentials healthy; Runtime/Executor/Antigravity active counts **0 at snapshot**. Local PCP `main` clean `d53fbb07524bb3ca13324e2ed7edac1513367072`, behind GitHub at that observation; do not treat the previous source-diff classification as a fresh post-#614 compare. Earlier [6093879505](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093879505) observed Runtime timeout; later health does not prove its root cause or a permanent zero-job state.
- **Residual acceptance:** Executor source fix [#583](https://github.com/sonvhse06072/personal-coding-platform/pull/583) already merged and Executor 1.0.35 observed, but **natural cold-start proof (#493)** and **autonomous remote outage recovery (#512)** are not established. Earlier Guardian `ddev restart` **900s timeout** and Owner-local recovery are logged in [#512](https://github.com/sonvhse06072/personal-coding-platform/issues/512) and [#524](https://github.com/sonvhse06072/personal-coding-platform/issues/524), not repeated here.
- **Source vs deployed and GH-89 worktree details:** [G0-01 T3 audit](history/g0-01-architecture-audit-2026-10-10.md); no automatic local sync, restart, rollout or historical job/lease mutation.

## Active PCP issues and owner attention

GitHub issue/PR search on **2026-10-10** found **21 open issues, 0 open PCP PRs** after #594 was closed and PR #614 merged. These are **backlog and operational evidence**, not permission to dispatch jobs:

- **#593 — Canonical PCP product-completion program:** 17 implementation issues **#594–#610** across G0–G3. **#594 G0-01** is CLOSED completed with [T3 source+live audit](history/g0-01-architecture-audit-2026-10-10.md) / merged PR #612; **#595 G0-02**: benchmark analyzer/guards merged via PRs #613/#614/#616, [T3 protocol](history/g0-02-benchmark-protocol-2026-10-10.md) and [scoped F-DRUPAL WorkOrder](history/g0-02-drupal-fixture-workorder-2026-10-10.md). **Fixture creation approved but not executed**. Greeter #7 is completed generic PHP, not Drupal; no measured A/B/ROI decision. G1–G3 remain behind staged Go/No-Go, approved authority and real evidence gates.
- **#493 — DDEV Executor cold-start:** source fix PR #583 merged; Executor **1.0.35 was observed live** in Guardian 6093920625. The rollout/changed-image provenance and natural cold-start acceptance remain incomplete. Do not redo source fix.
- **#512 — Remote PM/Guardian:** retained for natural remote-intake and out-of-band recovery acceptance, not a second implementation program.
- **#524 — Guardian control/audit:** intentionally open operations channel, **not** developer backlog.
- **#588 — Project Discovery:** **FUTURE / DEFERRED**; excluded from Product RC1, no autonomous no-doc onboarding now.
- **#591 — COMPLETED source-of-truth reconciliation:** [PR #592](https://github.com/sonvhse06072/personal-coding-platform/pull/592) merged with **4/4 CI PASS**, as established above; **#591 is closed and is not one of the 22 open issues**. Runtime deployment and approved ProjectBaseline promotion remain separate events.

**#586, #587, #589, #590 were closed as duplicate/superseded planning** and their implementation acceptance moved to #594/#601, #603/#604, #606/#607, and #594–#599 respectively. This is **not** proof that the associated features or the old Chợ Nhạc #89 PCP job are complete, cancelled or released. Do not issue a replacement job, bypass a lease or mutate worktree because its historical issue is closed. **#557, #562, #563, #571 are also closed** and do not represent open development gates.

Chợ Nhạc GH-63 founder acceptance is a managed-project decision, not a PCP source blocker. Live GitHub/Runtime and project branch/lease state are authoritative for time-sensitive work, not this snapshot.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

- Event: `pr_merged`.
- Project/job: `chonhac` / `057f6acff17b501eae3a673cbb6bbe36`.
- Runtime state: `completed`; outcome: `accepted`.
- WorkOrder: `EE-0-04-event-engagement-analytics`; branch: `ai/057f6acff17b`.
- Human attention: interventions `1`, avoidable `0`, owner wait `502.9` seconds.
- Execution evidence: first-pass `False`, repairs `5`, provider failures `0`, quota failures `0`.
- Incident learning: candidate `incident:5ca80fdd5a5adbc9a082`; signals repair_churn, verification_retry_anomaly.
- This section is mutable execution state only. Durable architecture/policy changes still require their normal reviewed Git path.
<!-- PCP:CONTINUITY:END -->

## Chợ Nhạc managed-project checkpoint

- Pinned approved pilot baseline referenced by this continuity snapshot: **pilot-v1-2026-10-04-dec033-r3**, source **aa8e68dd9aea6740de446151eb97615931de9b40**. This is **not** a statement that newer GitHub main amended the approved baseline; each existing WorkOrder retains its own bound revision.
- GH-63 Step 7 `EE-0-04-event-engagement-analytics` completed on preserved job `057f6acff17b501eae3a673cbb6bbe36`, plan `pm-b0748be27f8446a0813c2d1fe7d697fd`. Its PR [#85](https://github.com/sonvhse06072/chonhac/pull/85) reviewed head `90c84d38692f781e1df91e85d253897d68458638`, merged as `d069ac2280b5592327debb166592f99efe685bac`; parent checkpoint **184** and plan `completed` confirmed in [GH-63 audit](https://github.com/sonvhse06072/chonhac/issues/63#issuecomment-6059394452).
- Chợ Nhạc **GH-63 remains OPEN** for founder/live product acceptance, not for the already merged Step 7 source. PCP #562 reviewer-boundary recovery was completed and closed. Do not restart/recover the accepted job simply to produce another acceptance record.
- **2026-10-10 GH-89 fresh PM diagnostic:** [6093934986](https://github.com/sonvhse06072/chonhac/issues/89#issuecomment-6093934986) shows preserved PCP job `08ae925693b85379b11a54e4dc26121e` **blocked**, plan checkpoint 187, zero pending remote actions. Crucially, *current shared direct worktree* is on **`codex/132-stage-b-editorial-repair`**, dirty, HEAD **`b133355926098682a2ef88a72adba46cb3d8c0d0`**; the persisted old PCP job retains branch `ai/08ae925693b8`. No code/lease mutation is authorized from the mismatch; do not touch the dirty direct Codex workspace.
- Chợ Nhạc application issues are not automatically PCP roadmap scope. Reconcile fresh managed-project source/jobs and approved authority before any new WorkOrder.

## Immediate next safe actions

1. **#594 complete:** evidence [PR #612](https://github.com/sonvhse06072/personal-coding-platform/pull/612) merged; no further G0-01 code. Shared Chợ Nhạc dirty direct worktree and historical lease unresolved remain **no-touch** until separately authorized.
2. **#595 next execution:** Owner approved [DEC-G0-FIXTURE-01](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6094931078), **only new empty-data fixture prep/limited registration**. Execute [G0D-01 Drupal WorkOrder](history/g0-02-drupal-fixture-workorder-2026-10-10.md) **from this ChatGPT PM session**, not through the Codex session dedicated to Chợ Nhạc. Offline bootstrap bundle prepared; **11/11 static tests and PHP syntax PASS**, actual Composer/DDEV/Drupal Kernel/CI/local repo NOT YET RUN. **No existing project/DB touch**. Source SHA/Unit/Kernel/CI proof must exist before separately reviewed protected `config/projects.yml` / `config/project-baselines.yml` PR; don't claim that approval means local deployment or G0 Go. Next/repair follow Drupal readiness. `config/pm-bridge.yml` enables only Chợ Nhạc; no invented fixture remote dispatch or #596 security authority.
3. **#493/#512 residual:** Executor **1.0.35 observed**, natural cold-start and remote recovery still unproven. No reason to restart just to update docs or repeat fixed source changes. The prior host `ddev restart` 900-second incident still requires bounded root-cause/rollback planning.
4. **Chợ Nhạc writer protection:** GH-89 blocked durable PCP job exists while current direct worktree is **dirty Codex branch**. Do not checkout, stash, reset, resume, retire, cancel or overwrite that shared workspace from PCP audit. No Docker prune, replacement job or protected authority override. Only a fresh explicitly authorized single-writer/lease handoff can change this.

## Historical and detailed evidence pointers

- Memory model and accepted original benchmark: #313, #314, #317; docs/project/context-memory-architecture.md.
- Baseline/document governance hardening: #322; approved source in AGENTS.md / docs/project/constitution.md.
- Incident-learning and PM triage: #406, docs/project/operating-model.md, docs/project/history/episodes.md.
- Remote PM/Guardian controls: #512 and #524; Runtime state and audit events are authoritative for current actions.
- G0-01 read-only/source-and-live audit: `docs/project/history/g0-01-architecture-audit-2026-10-10.md` and PCP #594; measured A/B evidence belongs to #595.
- Chợ Nhạc old/retired ExecutionPlan and rollout details: GH-63, PCP issues #424, #466, #493 and Git history of this file. Completed chronology belongs in GitHub/Git/Runtime/T3, not this replace-in-place snapshot.
- Review required code, tests, and exact branch diff for implementation; high-volume CI logs, transcripts, and diagnostics belong at T4 and are fetched only when specifically needed.

## Standing safety boundary

**Owner directive (2026-10-10), applies to this PM execution:** Codex is exclusively handling Chợ Nhạc. **PCP must not initiate any operations on Chợ Nhạc:** no PM Bridge/Guardian control for `chonhac`, no PCP dispatch, resume/cancel/recovery, Git branch/PR/commit write, database/DDEV action, worktree checkout, preview, test run, Docker cleanup, credential use or historical job/lease mutation targeting Chợ Nhạc. Focus is exclusively on **PCP repository + brand-new isolated G0 fixture**. This is a **PM-level operational prohibition**; it does **not** claim that a technical Runtime denylist has been installed or that historical lease state was reconciled.

Developer agents never merge. Required deterministic verification, applicable independent review, exact-head CI, protected decisions and expected-head privileged merge checks are never waived by a status summary. Live locks, incident history, old PR evidence or T1 prose cannot override authoritative current Runtime/GitHub state.
