# Current Project State and Handoff

Status: **Tier-1 mutable working-state index**, not an approved ProjectBaseline revision, Runtime/WSL rollout attestation, authority change, or chronological log. Verify GitHub and local durable evidence immediately before any mutation. The Constitution, architecture and approved baseline outrank this snapshot.

Last reconciled: **2026-10-16 (GitHub source/CI, not local deployment)**. PCP `main@6c4d1fa7938840dbea691d0ea2c8b88459115a4c`; [#739](https://github.com/sonvhse06072/personal-coding-platform/pull/739) squash-merged after [exact PR-head CI #38849173754](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38849173754) PASS 4/4 and PM source review. [Exact postmerge push/main #38850123092](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38850123092) **completed SUCCESS attempt 1, 4/4**. [#738](https://github.com/sonvhse06072/personal-coding-platform/issues/738) CLOSED/completed. At this verification: **22 PCP issues open, 0 PCP PRs open**; these counts are ephemeral.

## Active investment / execution gates

- **G0 #595: HOLD / NOT GO.** Historical G0D-T01 had code-valid fixture results but no clean unattended end-to-end comparable Direct-vs-full-PCP pair. F2 delivery was PM-assisted, not autonomous; there is no matched quality/time/cost cohort, p50/p90 proof, or USD billing evidence. Do not promote source/CI success into G0 GO. [Benchmark authority/evidence](https://github.com/sonvhse06072/personal-coding-platform/issues/595).
- **PCP-light: active new-task-only practical coding path, NOT legacy Runtime PCP.** Owner-run `scripts/pcp-light-run.py --execute` uses an exclusive `~/.pcp-light/jobs/<key>` journal/worktree, one native Codex turn, exact Owner issue/body SHA and source, limited `scripts/pcp-light-*.py`, `tests/test_pcp_light_*.py`, `docs/pcp-light/*.md` paths, AST/Git quality gates, and a draft PR with human PM review plus exact-head hosted full CI. No automatic model retry, merge or deployment. [Operator guide](../../docs/pcp-light/README.md); [parent #593](https://github.com/sonvhse06072/personal-coding-platform/issues/593). The completed historical jobs #725/#729/#734/#738 are **not runnable again**; preserve their original journals/worktrees.
- **Latest PCP-light acceptance:** #738 required one native `gpt-6-luna` Medium coding call (112.4s model elapsed; 893,251 reported input including 809,856 cached, 83,395 uncached; 7,869 output; cash cost unknown), no extra model call or PM repair commit, and generated [#739](https://github.com/sonvhse06072/personal-coding-platform/pull/739). Current read-only `pcp-light-pr-review.py` accepts strictly bounded 1–4 linear commit chains, checks intermediate paths, preserves four exact-head CI requirements and independently reviewed repair status. This is **source/CI-proven**, not yet a naturally observed live open multi-commit repaired PR. Earlier #734/#736 did require two PM repair commits after one model call; do not count it as first-pass. No claim that model input volume equals unique context bytes or billable cost.
- **G1 #596: frozen current coding pilot.** An earlier isolated no-model job `2c6db0aa6f19*` proved corrected MCP→HTTP→Executor→DDEV Node phase PASS (0 model calls) and is preserved as smoke evidence. A **different** G1-T01 original job and one-use DB continuation ended `db_create_failed` (Docker Compose exit 1; NETWORK_ERROR/DAEMON_ERROR classes, cause inconclusive), **0 PCP coding model calls** and no pilot DB/network/container remaining in that read-only inventory. Both one-use markers consumed; **NO RETRY/RESET/REPLACEMENT**, no speculative Docker repair or new G1 activation. See [#596 incident and PM freeze](https://github.com/sonvhse06072/personal-coding-platform/issues/596#issuecomment-6196707676). Direct fixture [PR #6](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/pull/6) stays accepted but OPEN/unmerged; do not merge it without a separate benchmark decision.
- **F2 historic singleton: frozen.** Original isolated job `88b9e0d8500147a9857621d18875a8e4` BLOCKED at 2/2 model calls after scoped changes; [fixture draft PR #4](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/pull/4) is PM-assisted/open, not a PCP autonomous delivery. Preserve C2 database/volumes, credentials, counters, jobs, fixtures and evidence; F2 Router/Runtime/Executor remain parked as last confirmed, **do not infer current process health**. No restart, new job, third call or journal reuse. [G0 evidence](https://github.com/sonvhse06072/personal-coding-platform/issues/595).
- **Legacy managed-project Runtime/DB not safe to start by inference.** Prior read-only inventory showed old active project lease/orchestrations, pending WorkOrders, and a blocked Chợ Nhạc managed job. Starting Runtime may re-enqueue/cancel jobs and touch foreign project state; GitHub source merges do not activate its services. **No legacy Runtime/DDEV/DB operation without independent safe-start and lease proof.**

## CI and residual operations

- [#665 CI modernization](https://github.com/sonvhse06072/personal-coding-platform/issues/665): `pull_request` runs four stable checks on ephemeral GitHub-hosted Ubuntu 24.04; trusted `push main` uses the owner `SonVH` self-hosted runner. Trusted-base doc-authority/changed-file classifier remains enabled; narrow pure T1/T3 docs-only PRs skip service pytest but **all four status contexts still appear** and root structure/doc authority executes.
- The PC/runner outage interrupted [#737's exact postmerge run #38808710862](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38808710862); after Owner restored runner, ONE interrupted Executor job was retried, and run recovered to SUCCESS 4/4 attempt 2. This was an observed host-offline interruption, not an established code regression. [#739 exact postmerge run](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38850123092) later passed 4/4 attempt 1.
- **#665 residual security risk remains OPEN:** a PR-controlled workflow may target the persistent runner; independent runner registration/workflow access isolation and branch protection/required status enforcement were not established (GitHub reported `main protected:false`, ruleset query permissions limited). Never claim all untrusted PRs are host-isolated. Changing persistent runner scope or trusted push-main CI needs an independently approved safe operational decision; do not change it as a T1 documentation task.
- [#493](https://github.com/sonvhse06072/personal-coding-platform/issues/493) retains natural Executor 1.0.35 cold-start/provenance acceptance; [#512](https://github.com/sonvhse06072/personal-coding-platform/issues/512) retains remote-control/Guardian natural outage-recovery proof; [#524](https://github.com/sonvhse06072/personal-coding-platform/issues/524) is a **permanent Guardian audit channel**, not a coding ticket. Do not synthesize outages or restart services merely to close these.

## Priorities and backlog boundaries

- [#593 PCP completion program](https://github.com/sonvhse06072/personal-coding-platform/issues/593) governs outcome, autonomy, owner attention and cost. [#594](https://github.com/sonvhse06072/personal-coding-platform/issues/594) G0 audit completed; #595 investment gate remains HOLD, #596 existing G1 pilot FROZEN. #597–#599, G2 #600–#605, and G3 #606–#610 are **planned**, not dispatched by this doc. [#588](https://github.com/sonvhse06072/personal-coding-platform/issues/588) future Project Discovery is DEFERRED. Historical duplicate planning tickets #586/#587/#589/#590 closed **without** implying all capabilities are implemented or leases released.
- Next practical PCP-light task must solve an observed defect/owner-cost bottleneck, not be created merely for synthetic throughput or toolchain testing. Before new work, measure accepted task outcomes, owner interventions, source and PR CI, real elapsed time, model-reported cached/uncached/input/output and cash **if available**. A PR body is useful telemetry but not independent verification; original journal provenance and live GitHub facts outrank it.
- Do not claim local PCP source has fast-forwarded to the newest GitHub SHA, or Runtime has rolled out, from a merge/CI result. One task/worktree writer at a time; preserve original journals on STOP and never run blind recovery.

## Resume procedure

1. Read repository `AGENTS.md`, `docs/project/README.md`, then this T1, with relevant topical T2 and T3 only; read `README.md` for operational commands. [Context contract](context-memory-architecture.md) specifies authority tiers; standalone Context Composer is not automatically Runtime-integrated.
2. Recheck live GitHub main/issue/PR/CI and the exact local branch/worktree/job/lease before any write, PM review/merge or new Owner WSL `--execute`. Review actual diff/tests. Keep source/CI success separate from deployed Runtime/fixture evidence.
3. If no natural new task exists, do not create a placeholder PCP-light task or retry frozen G1/F2. T1 updates are mutable evidence (via reviewed `ai/*` PR); protected T0/T2, CI, budgets, baselines and security need genuine Human Owner approval.

## Historical managed-project continuity (NOT current Chợ Nhạc runtime status)

The following legacy automated continuity block is retained for existing parser compatibility and historical provenance only. **It is not authority to restart, resume, cancel or touch its project.**

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

## Chợ Nhạc strict no-touch / historical job preservation

Owner's PCP-side prohibition remains active: no PCP agent, PM Bridge, Guardian, Codex task, workflow or diagnostic may mutate or inspect the Chợ Nhạc repository, shared worktree, DDEV, DB, lease, secrets, deployment or its existing jobs as a side effect of PCP work. Historical Chợ Nhạc GH-89 job `08ae925693b85379b11a54e4dc26121e` and an old managed-project lease were observed blocked/uncertain; no status is inferred now, and no reset/cancel/replacement is allowed. This **operational** no-touch rule does not falsely claim a deployed technical denylist. PCP-light is explicitly **PCP-repository-only** and does not inherit any Chợ Nhạc writer privilege.

Developer agents do not merge. Exact-HEAD tests, PM review, protected approvals and expected-head privileged merge checks remain mandatory; GitHub source and T1 prose cannot grant authority or reset durable-state counters.
