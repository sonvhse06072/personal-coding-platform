# Current Project State and Handoff

Status: **Tier-1 mutable working-state index**, not an approved ProjectBaseline revision, Runtime/WSL rollout attestation, authority change, or chronological log. Verify GitHub and local durable evidence immediately before any mutation. The Constitution, architecture and approved baseline outrank this snapshot.

Last reconciled: **2026-10-24, SOURCE ONLY; NOT deployed.** `main@f613890692aac5b92a747035f7370431dfc163e5`: [#771](https://github.com/sonvhse06072/personal-coding-platform/pull/771) B2.2b, [#772](https://github.com/sonvhse06072/personal-coding-platform/pull/772) T1 and [#774](https://github.com/sonvhse06072/personal-coding-platform/pull/774) P1 accepted; [CI #40050596217](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40050596217) real full4 PASS. T02 PARKED; G0 HOLD.

## #752 source accepted; live T02 remains PARKED

- **Authority:** Owner explicitly approved `DEC-G1-T02-DELIVERY-SOURCE-V1` and `DEC-G1-T02-CI-PROVENANCE-PATHS-V1` in the task supplied to this developer session. [Comment 6313229565](https://github.com/sonvhse06072/personal-coding-platform/issues/752#issuecomment-6313229565) remains a **proposal**, not a post-approval record. The maximum is the 12 paths listed below; no operational permission follows.
- **Scope:** `services/runtime/app/{config.py,trusted_codex_broker.py,required_ci.py,engine_delivery.py}`, `services/runtime/tests/{test_g1_t02_identity.py,test_g0_fullpath_required_ci.py,test_delivery.py}`, `services/ddev-executor/app/{main.py,github_delivery.py}`, `services/ddev-executor/tests/{test_g1_t02_ddev_identity.py,test_github_delivery.py}`, and this T1. No other source/config/workflow/baseline path is authorized.
- **Implementation:** separate exact default-OFF delivery + identity flags; fixture-only repository/job/branch/seed and one normal seed-child commit with exactly two modified PHP paths. Recheck isolated DDEV identity and repository before publish. Dispatch proof binds pinned workflow blob at run main SHA, exact candidate Git objects, job steps and pre-validation logs; failed/duplicate candidate runs fail closed. Runtime binds proof to current job/source/branch/open PR, stops on CI failure, and waits for PM review after verified CI instead of completing.
- **P1 repair scope:** only `services/ddev-executor/app/main.py`, `services/ddev-executor/tests/test_g1_t02_ddev_identity.py`, and this T1. Reject the configured source symlink before path resolution; retain the exact fixture repository gate. Regression uses a real temporary symlink with real path resolution and mocked Git identity reads. No other gate or source/config/workflow/baseline change.
- **Validation / checkpoint:** P1 symlink regression PASS after repair; Owner WSL full4 **3,778 PASS / 88 skipped**. PM [COMMENT review #5622878258](https://github.com/sonvhse06072/personal-coding-platform/pull/760#pullrequestreview-5622878258) (not self-APPROVE); exact candidate `602b550ac502bebc2c6569821e96ed934edde9d6` and merge `2c6348d69cf64c611762b1a188f69db57b3af907` each passed 4/4 hosted suites. No Runtime/model/fixture execution.
- **Preserved:** PARKED template, validator, baselines and Compose byte-for-byte; baseline `active_revision: null`, `revisions: {}`, `entrypoint=/bin/false`, flags OFF. Egress activation `NOT_REVIEWED`; never retry/recreate/bypass the blocked overlay. No service/model/fixture operation performed.

| Queue | Status | Evidence / blocker |
| --- | --- | --- |
| #594 | COMPLETED | Live issue closed; #612 merged, exact head `8088e5382412d42790cb083c43e57b482debffc7` |
| #764 / #773 | B2.2b/P1 SOURCE ACCEPTED; B2.2c/B3 HOLD | [#774](https://github.com/sonvhse06072/personal-coding-platform/pull/774) full4 PASS; PCP-only baseline/worker/transfer unproven |
| #752 source | MERGED / VERIFIED | [PR #760](https://github.com/sonvhse06072/personal-coding-platform/pull/760); PR-head and postmerge 4/4 hosted CI PASS; Runtime not deployed |
| #752 live | NEEDS_OWNER_DECISION | Isolation/egress/credential/baseline/launch gates unresolved; PARKED |
| #595 | BLOCKED | G0 HOLD / NOT GO; comparable accepted cohort absent |
| #596–#599 | BLOCKED | Frozen historical pilot; G0/G1 exit and protected live gates unmet |
| #600–#605 | BLOCKED | G1 exit #599 and G0 #595 required |
| #606–#610 | BLOCKED | G2 exit #605 required |

## Immediate next safe actions

GitHub/Runtime evidence remains separate; Runtime was not queried.

**Next safe action:** [#764 B2.2c0](https://github.com/sonvhse06072/personal-coding-platform/issues/764#issuecomment-6378302228) isolated PCP-only registry/baseline/startup proposal is **NOT APPROVED**. No worker or WSL rollout, no legacy lease/DB restart, no T02 egress bypass. Dedicated Docker boundary, safe Codex/GitHub auth and budget require new live evidence. #752 PARKED, #595 HOLD; F2/T01/Guardian frozen, Chợ Nhạc no-touch.

## Active investment / execution gates

- **G0 #595: HOLD / NOT GO.** Historical G0D-T01 had code-valid fixture results but no clean unattended end-to-end comparable Direct-vs-full-PCP pair. F2 delivery was PM-assisted, not autonomous; there is no matched quality/time/cost cohort, p50/p90 proof, or USD billing evidence. Do not promote source/CI success into G0 GO. [Benchmark authority/evidence](https://github.com/sonvhse06072/personal-coding-platform/issues/595).
- **PCP-light: active new-task-only practical coding path, NOT legacy Runtime PCP.** Owner-run `scripts/pcp-light-run.py --execute` uses an exclusive `~/.pcp-light/jobs/<key>` journal/worktree, one native Codex turn, exact Owner issue/body SHA and source, limited `scripts/pcp-light-*.py`, `tests/test_pcp_light_*.py`, `docs/pcp-light/*.md` paths, AST/Git quality gates, and a draft PR with human PM review plus exact-head hosted full CI. No automatic model retry, merge or deployment. [Operator guide](../../docs/pcp-light/README.md); [parent #593](https://github.com/sonvhse06072/personal-coding-platform/issues/593). The completed historical jobs #725/#729/#734/#738 are **not runnable again**; preserve their original journals/worktrees.
- **G1 #596: frozen current coding pilot.** An earlier isolated no-model job `2c6db0aa6f19*` proved corrected MCP→HTTP→Executor→DDEV Node phase PASS (0 model calls) and is preserved as smoke evidence. A **different** G1-T01 original job and one-use DB continuation ended `db_create_failed` (Docker Compose exit 1; NETWORK_ERROR/DAEMON_ERROR classes, cause inconclusive), **0 PCP coding model calls** and no pilot DB/network/container remaining in that read-only inventory. Both one-use markers consumed; **NO RETRY/RESET/REPLACEMENT**, no speculative Docker repair or new G1 activation. See [#596 incident and PM freeze](https://github.com/sonvhse06072/personal-coding-platform/issues/596#issuecomment-6196707676). Direct fixture [PR #6](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/pull/6) stays accepted but OPEN/unmerged; do not merge it without a separate benchmark decision.
- **G1-T02 source accepted (21/10/2026; NOT activated):** Owner approved [15 paths](https://github.com/sonvhse06072/personal-coding-platform/issues/752#issuecomment-6221894639) plus separate [`config.py`](https://github.com/sonvhse06072/personal-coding-platform/issues/752#issuecomment-6312457266). [PR #758](https://github.com/sonvhse06072/personal-coding-platform/pull/758) registered exact default-OFF T02 only behind Owner flag, identity/base, isolated DDEV and five autonomy flags false; T01/smoke unchanged. Merge `main@5c28077c2fdf602161600171bb4298f24a461381`; [PR CI](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/39576294064) and [postmerge CI](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/39576554460) **4/4 real hosted pytest PASS (attempt 1)**. Earlier #753–#756 accepted. This is **source/CI only**, not live Runtime, baseline or benchmark proof.
- **G1-T02 remaining gates:** [#752](https://github.com/sonvhse06072/personal-coding-platform/issues/752) **PARKED / NOT DISPATCHED**. Baseline stays `active_revision: null`, `revisions: {}`; Compose `entrypoint=/bin/false`, broker OFF. Egress overlay write blocked by safety guard: `egress_activation=NOT_REVIEWED`, **never retry/bypass**. No independent Docker/DDEV/DB/network, PCP-vs-Direct workspace/credential, provider/GitHub auth/egress or budget proof; **no activation, tokens, fixture/model dispatch**. G0 #595 HOLD/NOT GO; T01/F2 FROZEN; Guardian PARKED; Chợ Nhạc STRICT NO-TOUCH.
- **F2 historic singleton: frozen.** Original isolated job `88b9e0d8500147a9857621d18875a8e4` BLOCKED at 2/2 model calls after scoped changes; [fixture draft PR #4](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/pull/4) is PM-assisted/open, not a PCP autonomous delivery. Preserve C2 database/volumes, credentials, counters, jobs, fixtures and evidence; F2 Router/Runtime/Executor remain parked as last confirmed, **do not infer current process health**. No restart, new job, third call or journal reuse. [G0 evidence](https://github.com/sonvhse06072/personal-coding-platform/issues/595).
- **Legacy managed-project Runtime/DB not safe to start by inference.** Prior read-only inventory showed old active project lease/orchestrations, pending WorkOrders, and a blocked Chợ Nhạc managed job. Starting Runtime may re-enqueue/cancel jobs and touch foreign project state; GitHub source merges do not activate its services. **No legacy Runtime/DDEV/DB operation without independent safe-start and lease proof.**

## CI and residual operations

- [#665 CI](https://github.com/sonvhse06072/personal-coding-platform/issues/665): hosted full4 on code PR/main; docs-only PR may skip service pytest, while structure/doc-authority must execute. T02 [PR #39883810525](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/39883810525) and [postmerge #39884075677](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/39884075677) both 4/4 actually executed PASS; not a Runtime rollout.
- **#665 security residual / FREE decision:** Owner explicitly chose `CP-665-PROTECTED-MAIN-V1 / FREE`: keep PCP **private** without GitHub Pro purchase, and **accept unprotected `main` / non-enforced required-status checks** as a known server-side risk. The four GitHub-hosted CI checks, PM exact-HEAD review and expected-head merge remain mandatory **manual process gates**, not actual server-enforced rules. The dedicated `SonVH` PCP runner was Owner-reported stopped/de-registered (no GitHub app runner-inventory API proof); no re-registration without a separate protected Owner decision. [Canonical #665](https://github.com/sonvhse06072/personal-coding-platform/issues/665) stays open as an accepted/known residual, not a pending payment request.
- **Guardian is operationally PARKED / UNAVAILABLE under approved Option A:** [#524](https://github.com/sonvhse06072/personal-coding-platform/issues/524) remains an audit channel but `pcp-guardian.yml` still targets the now-retired self-hosted runner. No remote Guardian command execution or automatic outage recovery should be expected, and the workflow/history must not be deleted. [#512](https://github.com/sonvhse06072/personal-coding-platform/issues/512) remains OPEN for residual natural recovery evidence after a separately approved replacement. [#493](https://github.com/sonvhse06072/personal-coding-platform/issues/493) remains OPEN for Executor 1.0.35 cold-start/provenance; no synthetic restart.

## Active PCP issues and owner attention

- [#593 PCP completion program](https://github.com/sonvhse06072/personal-coding-platform/issues/593) governs outcome, autonomy, owner attention and cost. [#594](https://github.com/sonvhse06072/personal-coding-platform/issues/594) G0 audit completed; #595 investment gate remains HOLD, #596 existing G1 pilot FROZEN. #597–#599, G2 #600–#605, and G3 #606–#610 are **planned**, not dispatched by this doc. [#588](https://github.com/sonvhse06072/personal-coding-platform/issues/588) future Project Discovery is DEFERRED. Historical duplicate planning tickets #586/#587/#589/#590 closed **without** implying all capabilities are implemented or leases released.
- Next practical PCP-light task must solve an observed defect/owner-cost bottleneck, not be created merely for synthetic throughput or toolchain testing. Before new work, measure accepted task outcomes, owner interventions, source and PR CI, real elapsed time, model-reported cached/uncached/input/output and cash **if available**. A PR body is useful telemetry but not independent verification; original journal provenance and live GitHub facts outrank it.
- Do not claim local PCP source has fast-forwarded to the newest GitHub SHA, or Runtime has rolled out, from a merge/CI result. One task/worktree writer at a time; preserve original journals on STOP and never run blind recovery.

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

## Standing safety boundary

**Chợ Nhạc strict no-touch / historical job preservation.**

Owner's PCP-side prohibition remains active: no PCP agent, PM Bridge, Guardian, Codex task, workflow or diagnostic may mutate or inspect the Chợ Nhạc repository, shared worktree, DDEV, DB, lease, secrets, deployment or its existing jobs as a side effect of PCP work. Historical Chợ Nhạc GH-89 job `08ae925693b85379b11a54e4dc26121e` and an old managed-project lease were observed blocked/uncertain; no status is inferred now, and no reset/cancel/replacement is allowed. This **operational** no-touch rule does not falsely claim a deployed technical denylist. PCP-light is explicitly **PCP-repository-only** and does not inherit any Chợ Nhạc writer privilege.

Developer agents do not merge. Exact-HEAD tests, PM review, protected approvals and expected-head privileged merge checks remain mandatory; GitHub source and T1 prose cannot grant authority or reset durable-state counters.
