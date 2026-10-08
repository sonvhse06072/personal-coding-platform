# Current Project State and Handoff

Status: **Tier-1 mutable working-state index**. This is not a chronological incident log, an approved ProjectBaseline amendment, or proof of a live Runtime/local lock. Repository governance and approved ProjectBaseline revisions remain authoritative; read GitHub/Runtime/local evidence again before any mutation.

Last reconciled: **2026-10-08** using GitHub main and issue/PR evidence. The last locally verified Guardian state cited below is historical; this edit does **not** assert a fresh local health/quiescence snapshot.

## Resume order

1. Read AGENTS.md and docs/project/README.md for repository authority and required boundaries.
2. Read this compact T1 snapshot and the relevant T2 source, not all historical project documentation.
3. Retrieve the relevant T3 episode from docs/project/history/episodes.md only when its lesson applies.
4. Revalidate exact live GitHub issue/PR/head/CI and Runtime job/plan/lease/local Git state before review, repair, merge, continuation or rollout.
5. Read exact code/diff/tests for the active WorkOrder; fetch T4 logs only to diagnose a specific problem.

Memory/retrieval contract: docs/project/context-memory-architecture.md. The existing Context Composer is scripts/context_memory.py (standalone deterministic tool); do not assume Runtime prompts automatically use it.

## Current product and operating frame

- PCP is a **personal engineering operating system**, not a SaaS product. Current stage is **consolidation and reliability**. See docs/project/business-strategy.md and docs/project/roadmap.md.
- Human Owner retains protected scope, architecture, security, destructive data, production, governance and material resource decisions. PM may perform routine in-scope work/merges only after their existing gates pass.
- Git/project documents hold durable approved knowledge. ProjectBaseline pins approved authority to an exact source commit; newer GitHub main is executable-source evidence, **not** implicit baseline approval.
- Router selects staffing and bounded budgets; Runtime/PostgreSQL owns durable job/checkpoint/orchestration state; GitHub provides auditable development/remote PM control; Guardian supplies strictly allow-listed out-of-band actions.
- Do not turn Chợ Nhạc application issues into PCP roadmap items unless a repeatable platform defect or material reusable capability gap is demonstrated.

## PCP GitHub source and rollout evidence

