# Current Project State and Handoff

Status: **Tier-1 mutable working-state index**. This is not a chronological incident log, an approved ProjectBaseline amendment, or proof of a live Runtime/local lock. Repository governance and approved ProjectBaseline revisions remain authoritative; read GitHub/Runtime/local evidence again before any mutation.

Last reconciled: **2026-10-11**. #595 G0-02 **OPEN / G0 NOT GO**, 0 accepted A/B pairs. **Owner ran safe PCP-local `main` fast-forward PASS: `d53fbb0` → GitHub `107202c0a6b7d99a91596e0039bcf680b2fccee9`**, Git clean, PCP services remain intentionally stopped, 3 PCP image tags present, 7.7 GiB RAM and 839 GiB disk observed. Existing Compose/hooks/Codex source pin unchanged; new code **not yet deployed in running images**. Private fixture `39ef13c2...` clean at `/home/sonvh/pcp-g0-fixtures/pcp-g0-drupal-fixture`, Executor root `/home/sonvh` bind aligns. **Startup blocker:** Runtime may re-enqueue queued jobs, cancel in-flight/Antigravity runs and reconcile leases; Plan Orchestrator may launch work, including historical Chợ Nhạc jobs. Owner read-only Docker inspection verified exact PCP PostgreSQL DB container name/site label, but it is `exited` (exit 255, `OOMKilled=false`, restart `no`): **READ ONLY SQL gate BLOCKED**; durable jobs/leases/plans remain unverified. Do not start PCP/bridge/fixture. Strict Chợ Nhạc no-touch.

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

- **Current GitHub source (2026-10-11):** PCP `main@7d35ed39404a3894d72be148e23dafaace82f3cd` after [PR #632](https://github.com/sonvhse06072/personal-coding-platform/pull/632), documentation-only and 4/4 exact-head CI PASS. **Owner local source was fast-forwarded clean to `107202c0a6b7d99a91596e0039bcf680b2fccee9`**; later GitHub difference is documentation-only and does not require local sync/rebuild. Router/Runtime/Executor/n8n remain last observed `exited`; images not rebuilt and new Executor guard not verified deployed.
- **2026-10-10 Guardian [6093920625](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093920625):** Runtime **1.0.141**, Executor **1.0.35**, Router **1.0.31**, n8n/Antigravity **1.13** and credentials healthy; Runtime/Executor/Antigravity active counts **0 at snapshot**. Local PCP `main` clean `d53fbb07524bb3ca13324e2ed7edac1513367072`, behind GitHub at that observation; do not treat the previous source-diff classification as a fresh post-#614 compare. Earlier [6093879505](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093879505) observed Runtime timeout; later health does not prove its root cause or a permanent zero-job state.
- **Residual acceptance:** Executor source fix [#583](https://github.com/sonvhse06072/personal-coding-platform/pull/583) already merged and Executor 1.0.35 observed, but **natural cold-start proof (#493)** and **autonomous remote outage recovery (#512)** are not established. Earlier Guardian `ddev restart` **900s timeout** and Owner-local recovery are logged in [#512](https://github.com/sonvhse06072/personal-coding-platform/issues/512) and [#524](https://github.com/sonvhse06072/personal-coding-platform/issues/524), not repeated here.
- **Source vs deployed and GH-89 worktree details:** [G0-01 T3 audit](history/g0-01-architecture-audit-2026-10-10.md); no automatic local sync, restart, rollout or historical job/lease mutation.

## Active PCP issues and owner attention

GitHub issue/PR search 2026-10-10: **21 open PCP issues, 0 open PCP PRs** after #624 merged. These are backlog/source-state observations, **not** live job, lease or deployment proof:

- **#593 — PCP completion program:** 17 issues #594–#610, G0-01 #594 DONE via #612. G0-02 #595 has comparer #613/#614/#616, [verified private Drupal fixture](https://github.com/sonvhse06072/pcp-g0-drupal-fixture) and source-only registry #624; **0 accepted matched PCP/direct A/B pairs**. [Fixture task G0D-T01](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/issues/2) is **PLANNED, not dispatched**. G1–G3 remain behind Owner-protected and evidence gates.
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
2. **#595 next safe step:** [T3 startup-risk evidence](history/g0-02-isolated-executor-readiness-2026-10-10.md), [#595 real sync/startup finding](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6099817286). Source and fixture path gates PASS; **do not use `ddev start` yet**: startup may touch persisted queued/in-flight jobs, lease and Antigravity `/cancel-all`; Plan Orchestrator ticks immediately. Owner [exact PCP DB gate](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6100397949): name and site label VERIFIED; DB is `exited`, read-only SQL gate STOP. Next: inspect only this PCP DB container's mount/entrypoint/port/network metadata **read-only** before designing Owner-gated DB-only recovery; a targeted PostgreSQL boot could replay WAL and is not read-only. Until durable jobs/leases/plans can be safely examined, no speculative DB or Runtime startup. PCP pre-start bridge also rewrites shared host Antigravity settings. Protect Chợ Nhạc jobs/lease and global Codex; later plan explicit PCP-only safe-start and image/deployed parity. Fixture `ddev.enabled=false`/delivery OFF; G0 NOT GO/G1 #596 blocked.
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
