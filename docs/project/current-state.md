# Current Project State and Handoff

Status: **Tier-1 mutable working-state index**. This is not a chronological incident log, an approved ProjectBaseline amendment, or proof of a live Runtime/local lock. Repository governance and approved ProjectBaseline revisions remain authoritative; read GitHub/Runtime/local evidence again before any mutation.

Last reconciled: **2026-10-09** for GitHub issue-tree cleanup and Owner-approved product documentation direction. Local Runtime and direct-workspace lease **have not been freshly verified in this PR**; source/CI changes must not be interpreted as deployed behavior. Recheck full live state before any operation.

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

- On **2026-10-09**, GitHub `main` before the documentation branch was `d53fbb07524bb3ca13324e2ed7edac1513367072` (PR #585 merged). This is **GitHub source evidence only**; no fresh deployed/healthy/quiescent Runtime or Chợ Nhạc workspace state is claimed.

## Active PCP issues and owner attention

GitHub issue search on **2026-10-09** found **23 open issues** after Owner-requested backlog consolidation. These are **backlog and operational evidence**, not permission to dispatch jobs:

- **#593 — Canonical PCP product-completion program:** 17 implementation issues **#594–#610** across G0–G3. All were open/planned at the reconciliation point. **#594** is the first read-only architecture/critical-path audit; **#595** is direct-Codex benchmark. G1–G3 remain behind staged Go/No-Go, approved authority and real evidence gates.
- **#493 — DDEV Executor cold-start:** source fix PR #583 merged; actual Executor **1.0.35** rollout/natural cold-start acceptance still must be verified. Not a new source implementation ticket.
- **#512 — Remote PM/Guardian:** retained for natural remote-intake and out-of-band recovery acceptance, not a second implementation program.
- **#524 — Guardian control/audit:** intentionally open operations channel, **not** developer backlog.
- **#588 — Project Discovery:** **FUTURE / DEFERRED**; excluded from Product RC1, no autonomous no-doc onboarding now.
- **#591 — T2 documentation reconciliation:** protected docs PR [#592](https://github.com/sonvhse06072/personal-coding-platform/pull/592); its exact-head tests, review and merge must be checked live. A source branch does not automatically update approved project authority.

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
- Chợ Nhạc application issues are not automatically PCP roadmap scope. Reconcile fresh managed-project source/jobs and approved authority before any new WorkOrder.

## Immediate next safe actions

1. #493 source/CI/review completed in merged PR #583. **Do not repeat Guardian rollout without addressing the host `ddev restart` pre-start 900s incident**; first obtain a fresh safe startup plan and full quiescence, then separately deploy Executor 1.0.35. GitHub merge does not imply local deployment.
2. Fresh post-merge Guardian [snapshot 6064238395](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6064238395) confirmed Runtime **1.0.141**, Executor **1.0.34**, Router **1.0.31**, n8n/Antigravity/credentials healthy, and 0 active Runtime/Executor/Antigravity work. **At that 2026-10-08 snapshot**, local `main` was clean at `23d2d5432a11d4b39f6dbbeaf89ffc78d453040e` and GitHub `main` was `dabc579f23a8b9d500a6dcf5647c1e2593b08216`. The later GitHub #585 source merge is recorded above; **no newer local deployment/source state is claimed**. Recheck all quiescence/clean gates before any future rollout, never reuse this historical snapshot as a standing permission.
3. Finish #591 / PR #592 via exact-head tests and reviewed doc authority; start #594 read-only audit against live GitHub. Use #593 as the single engineering plan and only dispatch later phases after Go/No-Go. #512 remains for natural remote acceptance; #524 for Guardian audit. #588 remains deferred. Historical #586 GH-89 job/lease needs read-only reconciliation before any new write.
4. Preserve approved ProjectBaseline/managed-project source identities, existing job state, tracked cancellation, finite retries and Human Owner-protected decisions. No Docker prune/reset or replacement job to bypass a blocker.

## Historical and detailed evidence pointers

- Memory model and accepted original benchmark: #313, #314, #317; docs/project/context-memory-architecture.md.
- Baseline/document governance hardening: #322; approved source in AGENTS.md / docs/project/constitution.md.
- Incident-learning and PM triage: #406, docs/project/operating-model.md, docs/project/history/episodes.md.
- Remote PM/Guardian controls: #512 and #524; Runtime state and audit events are authoritative for current actions.
- Chợ Nhạc old/retired ExecutionPlan and rollout details: GH-63, PCP issues #424, #466, #493 and Git history of this file. Completed chronology belongs in GitHub/Git/Runtime/T3, not this replace-in-place snapshot.
- Review required code, tests, and exact branch diff for implementation; high-volume CI logs, transcripts, and diagnostics belong at T4 and are fetched only when specifically needed.

## Standing safety boundary

Developer agents never merge. Required deterministic verification, applicable independent review, exact-head CI, protected decisions and expected-head privileged merge checks are never waived by a status summary. Live locks, incident history, old PR evidence or T1 prose cannot override authoritative current Runtime/GitHub state.
