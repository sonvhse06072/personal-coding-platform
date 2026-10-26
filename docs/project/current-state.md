# Current Project State and Handoff

Status: **Tier-1 mutable working-state index**, not an approved ProjectBaseline revision, Runtime/WSL rollout attestation, authority change, or chronological log. Verify GitHub and local durable evidence immediately before any mutation. The Constitution, architecture and approved baseline outrank this snapshot.

**Last reconciled: 2026-10-25, P0 #808 queued Runtime seam SOURCE ACCEPTED; Host/LIVE STOP.** [PR #811](https://github.com/sonvhse06072/personal-coding-platform/pull/811) merged `main@463d81f3fee27bc0fd804486e8b941fdf7887d14` after [PM review #5643860078](https://github.com/sonvhse06072/personal-coding-platform/pull/811#pullrequestreview-5643860078) and [postmerge real4 #40207083378](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40207083378) **4,717 PASS/89 skipped**. Owner approved 11 exact SOURCE paths/4 protected. OCI historic pin remains unchanged; queued is not Codex execution. #752 PARKED; #595 HOLD.

## #764 / #777 — Phase B PCP-only source acceptance and Gate A audit

- **B2.2c0 SOURCE ACCEPTED:** [PR #776](https://github.com/sonvhse06072/personal-coding-platform/pull/776), merge `2d536201dd28d94f43dd20903419007c0136261b`. Six approved paths: draft PCP-only registry (`path: null`), inactive baseline, parked `pcp_local_inspect`; PR/postmerge full4 CI PASS. No local model/Docker/worker action. [PM outcome #764](https://github.com/sonvhse06072/personal-coding-platform/issues/764#issuecomment-6378674879).
- **B2.2c1-A1 SOURCE ACCEPTED:** [#779](https://github.com/sonvhse06072/personal-coding-platform/pull/779) + [safe shell #780](https://github.com/sonvhse06072/personal-coding-platform/pull/780); fake-only tests PASS. Owner reported `DOCKER_DESKTOP_SHARED`, controlled exit 2 / LIVE STOP. Owner subsequently accepted shared Docker as a deployment trade-off. Earlier exclusive-daemon A1 STOP is historical evidence, **not** permission to bypass its guard. [Decision #777](https://github.com/sonvhse06072/personal-coding-platform/issues/777#issuecomment-6379866815).
- **Static blockers:** current `.ddev/docker-compose.platform.yaml` uses `/config/projects.yml` in Router/Runtime/Executor, exposing a registry with managed Chợ Nhạc and legacy fixtures. Runtime mounts host Codex/OpenCode home and gitconfig. Executor mounts `/var/run/docker.sock`, project/workspace roots and host `.ddev`. Existing DDEV pre-start builds images and invokes host bridge; `ddev start`, `--prepare` or `--start` are **not read-only Gate A diagnostics**.
- **A2/A3/H0/H1b2 source evidence:** [A2 Owner filtered counts](https://github.com/sonvhse06072/personal-coding-platform/issues/782#issuecomment-6381693431) old PCP 6 containers/3 volumes, new `pcp-local` 0/0/0, not complete resource proof. A3 parked DDEV and H1a offline checker accepted. [Owner H0](https://github.com/sonvhse06072/personal-coding-platform/issues/790#issuecomment-6385186600) old Runtime image unverified. [H1b2 #799](https://github.com/sonvhse06072/personal-coding-platform/pull/799) SOURCE ACCEPTED: pinned Python 3.13.17 `linux/amd64` base manifest, 18 hashed wheels, deny-by-default context and synthetic source TAR. **No built/final OCI image, verified SBOM/attestation or Host UAT.** `--check` still STOP; `pcp-inspect` remains OFF/unrunnable.
- **Operational STOP:** `B22C1_GATE_A_PHYSICAL=NOT_ATTESTED`, `CREDENTIAL_ISOLATION=NOT_ATTESTED`, `LIVE=NOT_AUTHORIZED`, `MODEL_CALLS=0` (in this phase). Do not run DDEV, change Compose/mounts, enable task flags, install credentials, spend model quota, inspect legacy DB/jobs or bypass T02 egress. Chợ Nhạc STRICT NO-TOUCH; #752 PARKED; #595 HOLD; F2/T01/Guardian frozen.

## #752 source accepted; live T02 remains PARKED

[#752](https://github.com/sonvhse06072/personal-coding-platform/issues/752) source gates accepted in [PR #760](https://github.com/sonvhse06072/personal-coding-platform/pull/760), with exact-head/postmerge hosted CI PASS. **No live dispatch**: baseline inactive, runtime/egress not attested and earlier T02 egress overlay safety-blocked; no retry, rename or bypass. G0 #595 HOLD, F2/T01/Guardian frozen, Chợ Nhạc strict no-touch.

| Queue | Status | Evidence / blocker |
| --- | --- | --- |
| #594 | COMPLETED | Live issue closed; #612 merged, exact head `8088e5382412d42790cb083c43e57b482debffc7` |
| #764 / #773 | B2.2c0 SOURCE ACCEPTED; B2.2c1 GATE A PHYSICAL HOLD | [#776](https://github.com/sonvhse06072/personal-coding-platform/pull/776) merged; [postmerge #40053565494](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40053565494) full4 PASS; no local worker deployment |
| #777 / #797 / #800 | H1b2/H1b3 SOURCE ACCEPTED; OCI Host HOLD | [#799](https://github.com/sonvhse06072/personal-coding-platform/pull/799), [#802](https://github.com/sonvhse06072/personal-coding-platform/pull/802) merged; [postmerge real4](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40156915986) PASS. No producer trust root, privileged-builder/no-fallback or disk/egress proof; LIVE STOP |
| #752 source | MERGED / VERIFIED | [PR #760](https://github.com/sonvhse06072/personal-coding-platform/pull/760); PR-head and postmerge 4/4 hosted CI PASS; Runtime not deployed |
| #752 live | NEEDS_OWNER_DECISION | Isolation/egress/credential/baseline/launch gates unresolved; PARKED |
| #595 | BLOCKED | G0 HOLD / NOT GO; comparable accepted cohort absent |
| #596–#599 | BLOCKED | Frozen historical pilot; G0/G1 exit and protected live gates unmet |
| #600–#605 | BLOCKED | G1 exit #599 and G0 #595 required |
| #606–#610 | BLOCKED | G2 exit #605 required |

## Immediate next safe actions

GitHub/Runtime evidence remains separate; Runtime was not queried.

**#800 reprioritized:** [Cloud producer/OCI successor research PARKED P2](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6396801006); research preserved, current accepted offline security and physical STOP retained. No Google Cloud Build selection, new SOURCE approval or Host permit.

**#808 B2-F2 SOURCE DRAFT:** [PR #813](https://github.com/sonvhse06072/personal-coding-platform/pull/813), `ai/808-no-legacy-replay-source-v1`, base `a03cb8c`. Owner chat approved `DEC-PCP-B2-F2-808-LEGACY-FIXTURES-SCOPE-V1`:12 paths/4 protected. Repair `cae8750` [CI40263331491](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40263331491) actual full4 PASS:4,869 passed/89 skipped/3 dependency warnings; old40215827175's9 failures retained. Production guards unchanged. Final handoff HEAD CI/PM review pending; no acceptance/merge or physical proof. Host/LIVE STOP; #752 PARKED, #595 HOLD; Chợ Nhạc NO-TOUCH.

## Active investment / execution gates

- **G0 #595: HOLD / NOT GO.** Historical G0D-T01 had code-valid fixture results but no clean unattended end-to-end comparable Direct-vs-full-PCP pair. F2 delivery was PM-assisted, not autonomous; there is no matched quality/time/cost cohort, p50/p90 proof, or USD billing evidence. Do not promote source/CI success into G0 GO. [Benchmark authority/evidence](https://github.com/sonvhse06072/personal-coding-platform/issues/595).
- **PCP-light: active new-task-only path, not legacy Runtime.** [Guide](../pcp-light/README.md), [#593](https://github.com/sonvhse06072/personal-coding-platform/issues/593): exclusive job journal/worktree, one Codex turn, exact Owner/source SHA, bounded paths, deterministic checks, Draft PR and human PM/exact-head CI. No automatic retry/merge/deploy. Preserve completed #725/#729/#734/#738 journals; never rerun them.
- **G1 #596: frozen current coding pilot.** An earlier isolated no-model job `2c6db0aa6f19*` proved corrected MCP→HTTP→Executor→DDEV Node phase PASS (0 model calls) and is preserved as smoke evidence. A **different** G1-T01 original job and one-use DB continuation ended `db_create_failed` (Docker Compose exit 1; NETWORK_ERROR/DAEMON_ERROR classes, cause inconclusive), **0 PCP coding model calls** and no pilot DB/network/container remaining in that read-only inventory. Both one-use markers consumed; **NO RETRY/RESET/REPLACEMENT**, no speculative Docker repair or new G1 activation. See [#596 incident and PM freeze](https://github.com/sonvhse06072/personal-coding-platform/issues/596#issuecomment-6196707676). Direct fixture [PR #6](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/pull/6) stays accepted but OPEN/unmerged; do not merge it without a separate benchmark decision.
- **G1-T02:** source-only [#752](https://github.com/sonvhse06072/personal-coding-platform/issues/752) accepted and hosted CI checked; **PARKED / NOT DISPATCHED**. Baseline `active_revision: null`, parked Compose/broker and disallowed egress overlay remain unchanged. No model/provider call, WSL/DDEV startup, retry or credentials. No historical job reset.

- **F2 historic singleton: frozen.** Original isolated job `88b9e0d8500147a9857621d18875a8e4` BLOCKED at 2/2 model calls after scoped changes; [fixture draft PR #4](https://github.com/sonvhse06072/pcp-g0-fullpath-fixture/pull/4) is PM-assisted/open, not a PCP autonomous delivery. Preserve C2 database/volumes, credentials, counters, jobs, fixtures and evidence; F2 Router/Runtime/Executor remain parked as last confirmed, **do not infer current process health**. No restart, new job, third call or journal reuse. [G0 evidence](https://github.com/sonvhse06072/personal-coding-platform/issues/595).
- **Legacy managed-project Runtime/DB not safe to start by inference.** Prior read-only inventory showed old active project lease/orchestrations, pending WorkOrders, and a blocked Chợ Nhạc managed job. Starting Runtime may re-enqueue/cancel jobs and touch foreign project state; GitHub source merges do not activate its services. **No legacy Runtime/DDEV/DB operation without independent safe-start and lease proof.**

## CI and residual operations

- [#665 CI](https://github.com/sonvhse06072/personal-coding-platform/issues/665): hosted full4 on code PR/main; only `current-state.md`/history T1/T3 may skip service suites. Structure/doc authority always execute. CI does not prove Runtime deployment.
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
