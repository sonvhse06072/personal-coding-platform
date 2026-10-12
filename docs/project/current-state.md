# Current Project State and Handoff

Status: **Tier-1 mutable working-state index**. This is not a chronological incident log, an approved ProjectBaseline amendment, or proof of a live Runtime/local lock. Repository governance and approved ProjectBaseline revisions remain authoritative; read GitHub/Runtime/local evidence again before any mutation.

Last reconciled: **2026-10-12**. **Canonical PCP #595 remains OPEN / G0 NOT GO.** G0D-T01 has **one code-valid Drupal pair** (both PRs exact-head hosted CI and PM review PASS), but **zero clean unattended end-to-end pairs**: Direct Docker/Python wrapper timed out, model completion recovered by read-only forensics, and PR delivery required the PM GitHub connector. Do not treat the G0 fixture-only CodexAdapter path as the full PCP Planner/Router/Orchestrator/Verifier/Delivery pipeline. [T3 outcome and next feasibility gate](history/g0-02-first-paired-outcome-2026-10-12.md).

**Current GitHub:** PCP `main@9f50848154eb115ae271661f17ce2346cae3e948`, no open PCP PRs. Fixture [PCP PR #4](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/4) and [Direct PR #5](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/5) are both **OPEN/CI SUCCESS**; the two permanent `benchmark/*` bases remain frozen at `39ef13c25b24c4a1b43a720ae53419f479996ed2`. Their CI-green delivery commits are independent GitHub connector commits from byte-verified original working files, not automatic PCP delivery. No further G0D-T01 model calls, retry or merge authorized by this state record.

**WSL/execution authority:** Owner proved isolated `pcp-g0d01` activation and GET-only health checks before the trials; original local G0 Runtime job and Direct journal/workspace must be preserved. **Legacy PCP PostgreSQL** has separately observed historical managed-project active lease/orchestration/pending WorkOrder evidence (2026-10-11 read-only snapshot); legacy Router/Runtime/Executor must NOT be started from those stale records. Strict managed-project no-touch, no shared-host Codex/DDEV/project lease manipulation. A source PR merge does not update deployed G0 images.

**G0/F1 source implementation pending PR #656 (2026-10-12):** candidate `g0_fullpath_candidate` intentionally fails closed before normal RuntimeEngine/PlanOrchestrator, and every candidate HTTP endpoint returns 503. New pure admission contract/tests require a completely separate future fixture identity. **No full-path Runtime/model/DDEV/GitHub delivery activated.** After exact-head CI and source review/merge, next scoped work is to establish a *real hostless deterministic verifier + independent exact-SHA CI delivery* using the existing engine, or stop with an infeasibility decision. [Detailed source gate](history/g0-02-fullpath-source-admission-2026-10-12.md) · [PR #656](https://github.com/sonvhse06072/personal-coding-platform/pull/656).

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

- **GitHub source and local rollout:** PCP `main@9f50848154eb115ae271661f17ce2346cae3e948` after G0 Direct timeout forensic [PR #654](https://github.com/sonvhse06072/personal-coding-platform/pull/654), reviewed/CI-green. A separate Owner WSL G0-only Runtime/Executor activation was observed PASS, and the one PCP fixture job completed; one Direct model coding turn was session-reconciled PASS after wrapper TIMEOUT. **Neither GitHub source merge nor G0 operation restarted legacy PCP.** G0 source/image/Runtime mode and historical DB must not be conflated with PCP normal rollout; no DDEV or provider retry.
- **2026-10-10 Guardian [6093920625](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093920625):** Runtime **1.0.141**, Executor **1.0.35**, Router **1.0.31**, n8n/Antigravity **1.13** and credentials healthy; Runtime/Executor/Antigravity active counts **0 at snapshot**. Local PCP `main` clean `d53fbb07524bb3ca13324e2ed7edac1513367072`, behind GitHub at that observation; do not treat the previous source-diff classification as a fresh post-#614 compare. Earlier [6093879505](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093879505) observed Runtime timeout; later health does not prove its root cause or a permanent zero-job state.
- **Residual acceptance:** Executor source fix [#583](https://github.com/sonvhse06072/personal-coding-platform/pull/583) already merged and Executor 1.0.35 observed, but **natural cold-start proof (#493)** and **autonomous remote outage recovery (#512)** are not established. Earlier Guardian `ddev restart` **900s timeout** and Owner-local recovery are logged in [#512](https://github.com/sonvhse06072/personal-coding-platform/issues/512) and [#524](https://github.com/sonvhse06072/personal-coding-platform/issues/524), not repeated here.
- **Source vs deployed and GH-89 worktree details:** [G0-01 T3 audit](history/g0-01-architecture-audit-2026-10-10.md); no automatic local sync, restart, rollout or historical job/lease mutation.

## Active PCP issues and owner attention

GitHub issue/PR search 2026-10-12: **21 open PCP issues, 0 open PCP PRs**. Fixture has two separate open accepted-code PRs; those are not PCP repository PRs. These are backlog/source-state observations, **not** live job, lease or deployment proof:

- **#593 — PCP completion program:** 17 canonical child workstreams #594–#610; #594 audit DONE. #595 G0-02 has a code-valid Drupal pair (both fixture PR #4/#5 hosted CI and PM review PASS), **0 clean full-product end-to-end pairs** due to Direct wrapper TIMEOUT + manual recovery. **G0 investment NOT GO / insufficient evidence; #596 G1-01 remains gated**. Full pipeline source-only feasibility assessment F1 is next inside #595, not another overlapping issue. [G0D-T01 T3 outcome](history/g0-02-first-paired-outcome-2026-10-12.md).
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

- Historical pilot GH-63 Step 7/PR #85 is already accepted; see [GH-63 audit](https://github.com/sonvhse06072/chonhac/issues/63#issuecomment-6059394452) for exact baseline, job, commits and checkpoint. This historical evidence does not promote a newer ProjectBaseline or authorize a repeat.
- [GH-89 diagnostic](https://github.com/sonvhse06072/chonhac/issues/89#issuecomment-6093934986) reported preserved blocked PCP job `08ae925693b85379b11a54e4dc26121e` with a dirty direct Codex worktree; do not alter it. Owner's [2026-10-11 PCP-only SQL audit](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6106925635) now confirms a historical managed-project active lease with blocked owner. This does not identify the exact lease-owning job or authorize release. Chợ Nhạc issues are not PCP roadmap scope without reusable platform evidence.

## Immediate next safe actions

1. **#594 complete:** evidence [PR #612](https://github.com/sonvhse06072/personal-coding-platform/pull/612) merged; no further G0-01 code. Shared Chợ Nhạc dirty direct worktree and historical lease unresolved remain **no-touch** until separately authorized.
2. **#595 next source action — hostless verification boundary:** [PR #656](https://github.com/sonvhse06072/personal-coding-platform/pull/656) introduces an opt-in **non-executable** fullpath candidate mode and negative gates that refuse startup before Storage.init/host cancel/lease/tick. It does **not** prove normal product parity. After CI/review/merge, assess the real Executor capabilities needed to perform mandatory fixture Drupal tests/CI **without Docker socket/global DDEV** and define a safe exact-SHA delivery contract; if not possible without parallel engine or weakened quality, file G0 investment No-Go proposal within #595. No new model, live DB/container, G0D-T01 replay/retry, old lease operations or Chợ Nhạc access.
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
