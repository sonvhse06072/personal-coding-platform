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

- GitHub main last checked at **104900d8069a2db9d90850e53b5f81557257a42b** (PR #560 / issue #561 follow-up). This commit includes source code declaring **Runtime 1.0.134**. Re-read the current branch head before using this SHA as an exact-match precondition.
- Runtime **1.0.132** rollout was accepted via Guardian result **6049394135**, following quiescence result **6049369444**: local PCP main was clean at **b0c0e9a43634b4b133382a2b2cab4c5828372465**, Router **1.0.31**, executor **1.0.33**, and no active work at that observation. This quiescence proof is **not reusable** for later rollouts.
- Issue #561 records later **Runtime 1.0.133** Guardian deployment with stable parent checkpoint 182; issue #562 contains read-only diagnostics from **Runtime 1.0.134**. Those are point-in-time evidence; current running versions, health and local source must be checked live.
- Dashboard workflow-progress implementation from #557 / PR #558 was merged in 1.0.132; #557 remains open on GitHub as a tracking issue. Estimated workflow percentage is based on durable workflow stages, not ETA or budget consumption.
- GitHub PR listing showed no open PCP PR at this reconciliation. Treat this as an observation, not a persistent invariant.

## Active PCP issues and owner attention

- **#562 — protected review/merge recovery:** Chợ Nhạc GH-63 Step 7 is blocked by required different-provider reviewer independence. Preferred direction is a genuine late independent review of the exact verified head, preserving the same job, not an automatic waiver. The proposal explicitly requires a separate Human Owner approval for changes to this review/merge trust boundary. Do not bypass by resetting review policy, counters, identity or orchestrator state.
- **#493 — DDEV cold/bootstrap reliability:** bounded cold image-start timeout/recovery still needs evidence-based repair. Do not blindly increase timeout or create extra retries.
- **#512 — remote PM control parent:** keep open for naturally observed remaining acceptance evidence; no synthetic jobs/outages simply to close it.
- **#524 — persistent Guardian commands/audit:** intentionally open operations channel, not engineering backlog.
- **#557 — progress UI tracking:** implementation merged in PR #558; reconcile the open issue only against actual acceptance/owner UI evidence.
- **#563 — documentation reliability hardening:** owner-approved, bounded T1 hygiene, deterministic retrieval correctness and evaluation/adoption. This is separate from Runtime/reviewer recovery.

Current Human Owner attention: #562 requires an explicit approved review-governance choice before implementing a critical late-review eligibility path. Do not treat a normal doc hygiene PR as this approval.

## Chợ Nhạc managed-project checkpoint

- Active configured approved baseline: **pilot-v1-2026-10-04-dec033-r3**, source **aa8e68dd9aea6740de446151eb97615931de9b40**. Existing and new WorkOrders must respect their **own pinned revision**; do not silently advance or rewrite authority to follow newer main.
- GH-63 / parent plan **pm-b0748be27f8446a0813c2d1fe7d697fd**: Step 7 WorkOrder **EE-0-04-event-engagement-analytics**, preserved job **057f6acff17b501eae3a673cbb6bbe36**, Chợ Nhạc PR **#85** at exact verified head **90c84d38692f781e1df91e85d253897d68458638**.
- The last cited Runtime 1.0.134 diagnostic in PCP #562 reported parent checkpoint **182**, stably blocked at **pm_merge_ineligible:required_review_independence_not_satisfied**, despite passing executable checks, evaluator and exact-head CI. This is **historical observed state**, not authorization to mutate the job or proof the state has not changed since.
- Check Chợ Nhạc GH-63 and PCP #562 plus fresh Runtime plan_progress/diagnostics before inferring any next WorkOrder, PM merge, supervised hold or continuation identity.
- Prior AP-MVP-03 was merged via Chợ Nhạc PR #84. Completed-stage details and retired pilots are historical evidence, not active T1 instructions.

## Immediate next safe actions

1. For #562 / GH-63 Step 7, obtain/revalidate exact current plan/blocked-review evidence. Keep the PR blocked until a genuinely independent review or an explicit protected Owner decision has satisfied the existing governance.
2. Complete #563 as small reviewed PRs: T1 cleanup first, retrieval correctness second, benchmark/adoption third. No new memory service, vector DB or Runtime execution-semantic change by implication.
3. Reassess #493 after a safe managed-project checkpoint; preserve healthy active work before any DDEV/Runtime rollout.
4. Use existing safe remote-control/Guardian paths with exact identity, idempotency and fresh preconditions; no arbitrary shell/SQL edits, force push, reset, stashing, destructive cleanup or unbounded retries.

## Historical and detailed evidence pointers

- Memory model and accepted original benchmark: #313, #314, #317; docs/project/context-memory-architecture.md.
- Baseline/document governance hardening: #322; approved source in AGENTS.md / docs/project/constitution.md.
- Incident-learning and PM triage: #406, docs/project/operating-model.md, docs/project/history/episodes.md.
- Remote PM/Guardian controls: #512 and #524; Runtime state and audit events are authoritative for current actions.
- Chợ Nhạc old/retired ExecutionPlan and rollout details: GH-63, PCP issues #424, #466, #493 and Git history of this file. Completed chronology belongs in GitHub/Git/Runtime/T3, not this replace-in-place snapshot.
- Review required code, tests, and exact branch diff for implementation; high-volume CI logs, transcripts, and diagnostics belong at T4 and are fetched only when specifically needed.

## Standing safety boundary

Developer agents never merge. Required deterministic verification, applicable independent review, exact-head CI, protected decisions and expected-head privileged merge checks are never waived by a status summary. Live locks, incident history, old PR evidence or T1 prose cannot override authoritative current Runtime/GitHub state.
