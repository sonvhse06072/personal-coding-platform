# Temporary artifacts and held848 — SOURCE/FIXTURE WorkReport

Authority: [WO6537270657](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6537270657).
Anchor H **871fbf2485a1ffb89a88a69e1daaaca10e25b318**; branch
`ai/835-temp-artifacts-held848-v1`. One writer, one [Draft source PR849](https://github.com/sonvhse06072/personal-coding-platform/pull/849). Exact head and
four executed hosted suites are recorded in that PR's checks/description, avoiding
a self-referential commit hash. Evidence [PR847](https://github.com/sonvhse06072/personal-coding-platform/pull/847)
remains unmerged at e97fa327596914e6d29644924f7f0e6f9cbf9dae.

## Outcome and preserved LIVE boundary

SOURCE adds a private temporary-output lifecycle and a separate exact-inventory
held continuation through the existing authenticated `verify-held`/CAS machinery.
FIXTURE demonstrates same copied848 verification, commit and synthetic delivery;
PHYSICAL demonstrates the pinned CLI/tool sandbox and H verifier in isolated containers.
There is **no live adoption or recovery**. No task848 implementation was written or
copied into this branch. Its existing candidate was read only for private backup and
restored-copy testing. No live login, model, worker start, permit installation or build.

Original848 job **15271df1a36b1281010465538a9318ae** remains blocked /
`pcp_local_changed_paths_denied`, held from invocation_returned: receipt running/gen2,
lease active/gen4, counters **1 model /0 mandatory phases /0 delivery**; no proof,
commit or task PR. Task/base/canonical/verifier H remain immutable. A831, B837 and C843
remain completed/accepted with their original proof, usage and counters1/2/1;
retired824, V3, credentials, both original configs, disabled authorities and evidence
are preserved. The final read-only audit compares the entire V4 DB/three sequences,
all 831 entries in848’s workspace and historical A/B/C bytes/metadata to retained preimages.
The original ordinary V2 expiry remains **2026-10-31T07:00:00Z**, without renewal.

https://localhost:18443/dashboard remains tokenless `loopback_readonly`, on the existing
N observer. Availability is rechecked with trusted HTTPS; no observer replacement.
Original workers remain stopped, V2 disabled intact and provider auth absent.

## Reproduction and smallest coherent repair

Actual accepted H Runtime image/CLI **0.160.0** with a credential-free local synthetic
SSE transport executes real `exec_command` and pytest. With H permissions, pytest
cannot use shared /tmp and falls back to cwd. Merely exporting TMPDIR in the outer CLI
still fails: the pinned profile's dynamic `:tmpdir` denial resolves from the child tool
environment. Actual cleanup rejection is CLI command policy (`rm -f style commands
are not permitted`), not Unix shell permission failure. No inference/provider traffic.

Runtime now records a unique creation intent, atomically creates a private0700 child
of the already writable job, records its inode identity, and passes child-only
TMPDIR/TMP/TEMP plus PYTHONDONTWRITEBYTECODE=1 through the actual adapter arguments.
PYTEST_ADDOPTS places the ordinary pytest cache in that same private child, including
paths with spaces; plain `python -m pytest` therefore needs no agent cleanup flags.
The profile omits the dynamic alias denial only for this validated private child;
root, shared /tmp, sibling/provider/config homes, .git, network and command-policy
boundaries remain. The actual pinned CLI confirms pytest writes there, including
when a tool attempts another working directory. No blanket /tmp permission, global
environment, CLI upgrade or command-policy workaround.

Returned-turn closure retains the complete original workspace and complete Git
candidate identity (including modes and full diff). A Runtime-created claim, or a
separately reviewed exact legacy inventory, identifies output; names/ignore rules/
on-disk markers never grant authority. Unknown files, tracked/staged output, forged
claims, external links, hard links, special files, source/index/config drift deny.
Approved internal output symlinks are preserved as links without opening targets.

Custody uses existing project serialization/full job-receipt-lease CAS: durable intent
precedes no-overwrite same-filesystem descriptor-relative renames; fsync and exact
source/destination partition reconciliation follow. Output is retained outside all
developer job boundaries at `.pcp-artifact-custody/<job>/<plan-sha>/<root-index>`.
There is no deletion or recursive-follow cleanup. Every namespace entry must match
a durable audit. Partial multi-root renames/lost acknowledgements reconcile against
the original inventory; a different candidate never becomes the new expectation.
Repair turns keep lossless audit history with SHA references instead of recursively
duplicating full histories. Counters/ownership never reset.

Legacy848 has **three** proposed exact roots: pytest-of-node (50 nodes),
scripts/__pycache__ (2), tests/__pycache__ (2): **54 nodes, 33 non-directories**.
The last two contain ignored bytecode missed by the original34-path Git projection.
The first restored rehearsal correctly denied them before any mutation. Their exact
bytes/metadata need independent PM inventory approval too; the implementation does
not classify them from filenames, extension or ignore status. Future bytecode is
prevented via the child environment; an explicitly overriding tool still fails scope.

A separate version2 artifact permit and opt-in preserve the old version1 config-error
permit unchanged. Eligibility requires the exact changed_paths_denied/returned class,
full original job/receipt/lease, successful durable returned checkpoint, original usage
and counters1/0/0. It binds the exact unverified candidate and full artifact/source
preimage. Original proof is absent until genuine mandatory H verification succeeds.
Unknown verification stays fenced; no adapter/model path is reachable. Existing commit,
publication, CI and PM review contracts remain authoritative. Runtime/Executor repairR
is explicitly distinct from task/baseline/verifierH. R is unknown until independent
acceptance; no P/Q-style source bypass or baseline rewrite.

Dependencies: adapter; worker private-claim/closure/retained-root validation; existing
recovery/readiness; Executor's exact release permit; one descriptor-safe helper.
Inspection packaging adds only that helper to the literal allowlist and updates its
**draft** fingerprint. Artifact/source pins remain unresolved; no live provenance changes.
Protected source dependencies declared for worker_loop, the literal inspection allowlist
and its draft image-provenance fingerprint.
No main-route, generic cleanup service, policy, pin, baseline or task solution change.

## Criteria and evidence matrix

| Criterion | Evidence | Outcome/boundary |
| --- | --- | --- |
| Pinned failure and future self-tests | Actual H image/CLI, real pytest, synthetic SSE; red/default versus green private child | PHYSICAL/FIXTURE PASS; no inference |
| Isolation/unsafe commands | Actual foreign cwd/read, sibling, provider, private custody, proc/shared tmp/network probes; rm policy refusal unchanged | PHYSICAL/FIXTURE PASS |
| Exact source versus output | Real Git; three-file candidate plus inventoried output accepted; extra/ignored/tracked tmp-named/source/index/config/hook drift denied | FIXTURE PASS |
| Hostile paths/races | No-follow/no-atime descriptor reads; external symlink/hardlink/special/traversal/forged claim; parent swap never reads foreign bytes | FIXTURE PASS |
| Custody durability | Real PostgreSQL full-row CAS; rollback, concurrent stale requests, partial rename, rename/DB/afterimage lost ack and drift | FIXTURE PASS; no double move/reset |
| Non-model continuation | Existing authenticated HTTP/readiness/verify-held and ordinary run-once fence; duplicate observe-only; unknown tests stay fenced | FIXTURE PASS |
| Mandatory tests/proof | Restored copy, accepted H verifier image and actual H mandatory runner: **19 targeted +19 full passed** | PHYSICAL/FIXTURE PASS; agent self-tests not reused |
| Commit/delivery | Real copied Git commit09e7dd0b9b45d584ddd600139659f08788ee68ad; original tree/diff preserved; actual review payload and synthetic publisher/CI; publication lost ack reconciled | FIXTURE PASS; no real task PR/hosted task CI |
| A/B/C + all readers | Actual producer/sparse Git → retained A → ordinary B, all eight readers, registrar, readiness and HTTP; copied historical A/B/C unchanged | FIXTURE PASS |
| Context/diagnostics | Actual invocation receives immutable task/context and diagnostic-driven repair; three healthy repair turns retain all custody audits | FIXTURE PASS; internal CLI compaction unproven |
| Original retained state | Read-only full DB/sequences and no-follow/no-atime workspace comparisons, stopped workers/disabled authority, HTTPS GET | LIVE preservation PASS; no live recovery |

Restored Git tree **b14a0bb25ef7bfb82609c87f88a1f0d37b63b95b**; source diff SHA256
**b7f49de89ffa98cf20f549a4cfdbfc8ce9263a995e23b484faa21e2264f685cf**.
These identify an **unverified original candidate** until copied mandatory verification;
they do not create original-job proof. Copied after-counters1/2/1, running2/active4,
model usage unchanged. Fixture role bindings are synthetic R/H; candidate source is an
explicit /tmp overlay of H image, not a built/adopted R image or release provenance.

Required local suites: root1761 (final scoped run20.54s), Router132, Executor815; final standard Runtime **2783 passed /366 skipped in87.84s**.
Final hosted counts in the PR checks are authoritative for Python3.13.
Focused Git/PostgreSQL/artifact/context73 and eight-reader/HTTP6 pass (overlap, not additive).
The broader optional PostgreSQL run initially found two stale adapter-argument assertions
in ordinary-cycle fixtures; those now assert the real recorded private temp and output.
Two **unrelated accepted-H supervision failures** reproduce on pristine H:
`test_initial_supervised_hold_rejects_mutated_ready_set` (continuation_key signature) and
`test_pr_acceptance_does_not_hold_but_durable_merge_does` (released projection).
They remain tracked, not hidden by changing unrelated production/tests. Final optional
run: **3146 passed /2 baseline failures in300.23s**; final adapter/ordinary/context
selection **44 passed62.17s**, plus the plain-pytest cache regression **1 passed0.30s**.
Four exact-head hosted results are attached to the PR; private logs retain all runs.

## Retained fixture evidence, resources and measurements

Private evidence root `/home/sonvh/.local/state/pcp848-temp-source-v1` (0700). Full
preimages, permits and logs stay private. Accepted existing backup **240271 bytes**, SHA256
**1f3fe522d2295117323d32eeb281a51651d06bc32ed93085a60ae06f36b5a029**,
restored into owned `pcp848_restore`. The initial full11-table/3-sequence state matches
the original shutdown projection exactly. Historical XML transport escapes and timestamp
precision are representational; new permit preimages must use production `read_rows/frozen`,
not XML strings. Neither mismatch nor projection reformats refreshed an expectation.

Owned containers, stopped and retained at closeout:

| Purpose | Full container ID |
| --- | --- |
| Pinned CLI probe | 6bfe00d7a8caf96ffa65ddef70acfd46deeb8ca12571c2b828d444a2dff5cd6a |
| PostgreSQL17.11 | c55edb5759fecbb19d2f7e983c1abd0f4acaf85797fbbf90c9a8348f6b889c0f |
| Restored Runtime idle fixture | 458b1b38f90af3901fe6bc3dc0b8add62940e2070fde3ee2aeb89e44e9099b86 |
| H targeted verifier | 9b098029ed1c1e136e4a0d64e54b8a7138b1366284b1864dea23ce1943a70f32 |
| H full verifier | 509405b87a133587785c86c952db774549881f6b51c57a36d8c1e5503773059c |

Runtime/verifier image **sha256:d9f553ac9a3376b33f0343f3f5ad014689ed383107ca64ceefd85a4a6f6c9d3b**;
PG **sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27**.
Network none, no public ports, read-only roots, bounded CPU/RAM/PIDs, noexec tmpfs;
Runtime non-root1000/cap-drop/no-newprivs. Only own restored workspaces and socket mounts,
nonrecursive; no original workspace/config/credential mount. Own volume
`pcp848-temp-source-pg-data`, restored workspace/custody, dumps and tmp archives retained.
No containers/volumes/images deleted; no prune. Stop exact owned IDs only:

```sh
(
  unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
  docker --host unix:///var/run/docker.sock stop \
    6bfe00d7a8caf96ffa65ddef70acfd46deeb8ca12571c2b828d444a2dff5cd6a \
    458b1b38f90af3901fe6bc3dc0b8add62940e2070fde3ee2aeb89e44e9099b86 \
    c55edb5759fecbb19d2f7e983c1abd0f4acaf85797fbbf90c9a8348f6b889c0f
)
```

Keep original DB **8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8**,
N observer **da6c434797c46a3312f0ca185b20e0b5fbb9234ce137aee9f81ebc2fb9241660** and
HTTPS **601c552bd0562b947529a591b84c70570a1eaa556fb43e50a8c2ae0d76e362aa** running.
Original stopped Runtime **1b0949227f267d6d0b9144348e8e4dd5cd73d2ca9b74c69597e1d5bab7ecdf35**,
Executor **fc32fd0a0bf632a185aad7d83f21234988359a9d803f8dcc0be36145a9d93e1d**,
Router **f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6**.

Operator model gpt-6.1-sol; effort, tokens, cost and active Owner minutes Unknown.
Start2026-10-31T01:45:01Z; measured closeout/elapsed and evidence hashes are in the
[sanitized closeout JSON](2026-10-31-temp-artifacts-held848.json): operator elapsed
4306.608s through stopped-fixture closeout. Owner intervention requests0; PCP/provider inference0.
Fixture setup/diagnosis/verification/hosted waiting are operator time, not PCP counters.
Preserved setup findings: missing PGHOST caused initial official entrypoint health failure
**after initialization**; inspected PG_VERSION17 and restarted same initialized fixture,
no reset. Python3.11 tar extraction API/candidate import cwd and missing synthetic router
token were corrected only in fixtures. A root invocation without the workflow's explicit
`tests` scope collected service modules without their service import roots; the corrected
workflow-equivalent scoped invocation passed1761. Plain pytest cache placement has an
additional disposable-adapter RED and actual-pinned-CLI/source GREEN regression. Old held fixtures lacked immutable goal context;
fixture data was repaired, Composer was not relaxed. Original unknown bytecode denied as
above. No unattended, benchmark, direct-Codex comparison, VPN parity or internal CLI
compaction protection claim. Static2-call admission limit remains separate.

## Single future rollout/recovery packet — preparation only

1. Independent PM reviews this source PR, full scope/diff and exact-head four-suite CI.
   Choose accepted merge **R** and verify postmerge CI; keep evidence847 unmerged while
   main must equal R. R is not known here. Later update SAME847 onto R by normal merge,
   preserving historical receipts/no force push. No new task/body/base/baseline binding:
   original848 remains task/canonical/verifier H. A fresh ordinary baseline at R is a
   separate future decision after held recovery, never an edit of approved H.
2. A separate finite execution WorkOrder must authorize live operation. Revalidate stopped
   writers, all original rows/usage/counters1/0/0, full 831-node metadata/content manifest,
   exact54-node three-root inventory and three-file source candidate. Preserve original
   V2 bytes/hash **ec1d28f13f44d149001e1657b9122f3a1eb3947e966c3bebe5e99fcb59dbc665**,
   manifest **53b95372e77ef563e4fa527d4bebb42a92720981ac1681e18ffd026d2de6fea8**,
   configs, A/B/C/retired824. Fresh consistent private backup and restored-copy rehearsal;
   a mismatch stops dependent mutation, never refreshes proof/preimages.
3. Build Runtime and Executor serially at **exact R** using existing accepted tool/base
   pins and the accepted source archive/build procedure. Record source archive, Dockerfile,
   inputs/toolchain hashes, image IDs/revision labels and actual security/mount checks.
   Accepted inputs: Node22-bookworm-slim digestde170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d,
   Python3.13-slim-bookworm digest93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5,
   Codex0.160.0/OpenCode1.19.4, DDEVv1.25.4/Buildxv0.37.0. Reconfirm accepted input
   records/recipes; a tag alone is insufficient. Existing RouterS image is
   sha256:422d41413115ce46c24a063a018f942dfd63e04205b167d0b97e6e4d10660319.
   Retain H verifier image above, retained Router source/image only if its complete input
   binding remains valid, and unchanged N observer/HTTPS. No inference/login is needed for
   this non-model operation. No unreviewed source overlay counts as an adopted R build.
4. Reversible worker/config adoption leaves execution OFF. Retain prior IDs/images/configs.
   Before the independent concrete-permit checkpoint, explicitly authorize only bounded
   cold starts **without a permit** to settle first-start Docker metadata, if necessary.
   Runtime's dedicated held mode must reject a missing permit before scheduler/DB/model
   operation; record that expected failure and stop it. Executor/Router bounded start/stop
   likewise need the future WorkOrder. Capture stable post-start fingerprints, including
   OomKillDisable. Do not normalize false/null or auto-refresh a mismatched binding.
   This is a proposed sequence, not a performed or self-approved live operation.
5. Generate one **uninstalled private** version2 candidate with production `read_rows/frozen`:
   exact full original job/receipt/lease, durable returned attestation/progress digest,
   candidate identity/diff, full workspace metadata, explicit three-root inventory and
   private-evidence SHA, exact H baseline/issue/body and R repair commit/path range, actual
   R Runtime/Executor and retained Router configuration/image fingerprints, verifier H.
   Bind new finite validity and execution-record URL only from independent PM disposition;
   old07:00 authority supplies historical identity, not renewed permission. Publish a
   sanitized manifest of candidate/resource/source/image/evidence hashes for that checkpoint.
6. Only after exact independent PM approval install those bytes at
   `/config/pcp-local-artifact-recovery.json` and the unchanged originalV2 copy at
   `/config/pcp-local-artifact-original-activation.json`, private regular0600 files.
   Enable only `PCP_LOCAL_ARTIFACT_RECOVERY_ENABLED=owner-approved`; old held flag and
   ordinary activation remain absent. Do not overwrite/reuse the old config-error permit.
   Start only the approved R Runtime/Executor and retained Router (release observation
   requires it running; no selection/provider/model call). Revalidate stable inputs.
7. Use supported container-resident commands below with the newly approved exact Runtime
   ID substituted as the first argument. Readiness and read-only plan must pass before
   the **single** apply. No ordinary run-once/admission/model command is eligible:

   ```sh
   scripts/pcp-local-session.sh "$approved_runtime_id" readiness \
     --phase held-verification --job-id 15271df1a36b1281010465538a9318ae --json
   scripts/pcp-local-session.sh "$approved_runtime_id" verify-held \
     --job-id 15271df1a36b1281010465538a9318ae --json
   scripts/pcp-local-session.sh "$approved_runtime_id" verify-held \
     --job-id 15271df1a36b1281010465538a9318ae --apply --json
   ```

   Custody intent precedes exact renames; all source bytes/modes and original Git/index
   remain bound. Only genuine mandatory H test success may create proof/reconcile stale
   intent-to-add entries, then existing commit and real Draft task PR/hosted exact-head CI.
   Preserve model1; increment test/delivery counters only for actually executed phases.
8. On uncertain acknowledgement perform bounded read-only status/plan/DB/Git/remote
   reconciliation. No blind POST, new token, renamed source, cleanup or verification replay.
   Custody intent can resume only the exact unmoved partition after full reconciliation;
   `verifying`/unknown tests cannot auto-run again. Verified-uncommitted/commit-uncertain
   use existing delivery readiness and supported delivery reconciliation after checking
   local/remote commit/branch/PR. Failed checks retain evidence; this WO does not authorize
   manually solving848. Stop at independent PM review after real delivery, never finalize.
9. At blocker/delivery/expiry capture afterimages, usage/counters/measurements, fresh backup,
   actual dashboard and exact scoped shutdown. Stop the approved workers and disable new
   authority intact; keep DB/observer/HTTPS and all historical assets. Before custody intent,
   rollback can restore retained reviewed worker/config binding with authority OFF. After
   intent, preserve both source/custody partitions and reconcile; never move-overwrite output
   or restore a whole DB over later state. Unknown outcomes require PM disposition.

Remaining untested boundaries: actual accepted-R build/adoption/provenance, live original848
custody/mandatory verification/real publication/task CI, later PM acceptance; new finite
execution decision and concrete permit review. Optional supervision baseline failures are
not repaired by this change. They do not make the fixture or hosted required suites a
claim of production success. #835/#604 programme work remains open.
