# Current Project State and Handoff

Status: **Tier-1 mutable working-state index**. This is not a chronological incident log, an approved ProjectBaseline amendment, or proof of a live Runtime/local lock. Repository governance and approved ProjectBaseline revisions remain authoritative; read GitHub/Runtime/local evidence again before any mutation.

Last reconciled: **2026-10-10**, G0-01 #594 read-only audit in progress. GitHub main/issue/PR and fresh Guardian Runtime/Executor/Router health verified, with Chợ Nhạc GH-89 job + actual direct worktree observed by PM diagnostic. **The direct-project lease table and current Codex single-writer ownership remain unproven**; do not treat clean PCP local main or zero PCP active jobs as proof of Chợ Nhạc lease release. See `docs/project/history/g0-01-architecture-audit-2026-10-10.md`.

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

- On **2026-10-08**, PCP [PR #581](https://github.com/sonvhse06072/personal-coding-platform/pull/581) was exact-head PM-reviewed at `46cb41082fdbd50332ab1ac0849ba669babec89e`, CI 4/4 green, and merged into GitHub main as `23d2d5432a11d4b39f6dbbeaf89ffc78d453040e`. This source declares **Runtime 1.0.141**, but source/CI success is **not** installation or browser-UX evidence.
- Earlier PCP #562 reviewer fallback and Guardian attestation projection were delivered in PRs #578/#579; [Guardian post-health 6059320848](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6059320848) verified **Runtime 1.0.140** and DDEV Executor **1.0.34** at its historical exact main `9d22dffef9d74e485f6f56c380ab883da616d07b`. #562 is CLOSED; Chợ Nhạc GH-63 Step 7 was then released/merged.
- Guardian first [refused rollout](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061355284) with an active DDEV Executor process; later [fresh idle snapshot](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061444179) confirmed all zero and healthy. A second exact-main [rollout](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061451157) then [FAILED](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061782543): `ddev restart -y` exceeded its 900-second bound. This is **not** a successful Runtime 1.0.141 rollout.
- **Recovery verified on 2026-10-08:** after the Owner safely completed WSL disk work and manually ran `ddev start`, [Guardian read-only post-health 6063966849](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6063966849) proved Runtime **1.0.141**, DDEV Executor **1.0.34**, Router **1.0.31**, n8n/credentials/Antigravity **1.13** healthy, with **zero active engineering/executor/Antigravity work** and local `main` clean at `23d2d5432a11d4b39f6dbbeaf89ffc78d453040e`. This is Owner-assisted recovery, **not** a proven autonomous Guardian outage-recovery feature. At the **earlier recovery observation**, GitHub main `4cff9689cf00d30141d1721eb5d64f7ac30e5ef4` was ahead only by docs PR #582; the later #583 code merge is separately recorded below. Do not force a DDEV restart just to sync T1 documentation.
- [PCP PR #583](https://github.com/sonvhse06072/personal-coding-platform/pull/583) was exact-head PM-reviewed at `a5eefb54bd7bbfedc08a11601b28cdaff9a5d89c`, with **4/4 CI success** [37807089628](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/37807089628), and merged into GitHub `main` at `dabc579f23a8b9d500a6dcf5647c1e2593b08216`. This updates **Executor source** to **1.0.35**; **no Executor 1.0.35 local rollout** was attempted. The earlier Guardian post-health still proves *deployed* Executor 1.0.34; re-check live state for anything newer.

- On **2026-10-09**, GitHub [PR #592](https://github.com/sonvhse06072/personal-coding-platform/pull/592) merged after **4/4 exact-head CI success** and PM diff review, producing `main@26f5cc54912fc621e2daa898be00feb9f6cd2746`. This includes T2 product-direction documents and a bounded standalone Context Composer regression fix. It is **source acceptance only**, not proof of local Runtime/Executor rollout, project lease freshness, or new developer privileges.
- **2026-10-10 live observation:** [Guardian 6093920625](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093920625) confirms Runtime **1.0.141**, Executor **1.0.35**, Router **1.0.31**, n8n/Antigravity **1.13** and credentials healthy; Runtime active engineering=0, Executor jobs=0 and Antigravity runs=0 **at that snapshot**. Local `main` was clean at `d53fbb07524bb3ca13324e2ed7edac1513367072`; GitHub `main@aae9da0f4164b496f4fbb153d8e2fa4083d6fa08` was 17 commits ahead, with only docs/context script/test changes in the diff. This is an observed deployed version, **not natural cold-start acceptance** (#493) or fresh Chợ Nhạc project-lease proof. Earlier [Guardian 6093879505](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093879505) recorded a Runtime timeout; it subsequently recovered without any authorized rollout/restart from this PM audit.

## Active PCP issues and owner attention

GitHub issue search on **2026-10-09** found **22 open issues** after #591 was completed and PR #592 merged. These are **backlog and operational evidence**, not permission to dispatch jobs:

- **#593 — Canonical PCP product-completion program:** 17 implementation issues **#594–#610** across G0–G3. All were open/planned at the reconciliation point. **#594** is the first architecture/critical-path evidence audit, with a T3 report/PR in progress and exact runtime health/old job worktree diagnostics; **#595** is the subsequent controlled direct-Codex benchmark and is not yet dispatched. G1–G3 remain behind staged Go/No-Go, approved authority and real evidence gates.
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

1. **#594 audit:** review the [T3 G0-01 evidence report](history/g0-01-architecture-audit-2026-10-10.md) and fresh [Guardian health 6093920625](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093920625); pin source-vs-deployed distinctions and 10 bottleneck hypotheses. Missing exact project lease/active Codex writer state must not be silently filled in. G0-01 audit is not a production/rollout task.
2. **#595 benchmark:** remains next **after** #594 audit acceptance, using isolated fixtures and identical acceptance/CI/review conditions. Record actual sample and data gaps; do not claim direct-PCP p50/p90 from one GH-89 incident. #596/G1 remains protected by separate architecture/security ChangeProposal and stage gate.
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

Developer agents never merge. Required deterministic verification, applicable independent review, exact-head CI, protected decisions and expected-head privileged merge checks are never waived by a status summary. Live locks, incident history, old PR evidence or T1 prose cannot override authoritative current Runtime/GitHub state.
