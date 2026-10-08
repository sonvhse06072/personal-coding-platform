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
- Guardian deliberately [refused rollout 6061343971](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061355284) because DDEV Executor had one tracked active process, despite zero active Runtime engineering jobs. Later read-only [snapshot 6061444179](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061444179) reported all idle/healthy with local main clean at `9d22dffef9d74e485f6f56c380ab883da616d07b`; new exact-main [rollout control 6061451157](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061451157) was sent, **its result must be read before asserting deployment**. Never bypass a fresh Guardian quiescence gate.
- GitHub open PR listing was empty at this reconciliation before this continuity PR; check again live, do not treat that as a persistent invariant.

## Active PCP issues and owner attention

Four PCP issues remain open at reconciliation:
- **#557 — Estimated workflow progress:** PR #581 fixes the erroneous Planning→45% inference from `model_calls`/`iteration`. Keep open until Guardian post-health of 1.0.141 and natural Planning-job live UI acceptance; never start a synthetic job merely to inspect the bar.
- **#493 — DDEV cold-bootstrap reliability:** generic cold/quiesced/isolated fallback still contains `timeout=min(timeout, 600)` for `ddev start -y`; healthy direct-workspace reuse from PR #494 is already working. Bounded infrastructure policy/evidence/tests are outstanding; no blind 600→1800 increase.
- **#512 — remote PM control/Guardian parent:** live same-job repair, manual PM-chat review/release/merge, Guardian exact-main paths proven. Two natural parent acceptance gaps remain: real GitHub `direct_intake` for a new ticket, and Guardian diagnosis during an actual Runtime/n8n outage. Keep open, no failure injection or replacement jobs.
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

1. Read the outcome for Guardian [rollout control 6061451157](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6061451157). Accept Runtime **1.0.141** only with an `executed` audit, exact local main/head, zero active jobs and post-health versions. If it fails, diagnose fresh evidence; do not blindly retry.
2. Update #557 from actual rollout evidence; close only after its remaining natural Planning-UX acceptance. Keep the distinction between deterministic tests and observed UI.
3. Keep #512 OPEN until genuine GitHub `direct_intake` and Runtime/n8n-unavailable Guardian cases occur naturally. Keep Guardian issue #524 OPEN permanently for allow-listed controls/audit.
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
