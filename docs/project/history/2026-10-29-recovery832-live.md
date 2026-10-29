# Same-identity #831 recovery: actual rollout and Draft PR #833

Executed 2026-10-29 under [PM6499496019](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6499496019),
with the narrowly conditioned [binding disposition6500237978](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6500237978).
One operator/writer, evidence branch `ai/815-recovery832-live`, checkout
`/home/sonvh/pcp-recovery832-live`. No Developer merge or independent acceptance.

**Pre-finalization result:** SAME job `a8851f89dd3e4e582c697ec1fe6d8cdb` delivered one real
[Draft PR #833](https://github.com/sonvhse06072/personal-coding-platform/pull/833),
head `4161ba059002c7aaf3fd35a88e3b0b80065c62b7`; four hosted suites executed and
passed at that head. Durable status is **blocked / execution verified /
awaiting_independent_pm_review**, receipt **running/gen2**, lease **active/gen1**.
`delivery_finalized=false`; this is delivery evidence, not PM acceptance or lease release.
Workers and both permits are disabled; DB/tokenless HTTPS observer remain available.

Finalization under PM6501364012 subsequently completed the job; see the final
section for current afterimages. Earlier sections retain the execution audit.

## Source, identity and evidence classes

Accepted repair **R=1f9b5d50a18a7b93e6a22c6191d59985d4d3892a** remains actual main.
PR #832 merge parents/tree and [postmerge40891720152](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40891720152)
were independently re-read by the operator: four executed suites, 5241 passed/166 skipped.
Original task/baseline **S=b97ade581fecad4db2146258e5ca02c3902189e0** and revision
`pcp-local-successor-830-b97ade5-20261029` remain unchanged. All five reviewed S..R
commits/20 paths match; full-history pilot/Router/model/policy inputs are unchanged.
The canonical task clone remains clean at S; R objects were fetched for ancestry
validation without switching it. No baseline or source registry was rewritten.

Original #831 body hash `c05077c5838a3fb1fbd0ba53930f2348fc7ec52531a049df55761540ed000858`
and goal hash `b3d8bbf7a58da8d15605d23670e02f4b3af9d2c966cdfdf8f45d424a41e47640`
remain exact. Initial full 11-table/three-sequence snapshot matched retained hash
`62491980c3c6ab686661035c43175bedb19cc3915e877c172598b018bce94dff`: claimed/gen1,
no job/lease/workspace/remote branch or PR. Full receipt timestamps were compared.

| Class | Outcome | Actual evidence |
| --- | --- | --- |
| SOURCE | PASS | Accepted R/tree/postmergeCI, clean S task authority, exact repair history; no application source changes in this evidence PR. |
| FIXTURE | PASS | Credential-free/network-none real Docker probe reproduced first-start false→null metadata and stable full configuration across a subsequent restart. |
| FIXTURE | NOT TESTED this session | PR #832 PostgreSQL/Git/restored-copy regressions remain separately classified in the accepted packet. No new fixture is claimed as LIVE execution. |
| PHYSICAL | PASS | R images/files/modes/toolchain/security probes; actual role grants, publisher/account reads, same containers, schema/no schema mutation; actual verifier S containers exited 0. |
| LIVE | PASS | One supported registration, one fenced execution, one Luna invocation, two mandatory phases, verified commit, one Draft task PR and four exact-head suites. |
| LIVE | PASS | Real populated tokenless browser, normal TLS validation; 352 successful HTTP 200 snapshot responses, no form/cookie/page error, offline/reload/reconnect after worker shutdown. |
| LIVE | NOT TESTED | PM acceptance/finalization/merge; actual terminal completed/failed/cancelled dashboard states; VPN ON/parity and second-machine LAN. |

## Measured R release and unchanged roles

Release directory:
`/home/sonvh/pcp-local-adoption825-v4/releases/claim-recovery-1f9b5d50a18a7b93e6a22c6191d59985d4d3892a`.
One serial Runtime build and one Executor build; no Router/observer rebuild or relabel.
Services archive SHA256 `eac12fd3571b0dc5473588ff367045aa36d4159d197cd8c950c0233b28736e75`;
Runtime input tree `2df382a9f1e39258ea9d39728249f79d822272ce`, Executor tree
`72e511d16fec05d184c2c61bd2d1e57ab9aa0fc7`. Accepted complete R tree is
`9868134739591387145f3a15e4e5c16745c0e64c`.

| Role | Source | Immutable image ID |
| --- | --- | --- |
| Runtime | R | `sha256:0b4d39efde3cdb12be9b650bfb74477bd4d800dcf3e457235e9bea4db2da6bde` |
| Executor | R | `sha256:3cd95064283590141192d8d10216961239c35537c096d173d463130095c734bb` |
| Verifier | S | `sha256:6f057d0851e3c3e6daefc9509341683974c52d7e8256900a81b597fba7b55089` |
| Router | S | `sha256:422d41413115ce46c24a063a018f942dfd63e04205b167d0b97e6e4d10660319` |
| Observer |51349be73b54ca2fb827a4becc30e00ba62acd7d| `sha256:d7761e08e8f9318d38d948f1b3ea916825762cec45e47ead5f85c7567b5f586f` |

Pinned bases remain Node 22 `de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d`
and Python 3.13 `93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5`.
Actual Codex 0.160.0/OpenCode 1.19.4/Git 2.39.5/pytest 8.4.1, Executor
Docker 20.10.24/Buildx 0.37.0/DDEV 1.25.4 match the retained recipe. 264 Runtime and 43
Executor shipped files matched content/executable bits. Offline probes proved
UID 1000, read-only root, noexec tmpfs and immutable executable askpass outside/tmp.
Actual worker binds remain nonrecursive, scoped credentials/env/resources unchanged.

The real `pcp_runtime` role passed nine-table/three-sequence rights; observer
read-role grants remain SELECT-only. No DDL/grant installation was needed.
Retained scoped publisher identity, repository push entitlement, PR/Actions/status
reads and authenticated Git ls-remote passed; PAT expiry remains2026-11-04T08:29:46Z.
Authoritative Codex account metadata reported available/12% remaining at observation;
this is dated quota evidence, not a guarantee of future capacity. No new login,
credential import, provider/model selection change or global network/trust change.

## First-start binding failure and exact PM disposition

The accepted packet captured complete configuration fingerprints after Docker
create, before start. On actual daemon 28.1.1/cgroupfs/cgroupv2, first start changed
`HostConfig.OomKillDisable` from JSON false to JSON null for the new Runtime/Executor.
Docker 20 inside Executor observed the same change. Aggregate readiness failed with
`claim_recovery_container_changed` **before registration**. Router already had null.
No key was missing; no true value or other drift was accepted. The isolated probe
reproduced the transition and showed stable full config on restart. A proposed
probe-only `docker update --oom-kill-disable=false` was rejected as an unknown flag;
no worker configuration update was attempted. No OOM stress test occurred.

Daemon metadata reported memory/swap/PID limits supported and OomKillDisable=false;
owned containers reported OOMKilled=false. This is compatible with unsupported
optional-field normalization, but does not prove the daemon's exact internal cause.
The first permit was retained, workers stopped and PM asked for the reserved
binding decision; no expected hash was silently refreshed.

PM6500237978 then authorized exactly one successor. The operator used production
`configuration_digest`, reproduced old hashes from original snapshots, compared
all Name/Config/HostConfig/Mounts fields with only mount-list sorting, and obtained
two identical current snapshots. Memory/swap/CPU/PIDs/OomScoreAdj/UID/read-only/
capabilities/security/mounts/restart/ports/env and exact IDs/images/names/labels/
network/registry all remained unchanged. DB/remote no-side-effect checks passed.

| Role / exact unchanged ID | Original config SHA256 | Successor config SHA256 |
| --- | --- | --- |
| Runtime `d6fb53f17809e9b11a0e82ecadd1e7c250c8183d84305645c66557cfea6fd285` | `c3145ccd6ce7a2ef970b596f431afc006580e207e8ac78743c550e8799a890b9` | `37c9c4b364222cc07ff68307a2032eae8d30efb6bce64c624469aa824520d670` |
| Executor `403553246e43f86b5b38918f3a287d26165654c3919dc5ae5be7543266d269fb` | `fd0457bdcadf564b5523ac15cbe5175ddadffaa041b4fde0c8af92aa2b8f604c` | `93a4b121c8ca8f06003ee38c6f0e30e3bba5e7d4015a1af012fc1f495787e1ad` |
| Router `f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6` | `f7fd0acc9ce7eb78f36bf4afb13c8ac051640411e542b4ce3037c51a5a4da5ee` | unchanged |

Successor decision `PCP-831-RECOVERY832-OOM-BINDING-V2`, execution_record6500237978.
Only that decision/record and the two authorized full hashes changed. Atomic
installation used a private 0600 temporary file, fsync and rename; complete diff
was validated. Original **not_before 2026-10-29T14:49:39.238744Z and
expires_at 2026-10-30T14:49:39.238744Z stayed exact**, with no new 24h allowance.
The original activation expiry 2026-10-30T10:51:28.134568Z stayed disabled/unchanged.
The earlier local proposal for a fresh validity window was superseded and never applied.

## Real registration, execution, proof and delivery

After restarting the SAME IDs, full fingerprints remained exact. Aggregate
readiness returned ready=true; all eight trusted readers passed; actual Executor
recovery preflight returned side_effects=absent. Plan was unregistered.
One registration created the deterministic queued job/event/audit atomically;
full original receipt stayed claimed/gen1, no lease/workspace/model/tests.
Full registered preimage matched its durable audit; read-only plan returned
registered_not_started. No duplicate registration was needed.

One execute consumed the running/gen2 fence and acquired same-job lease gen1.
One `codex_gpt6_luna` / gpt-6-luna / low coding invocation returned successfully.
No model replay, second coding turn, delivery retry, run-once or SQL repair occurred.
Actual verifier S targeted and configured-full phases each executed 13 tests,
**26 passed/0 failed/0 skipped,2 test runs**. These configured phases both target
the #831 test file; they are not the repository-wide hosted suites below.

Verifier containers `7b85a82af75a085b2f7042714e2653283a201a4f04aa34f08593d847cadc2f03`
and `92858c0eabcbd8c9793b9e3e5d1b0f85ed3e9775fcd92eb270e23ad4ddfd583c`
are retained exited 0. Actual image S, networknone, UID 1000, read-only snapshot,
NonRecursive=true and ReadOnlyNonRecursive=true, all capabilities dropped,
no-new-privileges,1.5CPU/1GiB/no swap/PID 256 were verified. The accepted verifier
tmpfs declaration is `rw,nosuid,nodev,size=268435456,mode=1777`; effective noexec in
those already-consumed containers was NOT TESTED. Separate image noexec probes
passed. An overly strict operator audit assertion was corrected to the accepted
recipe; tests/containers/proof were not rerun or changed.

Read-only production `reconcile_commit` revalidated all 639 file entries/modes,
clean worktree, exact cumulative diff and **sole parent S**. Commit
`4161ba059002c7aaf3fd35a88e3b0b80065c62b7`, tree
`5098a5b31eb096e483b35089561a1b55bca096b1`, diff SHA256
`0efad36fdb8fb8797c46339dbbde33d46f7c01cbe6ed96574ccaaaa9ffb5933f`.
Only the original three allowed paths changed; author/committer PCP Local.

One publisher attempt created branch `ai/a8851f89dd3e` and Draft PR #833. Remote
branch/PR head matched the exact commit; all-state PR lookup found one PR.
[Hosted40898352672](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40898352672)
at that exact head actually executed:

| Suite/job | Result |
| --- | --- |
| structure / 123533528504 |1754 passed/1 skipped |
| Runtime / 123533528881 |2571 passed/165 skipped |
| Executor / 123533528990 |797 passed |
| Router / 123533529280 |132 passed |

Total **5254 passed/166 skipped**; skipped integrations are not live evidence.
Runtime recorded ci_success and awaiting_independent_pm_review. One model call,
two test runs, one delivery attempt; input cache-miss 34886/output 3482,
gross 271430/cached 236544. Reported provider cost is **Unknown**; estimated cost 0.
Tool-call observation is Unknown. Stored legacy zero/default progress flags are
not substituted for actual verification/diff/usage provenance. Receipt/lease
stay running/gen2 / active/gen1 until legitimate independent PM finalization.

## Dashboard, retention and next checkpoint

**https://localhost:18443/dashboard — loopback_readonly, no login/token/cookie.**
Actual job transitions queued/executing/delivering/blocked and PR/CI are visible.
Fresh Chromium used normal TLS verification: 352 HTTP 200 snapshot responses, no
form/cookie/page error; offline/reload/reconnect passed after workers stopped.
Verified execution duration 67.801641624s stayed fixed across 123.677s observations;
observation age continued changing separately. Token coverage is complete; reported
cost Unknown, estimate 0, tool calls Unknown. Terminal completed/failed/cancelled
states were not fabricated. Current connectivity passed actual account/GitHub/
service/HTTPS requests; VPN state was not reconfirmed. VPN ON/parity and a true
second-machine LAN test remain NOT TESTED.

Private evidence root `/home/sonvh/.local/state/pcp-recovery832-live-v1` contains
full original/registered/fenced/final DB snapshots, consistent dumps/listings,
create/build/inspect receipts, original and successor permit audit, browser
snapshots/screenshots, Git bundle, CI receipts and SESSION.md. No secrets or full
private manifest is attached to this PR.

| Retained artifact | SHA256 |
| --- | --- |
| Fresh before dump, 29082 bytes | `325509fd0855f7118c5158c7d0f52497b0b98c84d7e2e5f5b8b3bc9ca658bb17` |
| Final after dump, 86846 bytes | `20e1f5b1505bf15a6ba70c8397627afd437f82f57f7349ce993b92b8304e3ed4` |
| Final full rows/sequences | `340cc74e282235c77c740f55517c29f575390fc06cd1765a55f8c778f882395d` |
| Original permit bytes | `9133cf6a5995f019ccd3279c8f7fb452569b1961bf1406f28eadeaf3b042bc4a` |
| Original permit canonical | `d6b89b22f5afddefd19936426c22f02e758a27ec0483e0c46aaa66011ccee931` |
| V2 permit bytes | `083637a98ba1a63925181830e0b003d439188d86ccbb42393a627e154195c330` |
| V2 permit canonical | `3a098b1f7eb46d95ae7015857aa22f4cdaaaea7abc2428295504a820fd7a5e36` |
| Verified execution proof | `84e63889d00d513b60af55978a8b1088804bd6c9a2023c5f0e9e10a46ace210f` |
| Original registration audit | `567f72a9cdec3b28903e12e0263bc2516f81340178dfd2f349eb528ba2260763` |
| Final progress/counters | `07a21132ed7e1d8c9bf672fb3a95a903e0a16a31c9fc652a3262e53a1d05458e` |
| Job Git bundle | `2a7106d43b2a2598de1028f0072c38fab2915beec97d9d27075b52c9b0eb9e70` |

Both permit originals are retained under release `rollback/disabled-recovery-permit.json`
and `rollback/disabled-recovery-permit-v2.json`. Original activation stays disabled.
Final scoped shutdown changed no proof/result/counter/receipt/lease. 46 V4 containers
retained, 43 stopped. Only these exact resources remain running:

- DB `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8`.
- Observer `5d6b3e9b578745877f162f9c34e4413cc855a40a8c4281c32d3c6ed711b05411`.
- Frontend `d22a5bf0ef1adee16464c27ccab10bf3cf22dc7320fa65ed5a995fbd5ea4daf2`.

Network `4f39b2458e6bbb9cee83bcee01053d4022bc9e49aa4877f3815c1a1161d571d5`
and volume `pcp-local-adoption825-v4-postgres-data` unchanged. Stopped original S
Runtime f8d63b… and Executor cade4f… retain their full IDs/images under names
ending `-retained-S-<first8ID>`; Router retains its original ID. V3/#824, all
rollback assets and foreign resources were untouched. No prune/down-v/reset.

Next is **independent PM review of Draft PR #833 and this execution evidence**, then
an explicit eligible finalization/merge disposition. Keep main R while this
window remains in force. Do not execute again, call deliver on already-successful
publication, auto-release the lease or restore a dump over consumed ownership.
Any later startup/permit restoration must follow that disposition and recheck
the original expiry; no automatic permit chain. A future fresh task needs its
own approved immutable successor frame, final source/image bindings and legitimate
ownership resolution; this evidence does not activate a new baseline or task.

## Supported PM finalization — actual completed afterimages

[Decision6501364012](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6501364012)
accepted exact PR833 head4161ba059002c7aaf3fd35a88e3b0b80065c62b7 through structured
[review5700617139](https://github.com/sonvhse06072/personal-coding-platform/pull/833#pullrequestreview-5700617139).
This is independent ChatGPT PM review through the configured Owner account,
not cross-provider runtime attestation. Both PRs remain unmerged; main stays R.

PHYSICAL/PASS: full retained preimages matched; consistent private dump and full
row/sequence snapshot preceded mutation. Exact unchanged V2 bytes restored atomically
from the retained0600 copy. Same raw/canonical permit hashes and original expiry
2026-10-30T14:49:39.238744Z; original rejected permit/activation stayed disabled.
Same Runtime/Executor IDs/images/full configuration fingerprints were checked
before and after startup. Router never started. Finalization-specific health,
authority/registry/plan passed; verified workspace/PR were expected. No absent-workspace
fresh-admission preflight or subscription/model readiness was invoked. Health was
degraded with the deliberately stopped Router; Executor was ok and worker startup
authority allowed the supported plan/finalization endpoints.

LIVE/PASS: exactly one authenticated POST to internal Runtime8787
`/v1/pcp-local/pm-review`, using the six exact fields in the decision payload,
returned HTTP200. The shipped endpoint fetched actual structured review and latest
four-suite CI, then committed its transaction. Full afterimages—not HTTP alone—confirmed:

| Field | Before | After |
| --- | --- | --- |
| Same job | blocked/verified/awaiting_independent_pm_review | completed/verified; active error NULL |
| acceptance_phase / delivery_finalized | awaiting_independent_pm_review / false | pm_review_accepted / true |
| receipt | running/gen2 | delivered/gen3 |
| same-owner lease | active/gen1 | released/gen1 |
| review | pending | 5700617139, verdict pass |
| model / verifier / delivery counters | 1 / 2 / 1 | 1 / 2 / 1, entire progress unchanged |

Checkpoint including verified proof and original registration audit remains exact;
source/baseline/commit/tree/usage/history preserved. Original active error exists
in preimages/backups and was cleared only by normal finalization. Other receipt/
lease fields stayed exact except supported state/generation/update timestamps.
Unrelated tables/sequences unchanged except ordinary quota collector observations.
No transport ambiguity or second POST occurred. Zero additional coding, job test,
admission, execute, deliver or build calls; no permit renewal or manual SQL mutation.
Result eligibility has blockers=[], manual_only=true, eligible=false because
automatic PM merge is disabled; this is not permission for Developer merge.

LIVE/PASS: actual completed dashboard, terminal_outcome=completed, delivered/released
ownership, truthful unchanged usage/CI; default trusted Chromium TLS, no cookies/form/
page errors. Duration stayed67.80164162399888s across polls and offline/reload/reconnect;
activity age increased independently. Failed/cancelled states, VPN parity and
second-machine LAN remain NOT TESTED. Verifier noexec limitation above remains.

PHYSICAL/PASS: afterimages/dump captured; only same Runtime/Executor stopped again,
Router stayed stopped. Installed V2 moved intact to
`rollback/disabled-recovery-permit-v2-after-finalization.json`, original audit copy
retained. Proof/progress/ownership unchanged during shutdown.46 containers retained,
43 stopped; unchanged DB/observer/frontend only running, same exact IDs above.
All original images/workspaces/verifier containers/credentials/V3 assets retained.

| Finalization artifact | SHA256 |
| --- | --- |
| Consistent pre dump | `f2b5001794c5839f98a71191e843b8579ce8e8f8c7122045f3b1c30857dec614` |
| Consistent post dump | `b27467924e63e1484d231c9e24ad363029eb4cc7de941c45668b1f50da2f29a2` |
| Full pre rows/sequences | `340cc74e282235c77c740f55517c29f575390fc06cd1765a55f8c778f882395d` |
| Full final rows/sequences | `ae0955d513bbac055d0eb4a2c156804c26b094d9f313bfced22ebc53d9bf8406` |
| Unchanged complete checkpoint | `2b17a7ac27ca8ecc0cc6314e848b3c0fc919529f5287548a1eb4f80ae984498c` |
| Unchanged complete progress | `07a21132ed7e1d8c9bf672fb3a95a903e0a16a31c9fc652a3262e53a1d05458e` |
| Restored/disabled V2 bytes | `083637a98ba1a63925181830e0b003d439188d86ccbb42393a627e154195c330` |

Private exact payload/request/response, full before/afterimages, result eligibility,
dump listings, browser snapshots/screenshot and shutdown receipt are under the
same evidence root. Operator initially used system Python without the existing
FastAPI/Playwright dependencies; those import failures occurred before operations.
Using the retained validation venv resolved them without installs or application changes.

Next: ChatGPT PM confirms this after-state, closes stable-R hold, readies/merges
exact accepted833 and checks postmerge, then reviews/merges updated evidence834.
No new task/baseline activation or further worker action is authorized here.
