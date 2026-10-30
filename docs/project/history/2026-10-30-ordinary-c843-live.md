# Ordinary C843 — N adoption and LIVE delivery

Date: 2026-10-30. Authority: [WO6526365770](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6526365770).
Accepted N `85e415f1f53c8129056e2f04fb99a9b964b89609` (merged PR842), four executed postmerge suites
[41078980568](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/41078980568).
One operator/writer; evidence branch `ai/835-ordinary-c-n-live`.
Session **15:23:19Z–23:23:19Z**, recorded before operational mutation; no renewal.
[Draft evidence PR845](https://github.com/sonvhse06072/personal-coding-platform/pull/845)
supplies its exact final head and required CI separately.

## Outcome and exact identities

The ordinary task reached a real Draft [PR844](https://github.com/sonvhse06072/personal-coding-platform/pull/844),
head **871e50454faf37a0e1b551c8d2981d22ad57f797**, branch `ai/4d0f1df36be0`.
[Exact-head CI41083619406](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/41083619406)
executed all four suites: root **1758 passed /1 skipped**, Runtime **2734 /321 skipped**,
Executor **808**, Router **132**. These were actual test steps, not skipped service jobs.
Independent PM review/finalization is pending. Developer did not approve or merge.

- Fresh [issue843](https://github.com/sonvhse06072/personal-coding-platform/issues/843),
  exactly three allowed evidence-summary script/test/document paths. PCP produced
  duplicate-member rejection and raw JSON regressions; the operator did not implement C.
- Production-derived job `4d0f1df36be0b9b971c18b04af870950`.
- Body SHA256 `7276b8d3c191a1366708c199bac211341548af0ffd06dc1b1157bc895102172f`;
  goal SHA256 `afa31d81e63b383cbf3a1191d6d8ab3236c4a2af6db1a5f3d321a666ecc6c17d`.
- Immutable local baseline `pcp-local-ordinary-c-85e415f1f53c-20261030`;
  canonical/task/verifier N. Old revision definitions remain byte-identical.
- Durable state **blocked / awaiting_independent_pm_review**, execution **verified**,
  delivery **ci_success**, `delivery_finalized=false`; receipt **running/gen2**,
  project lease **active/gen3**. This is honest pending acceptance, not completion.
- Counters **1 model /2 mandatory test phases /1 delivery**, no repair/replay.
  Both mandatory phases actually ran **17 tests**,34 total. The supported run-once
  request returned an acknowledged response. No duplicate POST/publication was sent.
- Supported delivery readiness has no dependency blockers, proof/ownership/publisher
  checks PASS, operation `awaiting_pm_review`, eligible=false. Its nonzero CLI exit
  correctly prevents republishing; finalization requires the independent review.

A831 and B837 complete job rows, receipts, proof, usage, counters1/2/1 and original
workspace byte/metadata snapshots remain unchanged. Earlier events remain present.
The shared project lease legitimately advanced from B's released/gen2 to C's active/gen3;
B's historical release evidence is retained. Retired824/V3 was not touched. Original
workers/images, old canonical Q, credentials, earlier quarantines and disabled permits
are retained; no old permit was restored. Main remains N.

## Evidence by class

| Class | Result | Actually exercised |
| --- | --- | --- |
| SOURCE | PASS | Exact N clean detached service archive and pinned build recipe; complete Executor/Router relevant input history unchanged, packaged hashes/modes match N inputs. No application repair in this evidence PR |
| FIXTURE | PASS | Consistent live backup restored into new isolated PG17.11; all11 public tables/3 sequences identical. Scoped real Runtime role grants pass. Copied A/B proofs validated in built N image against restored rows, no inference |
| PHYSICAL | PASS | New Runtime/verifier image, no source overlay; pinned CLI lifecycle RED/retained rejection/GREEN/repeat/next, read isolation, real Executor sparse producer -> N validator; actual verifier13 tests, read-only/nonrecursive mount, effective noexec; immutable executable askpass outside tmpfs |
| PHYSICAL | PASS | Actual original A/B read-only inspection with restored DB, nested snapshots under unchanged Runtime2CPU/3GiB/256pids/256MiB noexec tmpfs;0.928403s, peak103866368B. Restored-copy check0.809571s/105472000B. A/B file bytes13959138/14401234; Engine backing free about865.86GB at measurement |
| LIVE | PASS | Exact config archive, fresh baseline and same-instance worker/observer adoption; actual scoped publisher entitlement/quota, schema/peers/stable fingerprints, aggregate readiness and all eight production readers; ordinary843 admission, one developer, mandatory verification, Draft PR, hosted CI |
| LIVE | PASS | Trusted browser HTTPS, tokenless local observer, A/B assisted=true and fixed67.801642/47.582929s timers; C assisted=false, actual usage and PM wait; polling/offline/reconnect, no login/cookies/forms, mutation/foreign routes denied; ownership unchanged by observer |
| LIVE | PENDING | Independent PM acceptance/finalization, delivered/gen3 and released/gen3. These were deliberately not performed |
| NOT TESTED | — | VPN ON/OFF parity, LAN/remote access, future task D, direct-Codex comparison, unattended operation or benchmark. #595 remains HOLD |

Existing unrelated optional PostgreSQL failures remain tracked in the
[accepted source WorkReport](2026-10-30-ordinary-next-task.md); hosted321 skips do
not resolve them. No full optional-PG green claim is made. This restored-copy check
used real PG, not mocked database evidence; external inference was absent in fixtures.

## Source, images and resource custody

Only Runtime/verifier needed a serial build. Existing base/toolchain pins were used:
Codex0.160.0/OpenCode1.19.4; actual Runtime Python3.11.2, Node22.23.4, Git2.39.5,
pytest8.4.1/PyYAML6.0.2. Executor keeps Docker20.10.24/DDEV1.25.4/buildx0.37.0.
Executor and Router images retain honest original source labels R2 and S.

| Role | Image | Binding |
| --- | --- | --- |
| Runtime/verifier/observer | `sha256:a925ddf0e4fe120889412b282af8556ba96dab05eb83f5f170303a5b66b5e536` | N |
| Executor | `sha256:78a752c0dbfc6bb9f4120660a0cba4ad6bc6dd1673b1240fd651597d6edf6aae` | R2 f02d9a14af33d9efeb99aa573d776aab3119dec1; unchanged complete inputs |
| Router | `sha256:422d41413115ce46c24a063a018f942dfd63e04205b167d0b97e6e4d10660319` | S b97ade581fecad4db2146258e5ca02c3902189e0; unchanged service/models/policy |
| Database | sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27 | retained PostgreSQL17.11 |
| HTTPS | sha256:552e7481ca93ffccd046aa658dbbed22caefbc09c66fa7cd247cbb90b8a5c609 | retained Nginx image/TLS/config boundaries |

Private release: `/home/sonvh/pcp-local-adoption825-v4/releases/ordinary-c-85e415f1f53c8129056e2f04fb99a9b964b89609`. Old Q canonical is retained at
`rollback/canonical-Q-e3b19700` with bundle/filesystem archive and manifest.
New worker containers remove held/claim recovery switches; original old containers
remain stopped. Missing-ordinary-authority startup failed before DB work as required.
Only measured first-start `OomKillDisable false -> null` normalization occurred;
stable post-start fingerprints were frozen before fresh activation, not refreshed
to waive later drift. Non-root/read-only/resource/nonrecursive/tmpfs guards remain.

The exact legacy config hash323b12e7fb0dce3cf5c4984aebf7dc513e89b9bf3991ac227dbc275716af10fc
(118B,0600,uid1000) was renamed once with `renameat2(RENAME_NOREPLACE)` and directory
fsync to `rollback/legacy-B-config-323b12e7.toml`. Bytes/inode/owner/mode/atime/mtime
remain; rename ctime and parent-directory deltas are explicitly recorded. Auth assets
were unchanged by archival; no new login/credential issuance was needed. The clean
provider home did not recreate config through account checks or C execution. Never
archive a new config automatically. Restore only with stopped writers and absent destination.

## Timing, usage and operating limitations

Session start15:23:19Z; executable-dispatch intent15:43:17.921751Z; acknowledged
response15:47:38.481322Z; workers stopped/authority disabled at15:51:47.230121Z.
Setup/build/archive precede executable dispatch and are separate from task latency.
The private stage ledger retains both UTC and same-process monotonic measurements.
Run-once driver measured236.207094s including its final custody checks; UTC intent
to response is260.559571s. These distinct clock measurements are preserved without
normalizing the difference or attributing an unmeasured cause. Independent-acceptance
wall time remains open. Durable developer execution was64.303379s; hosted CI ran
15:45:22Z–15:47:35Z. Do not add overlapping intervals as a total.

Observed tokens: gross input468637, cached430848, net input37789, output3933.
Reported monetary cost is **Unknown**, provenance=false, despite normalization's
zero field; estimated cost is0.0 and is labeled estimated. Subscription-only policy
and cash ceiling0 remained; no paid fallback was enabled. Tool count is Unknown in
the dashboard, not a claimed zero. One returned developer invocation is observed.

Interactive Owner requests during this session:0; Owner active minutes **Unknown**.
This required substantial operator preparation/observation and is not unattended
operation. Routine harness corrections were diagnosed with retained evidence:
PG init completed but bootstrap client used the wrong Unix socket (same fixture
resumed without reset); JSON tuple/list comparison; added retained-next CLI output;
dashboard `id` collector field (exact rollback, then same-container readoption).
Delivery-readiness nonzero was the intended PM gate. No application guard was weakened.
The developer's prose still referenced the immutable source packet's pre-adoption
wording; durable Runtime verification/CI supersede that prose. Legacy progress
booleans are not substituted for the authoritative verification checkpoint.

## Hashes, private evidence and final retention

Private evidence root: `/home/sonvh/.local/state/pcp-ordinary-c-n-live-v1`. Full manifests, DB dumps, auth/env and preimages
remain local. Only sanitized identities/digests are published.

| Artifact | SHA256 |
| --- | --- |
| Before backup174965B | `6f3dc6cecd664745a0a2c960fb07bc0d9b3a245d3a9383bc6c5d0e02d0a7dfdd` |
| After shutdown backup227744B | `954ba6b3b2e23353c2271de622ccda063c10033bd3c6fc76111019371e0ed71b` |
| Fresh ordinary activation bytes, disabled intact | `9e4c8b0da409fa91befd448ddbe53c9c00bc4fa08c403ff0a4ee2c4f0e52407c` |
| Activation manifest | `5762ce2a1eb5620a0f203fc8d9d878469aae62074fe71b4394e47af6bb3c69d9` |
| Dispatch manifest | `477e056e7665db4c09eb7356baa2fb9eedac2abc0b5f9464540c70f8e317a769` |
| Finalization afterimage manifest | `c6e2d80f10b2737ef1dd078bfc63689db7fd57660b6fbff86cf15dbf01c3084e` |
| Config archival receipt | `45adb46b24523af8ea7ab0dae9314da8e79ca3a19d4fd2c2e15bd926a986b0b8` |

Runtime `f55b55ded4f2479214233244def8b34e9da36b93e057cdf4c3eda75149df7e14`, Executor `fc32fd0a0bf632a185aad7d83f21234988359a9d803f8dcc0be36145a9d93e1d` and Router
`f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6` are **stopped**. C remains reserved with its active/gen3 lease;
shutdown does not release ownership. Authority is intact at
`/home/sonvh/.local/state/pcp-ordinary-c-n-live-v1/disabled-authority/pcp-local-activation.json`, same expiry **2026-10-30T23:23:19Z**.

Running retained services:

- DB `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8`.
- N observer `da6c434797c46a3312f0ca185b20e0b5fbb9234ce137aee9f81ebc2fb9241660`.
- HTTPS frontend `601c552bd0562b947529a591b84c70570a1eaa556fb43e50a8c2ae0d76e362aa`.

**https://localhost:18443/dashboard** — open locally; no token, login or cookie.
Access remains loopback-only, read-only, using SELECT-only `pcp_dashboard_reader`.
No TLS errors were ignored and no cookies were injected. Old observer5d6b3e9b and
HTTPSd22a5bf0 are stopped rollback assets; original leaf certificate and Nginx allowlist
are unchanged. A bounded observer switch/rollback occurred during preparation;
current availability and post-shutdown HTTPS200 are verified.

Scoped worker stop (already executed; never prune/remove):

```sh
env -u DOCKER_CONTEXT -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  docker --host unix:///var/run/docker.sock stop \
  f55b55ded4f2479214233244def8b34e9da36b93e057cdf4c3eda75149df7e14 \
  fc32fd0a0bf632a185aad7d83f21234988359a9d803f8dcc0be36145a9d93e1d \
  f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6
```

All campaign fixtures below are stopped/exited; no fixture remains running.
PG volume `pcp-ordinary-c-n-rehearsal-pg-data` and private copied data/logs are retained.

| Fixture | Container ID |
| --- | --- |
| pcp-local-adoption825-v4-https-n-syntax | `e3943ce95ba629a69e0633bbdaf18c95cb74e9f26dd91307fb98641f01dbff36` |
| pcp-ordinary-c-n-retained-check | `d7377691910e6fd23c0e4aa97618a4a7005e11160a73aea75642d40ad9905d3c` |
| pcp-local-adoption825-v4-ordinary-c-n-verifier | `691dbe6290b0ef55a5abd09412cdacb7838baa85cc1f6013feaa0eded1abc2cb` |
| pcp-local-adoption825-v4-n-producer-proof | `22e3301e89d8fa834b688cb94e432694d5c0b34c923bcea964ca21d010b9fe77` |
| pcp-local-adoption825-v4-n-producer-workspace | `36172b76d8bd7ce05570397a9ad4197e0c3ea494af379efc30dc5ac8eef76edd` |
| pcp-local-adoption825-v4-n-producer-source | `e8e845669069a244fbf0484a8c24b292b183c1b14ea9eecf5a8646558f6f3625` |
| pcp-ordinary-c-n-restored-check | `040e9dae6d2d0acfbcadf3dedf5041dda3777c09297099ada569486184519ebf` |
| pcp-local-adoption825-v4-ordinary-c-n-config-lifecycle | `29d6d21a4b9208a96a1a0aa325579b44d3bae9203361199f04b29ea6414c46cf` |
| pcp-local-adoption825-v4-ordinary-c-n-isolation | `1dd6a8daf46c9d8dccbb104c2e2cc4ff55cb5a7c49b292b0f5faf4c6ac940df2` |
| pcp-local-adoption825-v4-ordinary-c-n-router-packaging | `3c97e98fc67dc67cf7597684d0c2d0405e9decfb69010c01fc989ae03b18786a` |
| pcp-local-adoption825-v4-ordinary-c-n-executor-packaging | `0e254d36844446daf4dd54f2c02c4115c10a76f5924bece7d9df1e2f394df66b` |
| pcp-local-adoption825-v4-ordinary-c-n-runtime-packaging | `cf785e0ea94d0eaff45540fb22f042b48b6f660eb5f32fc7c6ba7a29451c1da2` |
| pcp-ordinary-c-n-rehearsal-pg | `7322f0128313d0352a288ec23508257b9679a10b94b06dccff58f48d8cd08839` |

## Concrete next PM checkpoint and finalization packet

1. Independently review issue843, exact PR844 head871e50454faf37a0e1b551c8d2981d22ad57f797,
   its real verification/four-suite CI and this evidence PR. Keep main N and task/evidence
   PRs unmerged during finalization. PM owns acceptance, review identity and merge order.
2. Issue a finite non-model finalization decision naming the exact independent structured
   review ID, job, source/images/config and `finalization-manifest.private.json` digest
   above. Revalidate full post-shutdown DB/workspace/config afterimages and exact open
   task PR/head/CI. Original ordinary activation must be unchanged and unexpired.
   After23:23:19Z no automatic renewal/restoration is permitted; PM must resolve authority.
3. Under that later decision only, restore the exact disabled activation with no-overwrite
   rename into `/home/sonvh/pcp-local-adoption825-v4/instance/config/pcp-local-activation.json`,
   verify SHA256 above and fsync. No old claim/held permit. Start only Runtime/Executor
   IDs above as needed; finalization excludes provider, Router and fresh-admission work.
4. Use the accepted container-resident operator. These commands are preparation, not
   permission in this completed session; `PCP_PM_REVIEW_ID` must come from PM's decision:

```sh
(
  set -eu
  : "${PCP_PM_REVIEW_ID:?Exact independent accepted review ID required}"
  cd /home/sonvh/pcp-ordinary-c-n-live
  sh scripts/pcp-local-session.sh f55b55ded4f2479214233244def8b34e9da36b93e057cdf4c3eda75149df7e14 \
    readiness --job-id 4d0f1df36be0b9b971c18b04af870950 \
    --phase finalization --review-id "$PCP_PM_REVIEW_ID" --json
  # Only readiness success reaches the single supported finalization request.
  sh scripts/pcp-local-session.sh f55b55ded4f2479214233244def8b34e9da36b93e057cdf4c3eda75149df7e14 \
    finalize --job-id 4d0f1df36be0b9b971c18b04af870950 \
    --review-id "$PCP_PM_REVIEW_ID" --json
)
```

No `--apply` on finalize. Reconcile uncertain acknowledgement using supported status
and finalization readiness, never blind POST retry. Require completed/pm_review_accepted,
finalized=true, delivered/gen3, released/gen3 with unchanged proof/usage/counters1/2/1.
Capture backup/afterimages/browser terminal state; stop exact workers and disable
same authority intact. Preserve DB/observer/HTTPS and all history. No model/test/
delivery replay, task reset, new admission, rebuild or self-merge.

Rollback is scoped: retain old source/images/config/observer pair; never restore an
old DB over new ownership or reactivate an expired/consumed permit. Observer rollback
must restore its exact previous binding before any worker authority is enabled.
Legacy config restoration is an explicit stopped-writer/absent-destination operation,
not a workaround for a new guard failure. No global network/VPN/DNS change.

## Evidence PR validation

Local root verification: **1755 passed in19.67s**; stable continuity headings,
standing stop markers and the GitHub/Runtime reconciliation reminder are preserved.
Packet shell blocks passed syntax validation without executing later finalization.
`git diff --check` passed. The exact evidence-PR head/hosted results belong to the PR
receipt; task844's four-suite CI above is separate. No protected repository path or
application source was changed by this evidence branch.
