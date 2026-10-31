# Separate finite finalization authority — #835 SOURCE/FIXTURE

WorkOrder [6544621726](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6544621726).
One writer/branch `ai/835-finalization-authority-v1`, based on
X `ee7ea0d824bf8b2aa568cbc5d03b222fd74d0275`. Return at independent PM source review.
This source candidate grants no live installation, adoption, worker start, finalization,
repair, provider login/inference, merge or foreign-resource action.

## Engineering acceptance and preserved live state

Independent [review5723218707](https://github.com/sonvhse06072/personal-coding-platform/pull/850#pullrequestreview-5723218707)
accepts SAME Draft task850 head `9574d62d9a7d385deb107bc8108b4b6802132fa3`,
sole parent `cf41cad08434f930841ced57a773f35783a1f537`, tree
`ec77318b2a4a901877d49b6670b5410c1b7f149c`, producer diff
`902a91634b03cc946cff15a01c4ac1af55d69344f8c59a16b4e760d06a64eb22`.
Actual task CI41199954657 and evidence CI41201046117 executed all four suites PASS.
These historical runs are distinct from this source candidate's required final-head CI.
SAME [evidence847](https://github.com/sonvhse06072/personal-coding-platform/pull/847)
at `cac81324ee295fa9782ec42eadb16a0df9602643` retains the complete physical execution.
Neither PR is merged or changed by this source implementation.

Original job `15271df1a36b1281010465538a9318ae`: blocked/awaiting_independent_pm_review,
execution verified/delivery ci_success, finalized=false, receipt running/gen2,
lease active/gen4, durable counters **1/4/2**. Task/base/canonical/baseline/verifier
H `871fbf2485a1ffb89a88a69e1daaaca10e25b318` remains pinned. Original repair window
**2026-10-31T10:21:43Z–13:15:00Z** expired before independent review. It is never renewed.

Historical bytes remain unchanged:

| Artifact | SHA256 |
| --- | --- |
| Original preparation permit996eec62 | `996eec62bce1b329bef1fa51d3a25eabc5894a21168b1381167607bf7e84a86d` |
| Actually consumed derived repair permit | `13e8797fb63f40639d4181cf17033d479bdc4bda45e4dee1063ea4203e7af2fa` |
| Original sidecar | `dabbc24b6fae2216cec7eb74cfcb0864121fa61a1c43c30fa03f9da8efe2ee10` |
| Derived sidecar | `f668745248bd581fd734030927f2459b72f19d2206d3ea58ca97a2bf259ae339` |
| Original activation | `ec1d28f13f44d149001e1657b9122f3a1eb3947e966c3bebe5e99fcb59dbc665` |
| Exact1973B patch | `bf3a6c53cf8adce7dcc47b7c8ad4234884804a0d6ba9785e47fd61499166fffb` |
| Post-delivery742478B backup restored in this fixture | `e3406d6d40e7fe97af824e353161dddc45c61c9c8c9402b18f6384a5f7f954a9` |

Original/new proof epochs, original failed CI/result, request/audit digests, complete
checkpoint/history/usage/agent_attempts and counters stay intact. A/B/C rows/workspaces,
all54 custody nodes, unknown copies and retired824/V3 are preserved. Read-only live
comparison confirms the retained full job/receipt/lease afterimages and filesystem.

## Change and executable contract

X constructs a fresh repair Permit even for finalization. Extending that permit's expiry
would change the digest retained in every repair audit/request; the finalizer then rejects
its own history. The regression on X fails `local_repair_authority_expired` before mutation.

`HistoricalPermit` now validates private bytes, strict schema, original activation/patch,
task/release/provenance, original eligibility and immutable digest without issuing an
execution capability. It has no `require_fresh` execution method. `Permit` still requires
its original finite window, live flag and unchanged bytes for **every** repair operation.
No expired execution authority, clock change, generic bypass or expectation refresh exists.

The new private `/config/pcp-local-finalization.json` plus explicit
`PCP_LOCAL_FINALIZATION_ENABLED=owner-approved` is default OFF. Shipped configurations
enable neither. Runtime and Executor parse it independently using existing protected-file
custody and reject competing ordinary/source/worker/repair/claim/held flags. Only the
existing authenticated PM finalizer/read-only finalization readiness can consume it.
Repaired jobs now require this separate authority; even a fresh repair permit alone is
not finalization permission. Ordinary non-repair finalization retains its existing flow.

Exact top-level schema (version1, extra/duplicate fields rejected):

```text
version, decision_id, execution_record, not_before, expires_at,
original_repair_raw_sha256, original_repair_digest,
before={job,receipt,lease}, workspace_sha256, expected_head, diff_hash, pr_number,
review={id,body_sha256,ci_run_id},
repair_source, repair_commits, repair_paths,
roles={runtime,executor,router,verifier},
resources={worker_ids={runtime,executor,router},
           database={container_id,image_id,configuration_sha256},
           network_id,observer_binding_sha256}
```

`before` contains **complete latest afterimages**, including all retained original/new
proof/history/usage; equality is canonical and type-sensitive. `workspace_sha256` binds
the complete descriptor-safe filesystem snapshot. Runtime/Executor roles bind exact new
accepted platform release/images/configs; verifier remains H. Router reuse requires the
entire Router/model/policy input history unchanged. `resources` binds full stable IDs,
DB image/config, network and unchanged original observer/frontend binding. The finalization
release reuses existing ancestry/full-history/path validation and rejects any pilot-path
change. Runtime/Executor must run only under a later approved adoption; Router must stay
OFF for this finalization-only phase. No discovery or name-only identity exception.

Authority has its **own independently approved finite window**, maximum24h, current
not-before, no artificial future wait/auto-renewal. Freshness and exact private bytes are
rechecked after remote/Git work and immediately before CAS. Original repair/activation/
patch files are historical inputs only, never rewritten/re-digested to fit new evidence.
HTTP carries existing exact task/head/branch/baseline/PR/review identities only; it cannot
supply a permit, window, rows, resource bindings, patch or commands.

The existing shared project/operation locks and full-row job/receipt/lease CAS perform
one atomic finalization. Under the locks, Runtime re-reads Executor's actual GitHub
review body/author/head and required executed four-suite CI, exact resource/release/
observer bindings, then rechecks Git/candidate, full rows and revocation before DML.
Unknown/stale evidence rejects; counters never reset. Only normal result acceptance,
receipt delivered/gen3 and lease released/same-gen4 change. Entire checkpoint/progress
remain equal. A separate result audit binds finalization decision/digest and completion
postimage digest; exact acknowledged retries validate the retained completion read-only.
Lost acknowledgement uses the existing one-POST session status reconciliation. No blind
retry, duplicate mutation, repaired-work publication or execution replay.

Affected source paths are the two local finalization modules, existing historical permit
parsers, trusted readers/startup, PM endpoint, delivery finalizer/readiness and release
binding. Runtime inspection packaging includes the new literal module; the draft ignore
hash and exact archive/oracle counts follow it. No CLI/base/dependency/security-policy/
baseline/Constitution/CI workflow change or physical image build occurred.

## Verification and fixture preservation

Real Git/PostgreSQL regressions exercise expired repair with absent/disabled/expired/
revoked/wrong authority; exact fresh finalization; changed raw/canonical historical digest,
history/proof/head/diff/review/CI/role/resource/lease/receipt/full rows/usage/workspace;
late revocation/expiry/Git/remote drift; shared operation lock, concurrent exact requests,
transaction rollback, uncertain COMMIT acknowledgement and conflicting completed retries.
Expired/finalization-only authority cannot reach source/admission/repair/model/test/commit/
publication. Executor tests use real release Git ranges and private files with explicit
synthetic Docker/GitHub responses; real endpoint parsing demands all four executed steps.

The isolated post-delivery restore uses **the actual expired permit13e8797f unchanged**,
its actual original activation/patch and the original848 job/proof/history. No fixture
metadata re-attestation, epoch/request rewrite or permit resealing is needed. A private
workspace copy at the original namespace plus PostgreSQL17 restore exercises actual Git,
authenticated ASGI readiness/PM endpoint and atomic ownership transaction. The real accepted
review5723218707 body is retained, but Executor/GitHub/resource responses remain explicitly
**synthetic FIXTURE**, not fresh live validation. Source is an overlay on existing X image;
this is not adoption/build evidence. Copied result: completed/delivered3/released4,1/4/2;
checkpoint/progress/workspace/expired bytes/siblings equal, no execution sentinel reached.
Live848 remains awaiting PM/finalized=false.

Private evidence `/home/sonvh/.local/state/pcp848-finalization-source-v1` (0700) retains
RED/GREEN logs, restored full before/after rows, original-copy manifests, private authority,
backup, actual review bytes, source-overlay container and exact resource receipt.
[Sanitized receipt and hashes](2026-10-31-finalization-authority848.json) records final checks
and fixture shutdown. Initial diagnostics/corrections remain logs, never reclassified PASS.

Two historical optional PostgreSQL supervision failures remain out of scope:
`test_initial_supervised_hold_rejects_mutated_ready_set` (unsupported continuation_key),
`test_pr_acceptance_does_not_hold_but_durable_merge_does` (initial released checkpoint).
They were reproduced against their anchor in the accepted prior report. Hosted CI skips
optional DSNs; neither this report nor CI claims these residuals fixed. An obsolete broad
optional-PG diagnostic was interrupted after focused work advanced; its partial failures
are not an accepted full-suite result. Required suites and scoped real-PG results are
recorded separately. No unrelated orchestration repair is included.

## One future adoption/finalization packet — NOT execution permission

1. Independent PM reviews this ONE Draft source PR, complete diff, regressions, restored
   evidence and **actual final-source-head four-suite CI**. PM owns source acceptance/
   eligible merge; operator does not merge. Keep task850/evidence847 unmerged. A later
   source merge/postmerge CI establishes candidate release Y, not activation permission.
2. A **separate concrete finite execution decision** must select Y, full reviewed H..Y
   range/paths, unchanged task H/head9574/diff/review5723218707/task CI41199954657 and
   retained original permit13e8797f/activation/patch, plus latest full afterimages. Do not
   extend the expired13:15Z window, mutate original historical files or refresh drift.
3. Under that future decision only: consistent private backup, restored-copy rehearsal,
   quiescent original workers and exact inventory; serial accepted Runtime/Executor builds
   from Y using existing reviewed pins. Validate actual packaged paths/modes/toolchain,
   image labels/non-root/security/nonrecursive mounts/noexec, source+release Git ranges.
   Reuse H verifier and truthful RouterS/observerN unchanged; no source/task/baseline swap.
4. Prepare only decision-selected successors, preserve every predecessor and existing
   limits/mounts/credentials/DNS/network. Set only finalization flag in Runtime/Executor;
   ordinary/source/worker/repair/claim/held/inference flags OFF. Keep Router stopped.
   Record stable full IDs/configuration digests AFTER any authorized missing-permit cold
   rejection, reject all unapproved drift. Independently select these bindings before
   installing authority; do not manufacture actual IDs in this SOURCE packet.
5. Prepare one separately named **UNINSTALLED** finalization file with the exact schema
   above, own reviewed current finite window and complete latest rows/workspace snapshot.
   Bind original expired raw/canonical13e8797f, review ID/body hash/task CI, H/Y roles,
   DB/network/observer+frontend and stable successors. Both production parsers and release
   validator must PASS offline. Publish exact bytes/hash/deltas for PM's execution selection.
   The original activation/repair/patch bytes may be mounted only as inert historical
   evidence under finalization-only mode and only when that future decision explicitly
   authorizes it. No repair flag, renewal or reuse of old execution permission.
6. Privately install only selected files with no-overwrite0600 under one fail-closed
   process after fresh original full-row/workspace/custody/ABC/unknown-copy/config checks.
   Start only exact approved Runtime/Executor under finite authority. No Router, discovery,
   login, quota/model probe, ordinary activation, admission, verification or publication.
7. One aggregate read-only finalization dry-run inventories: schema role, private finite
   authority/revocation, historical integrity, full afterimages/ownership, baseline/policy,
   latest proof/workspace, exact release/resources/observer, actual review/head/four-suite CI.
   Only actual PASS plus that execution decision permits **one** existing session finalize.
   Any extra drift/unknown is STOP with read-only reconciliation, never expectation refresh.
8. Read-only status proves completed/PM accepted, original checkpoint/progress and1/4/2,
   delivered3/released4; preserve full afterimages/consistent backup and dashboard evidence.
   On delivery, blocker or new expiry stop exact owned workers and disable new authority
   intact; preserve DB/observer/HTTPS and all predecessors. No automatic merge/next task.

```sh
# FUTURE reviewed/adopted release and independently selected finite authority only.
# These commands are NOT run against live848 in this SOURCE WorkOrder.
scripts/pcp-local-session.sh FULL_APPROVED_RUNTIME_ID readiness \
  --job-id 15271df1a36b1281010465538a9318ae --phase finalization \
  --review-id 5723218707 --json
scripts/pcp-local-session.sh FULL_APPROVED_RUNTIME_ID finalize \
  --job-id 15271df1a36b1281010465538a9318ae --review-id 5723218707 --json
scripts/pcp-local-session.sh FULL_APPROVED_RUNTIME_ID status \
  --job-id 15271df1a36b1281010465538a9318ae --json
```

The existing session sends at most one POST then reconciles status even after lost
acknowledgement. Do not automatically run it again after an unknown result. A read-only
status after authority disablement remains available through the accepted observer.

Before mutation, rollback means disable the new file and stop only selected successors,
retaining originals/DB. An uncertain finalization result requires read-only full-row/status
reconciliation; never restore a pre-finalization backup over live state or rewind ownership.
An acknowledged completion is durable and must never be undone by restoring old authority.

## Exact retained live resources — no adoption performed here

| Role | Full container ID | Configuration SHA256 |
| --- | --- | --- |
| OFF RuntimeX | `2933e0bc750854c21e3ff8353c6c68b76c6215339ad6666df594f8240b7b0b0e` | `2af1422999dd5405b8840715ab452285a54f44249dd4fb4ce914f7e1d1061748` |
| OFF ExecutorX | `14c608a23d473029c3dde440475453088141204f2b661fae1fc66e66f0874dc7` | `4feea261766aa6e196fd56dab96ae446bf3f901b2a3fdb901a787d08c2206959` |
| OFF RouterS | `f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6` | `f7fd0acc9ce7eb78f36bf4afb13c8ac051640411e542b4ce3037c51a5a4da5ee` |
| OFF predecessor (source config before permitted retention rename) | `a546d6e5c4e3f5b19ae54147159f07317cdd8207516ab77fa582026adda209e4` | `0e8b155edb01ad14b3053f027f74f38b83d351186d92b9998a72ec4fdf8032af` |

RuntimeX image `sha256:102d316d3d38d4e0608c2ce663f0d3d07e32ee034819f821be32f33ced872815`;
ExecutorX `sha256:4c54043a8c304ecea62147300bc3321cd0325e19c1ccb4080a85a28364bea851`;
H verifier `sha256:d9f553ac9a3376b33f0343f3f5ad014689ed383107ca64ceefd85a4a6f6c9d3b`.
Running DB `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8`,
N observer `da6c434797c46a3312f0ca185b20e0b5fbb9234ce137aee9f81ebc2fb9241660`,
HTTPS `601c552bd0562b947529a591b84c70570a1eaa556fb43e50a8c2ae0d76e362aa`.
Network `4f39b2458e6bbb9cee83bcee01053d4022bc9e49aa4877f3815c1a1161d571d5`,
PG volume `pcp-local-adoption825-v4-postgres-data`. Dashboard https://localhost:18443/dashboard.

These IDs identify retained X resources, not future Y successors. None is started,
replaced or reconfigured by this source WorkOrder. Private artifacts/backups remain intact.
Operator source/fixture/CI elapsed time and costs are separate from original PCP counters.
Requested operator effort high; actual exposed effort/tokens/cost/Owner active minutes
Unknown. Additional Owner requests0, PCP-managed model/login/admission/live finalization/
merge0, subagents0. No unattended-operation, benchmark, VPN parity or live release claim.

## Final source verification and scoped stop receipt

- RED on X: finalization rejected `local_repair_authority_expired`, no mutation.
- GREEN real-PG finalization/repair/operator **99 PASS90.69s**; ordinary lifecycle/
  dispatch/consolidation compatibility **326 PASS98.43s**. Separate Executor real Git/
  private-release/PM transport selection **86 PASS2.05s**, including canonical H drift.
- Required local suites: root **1761 PASS19.42s**, Router **132 PASS3.29s**,
  Runtime **2790 PASS/458 optional skips86.22s**, Executor **866 PASS24.28s**.
  Literal source packaging **109 PASS1.93s**; original524-case oracle unchanged.
- An overlapping obsolete all-PG diagnostic caused two `held_operation_busy` setup errors
  in an earlier97-pass focused run. The guards held; the obsolete scan was interrupted,
  then the complete final99-case selection ran serially PASS. No expectation/guard change.
- Final restored rehearsal container
  `a89e0d01301df31347961307c9e809133e7079f5a0ac146503c554be54d68826` exited0.
  Earlier successful source-overlay fixture
  `dac1483f70c2f8e5b5f3bcfc53a45742dcec512db499e475aade7469d8e4dd13` exited0.
  Both are network-none/non-root/read-only X image with explicit candidate source overlay,
  read-only copied workspaces and no socket/service/provider/publisher credentials.
- At **2026-10-31T15:09:40Z**, all owned Docker fixtures were OFF and the exact private
  native PostgreSQL17 cluster was stopped. Its data directory, both restored DBs, before/
  after dumps, workspace copies, fixture authority and logs remain retained. Live worker
  config/image fingerprints, original rows/workspaces/ABC/all54 custody/unknown-copy hashes
  were rechecked unchanged; original workers OFF, DB/observer/HTTPS ON, authority absent.

Reproduction commands (SOURCE checkout; test DSN must point to a newly created owned,
private disposable cluster, never the installed DB):

```sh
# Run in a child process, using the existing venv and service CWD.
(cd services/runtime && PCP_CHECKPOINT_TEST_DSN="$DISPOSABLE_FIXTURE_DSN" \
  PYTHONDONTWRITEBYTECODE=1 /home/sonvh/.venvs/pcp-g1-t02-review/bin/python -B \
  -m pytest -q -p no:cacheprovider tests/test_pcp_local_finalization.py \
  tests/test_pcp_local_review_repair.py tests/test_pcp_local_review_repair_operator.py)
(cd services/ddev-executor && PYTHONDONTWRITEBYTECODE=1 \
  /home/sonvh/.venvs/pcp-g1-t02-review/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_pcp_local_finalization.py tests/test_pcp_local_review_repair.py \
  tests/test_pcp_local_claim_recovery.py)
# Exact private cluster stop, already executed; never stop an unrelated cluster.
/usr/lib/postgresql/17/bin/pg_ctl \
  -D /home/sonvh/.local/state/pcp848-finalization-source-v1/pgdata -m fast stop
```

Do not restart the retained source fixtures merely to repeat a passed check. Reproduction
uses a fresh isolated restore/test identity if later source changes justify it. Final-head
hosted CI and source PR metadata are recorded after commit in that PR and private CI receipt;
no self-referential source hash or claimed future PASS is embedded here.