- On **2026-10-08**, PCP [PR #581](https://github.com/sonvhse06072/personal-coding-platform/pull/581) was exact-head PM-reviewed at `46cb41082fdbd50332ab1ac0849ba669babec89e`, CI 4/4 green, and merged into GitHub main as `23d2d5432a11d4b39f6dbbeaf89ffc78d453040e`. This source declares **Runtime 1.0.141**, but source/CI success is **not** installation or browser-UX evidence.
- Earlier PCP #562 reviewer fallback and Guardian attestation projection were delivered in PRs #578/#579; [Guardian post-health 6059320848](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6059320848) verified **Runtime 1.0.140** and DDEV Executor **1.0.34** at its historical exact main `9d22dffef9d74e485f6f56c380ab883da616d07b`. #562 is CLOSED; Chợ Nhạc GH-63 Step 7 was then released/merged.
- Guardian first [refused rollout](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061355284) with an active DDEV Executor process; later [fresh idle snapshot](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061444179) confirmed all zero and healthy. A second exact-main [rollout](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061451157) then [FAILED](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061782543): `ddev restart -y` exceeded its 900-second bound. This is **not** a successful Runtime 1.0.141 rollout.
- Read-only Guardian [post-timeout snapshot](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061879197) confirmed local Git clean `main` exactly at `23d2d5432a11d4b39f6dbbeaf89ffc78d453040e`, but Runtime, Router, Executor, n8n and credential probes **unreachable/timed out**, with Antigravity host bridge `down`. Active Runtime/Executor work **cannot currently be proven**, and live Runtime version is unknown. Guardian's out-of-band diagnosis succeeded; safe service recovery has **not** been demonstrated. Do not retry rollout blind or mutate durable orchestration state.
- GitHub open PR listing was empty at this reconciliation before this continuity PR; check again live, do not treat that as a persistent invariant.

## Active PCP issues and owner attention

Four PCP issues remain open at reconciliation:
- **#557 — Estimated workflow progress:** PR #581 fixes Planning→45% inference and CI is green, but the Runtime 1.0.141 restart/rollout failed and services are unreachable. Keep OPEN until a safe authenticated post-health and subsequent natural Planning-job UI check; do not run synthetic jobs.
- **#493 — DDEV cold-bootstrap reliability:** generic cold/quiesced/isolated fallback still contains `timeout=min(timeout, 600)` for `ddev start -y`; healthy direct-workspace reuse from PR #494 is already working. Bounded infrastructure policy/evidence/tests are outstanding; no blind 600→1800 increase.
- **#512 — remote PM control/Guardian parent:** live same-job repair, PM-chat review/merge and prior Guardian rollout are proven. The new natural Runtime/n8n outage **proves out-of-band Guardian diagnosis** through #524 snapshot, but **safe recovery** of this failure is not yet proven; new-ticket GitHub `direct_intake` remains unproven. Keep OPEN, no failure injection or unsafe restart.
- **#524 — persistent Guardian control/audit:** intentionally OPEN as operations channel, not an engineering work ticket.

PCP **#562** and documentation hardening **#563** are CLOSED; do not carry their completed blockers as live Human Owner attention. The product/founder UX acceptance for Chợ Nhạc GH-63 is a separate outstanding decision, not proof of a PCP source blocker. `docs/project/current-state.md` is T1 execution continuity only and cannot amend higher-authority policy.

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

1. Resolve the **real PCP control-plane outage** shown in [Guardian post-timeout audit 6061879197](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061879197). Local main is already exact, but service health and active jobs are unprovable. The reviewed Guardian allowlist has no general DDEV restart/recovery action and rollout requires live quiescence. No repeat rollout, ad-hoc remote shell or DB/process reset; request bounded Owner-local diagnosis/recovery if no existing reviewed path is safe, with immutable audit and fresh post-health.
2. #557 remains OPEN: preserve PR #581 merge/green CI evidence, then accept Runtime 1.0.141 only after a safe post-recovery status proving exact local main and healthy/idle services, followed by natural Planning-job UX validation.
3. Update #512 to count the natural Runtime/n8n-unavailable Guardian **diagnosis** as proven, but keep it OPEN for an authorized recovery from this incident and for new-ticket GitHub `direct_intake`; #524 remains intentionally OPEN.
4. After the first safe PCP rollout, plan the separate bounded #493 cold-DDEV fix with explicit startup timeout policy and relevant regressions, retaining direct reuse, tracked process-group termination and finite failure semantics. Do not disrupt legitimate active executor work.

## Historical and detailed evidence pointers

- Memory model and accepted original benchmark: #313, #314, #317; docs/project/context-memory-architecture.md.
- Baseline/document governance hardening: #322; approved source in AGENTS.md / docs/project/constitution.md.
- Incident-learning and PM triage: #406, docs/project/operating-model.md, docs/project/history/episodes.md.
- Remote PM/Guardian controls: #512 and #524; Runtime state and audit events are authoritative for current actions.
- Chợ Nhạc old/retired ExecutionPlan and rollout details: GH-63, PCP issues #424, #466, #493 and Git history of this file. Completed chronology belongs in GitHub/Git/Runtime/T3, not this replace-in-place snapshot.
- Review required code, tests, and exact branch diff for implementation; high-volume CI logs, transcripts, and diagnostics belong at T4 and are fetched only when specifically needed.

## Standing safety boundary

Developer agents never merge. Required deterministic verification, applicable independent review, exact-head CI, protected decisions and expected-head privileged merge checks are never waived by a status summary. Live locks, incident history, old PR evidence or T1 prose cannot override authoritative current Runtime/GitHub state.
