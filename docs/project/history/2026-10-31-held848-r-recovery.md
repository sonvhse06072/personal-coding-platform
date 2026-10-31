# Held848 finite recovery — LIVE publication, hosted CI blocked

[DEC6539534137](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6539534137)
and [timing correction6539840379](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6539840379)
executed against accepted packet610ed799f456b06a946d2ac5c3a86c53d4bc423f/review5721453660.
SAME Draft evidence PR847 remains unmerged; main/platform **R44b79c7e05235c402e426db1b713b1df802a3538**.
Task/base/canonical/baseline/verifier **H871fbf2485a1ffb89a88a69e1daaaca10e25b318** never advanced.
[Machine-readable sanitized receipt](2026-10-31-held848-r-recovery.json) records full hashes,
resources and measurements. Private rows, permits, credentials and transcripts remain local.

## Outcome and next decision

SAME issue848/job **15271df1a36b1281010465538a9318ae** reached real mandatory verification,
commit and [Draft task PR850](https://github.com/sonvhse06072/personal-coding-platform/pull/850),
head **cf41cad08434f930841ced57a773f35783a1f537**, branch `ai/15271df1a36b`. Exact-head
[hosted CI41175379839](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/41175379839)
executed all four suites; root failed one new task assertion. Durable job is **blocked /
pcp_local_hosted_ci_not_passed**, execution **verified**, delivery **ci_failure**,
finalized **false**. Receipt **running/gen2**, lease **active/gen4** full rows unchanged.
Counters **1 model /2 mandatory phases /1 delivery**, consumed budget retained.
No additional developer invocation, login, admission, replay, task edit or finalization.

The root failure is `test_cli_rejects_deep_nesting_sanitized_and_preserves_input`
for a2000-level nested array. The test expects `input_unavailable_or_invalid`; hosted
Python3.13 instead returns sanitized `record_0_schema_invalid`, both `status:INVALID`.
Pinned H verifier Python3.11 passes19+19. Read-only committed-source/log inspection shows
an interpreter-dependent decode/schema error path: the task catches RecursionError but
exposes InputError's bounded reason, and its new test hardcodes the former. This is an
inference from actual source and logs, not an extra runtime reproduction or a general
claim about Python recursion limits. CI green remains mandatory; this failure is not waived.

**Next PM action:** independently review the exact task failure and commission one bounded
same-job repair for a portable nesting/error contract (or a justified implementation policy),
with source/test scope and preserved identity/proof/counters. Determine the supported
post-publication repair transition before mutation; current finite non-model recovery does
not authorize operator solution/test edits, another model, new admission or replay. No
finalization while CI is red. The retained proof cannot be refreshed to accept new work.
Do not automatically restore either authority, even while the finite window remains valid.

## Exact timing correction and original evidence

Original permit360426B SHA **1e42acbcfe6663ed50aeda4051f86a313f9542de2b675fbd4799ee0707f6633e** and original
sidecar SHA **2206863d259df8cab005ac40b34bc0f2a95fee02ee99fb9e2e94e7484b0eecc1** remain byte-identical.
ONE separately named production-canonical derivative changed only top-level `not_before`
1793430900.0→1793426400.0 (07:15→06:00Z), retaining float type. Derived raw/canonical permit
SHA **681a728f8277403a73a9029b33409e8528d9c990a6badcc893056c35ead71284**, still360426B. Expiry1793452500.0
(**13:15Z**) and every other value/type/preimage/inventory/source/image/ownership binding
are unchanged. Offline accepted R serializer/parser passed using the real clock.
Separate sidecar changed only `permit_raw_sha256` and `proposed_not_before`; derived SHA
**cc452de8c5e24b6c71af6dc5e94ee23eafc472ab1ba9cab864585fc8cea77481**. Original provenance URL and null
approved_execution_record remain; separate append-only records carry external approval.
Sanitized deltas/hashes were published on847 **before installation**. Original ordinary
V1/V2 historical07:00Z expiry remains unchanged, disabled; the new finite authority is separate.

Read-only05:34:47 and06:03:31 audits matched ORIGINAL whole DB/sequences, all831 workspace
entries, candidate modes/index,54 nodes/three roots, full rows, mounted bytes/metadata,
canonical H, A/B/C and exact resource fingerprints. No evidence refresh. Install-preflight
06:05:12 passed; original V2-copy and derived permit installed no-overwrite0600/fsync.
Original V2 SHA **ec1d28f13f44d149001e1657b9122f3a1eb3947e966c3bebe5e99fcb59dbc665**, manifest53b95372… retained.
Router→Executor→Runtime each started once; stable post-start audit06:05:23 passed.
Actual held readiness and read-only plan passed; fresh pre-apply audit06:07:07 passed.
Exactly ONE supported `verify-held --apply` command began06:08:01.483761Z, sending ONE
mutation request. It reconciled verified_uncommitted; no second POST/replay. This historical
held audit cursor does not negate the later verified execution/commit/real publication.

## SOURCE / FIXTURE / PHYSICAL / LIVE evidence

| Class | Actual evidence | Result |
| --- | --- | --- |
| SOURCE | Accepted R reused; task H, canonical H, reviewed role/config bindings preserved; only evidence docs changed on847 | PASS |
| FIXTURE | [Prior accepted preparation](2026-10-31-held848-r-preparation.md): R74 regressions; restored copy H19+19 and synthetic publication. All12 prep fixtures retained OFF; no fixture proof copied | PASS historical, not live proof |
| PHYSICAL | Exact IDs/image/config/mount/inventory preflights, supported54-node durable custody, real H verifier child containers, no inference/auth/rebuild | PASS |
| LIVE mandatory | Targeted19 in0.27s; full19 in0.22s; actual bounded verifier workflow8.020790s | PASS |
| LIVE Git/publication | Complete candidate Git identity/modes bound to proof; commit exact single parent H; actual Draft850 and remote branch/head reconciled | PASS |
| LIVE hosted | Root1 failed/1761 passed/1 skipped22.20s; Router132/7.93s; Runtime2783/366 skipped127.64s; Executor815/26.31s | FAIL root, other3 PASS |
| LIVE dashboard | Trusted Chromium, real populated snapshot: blocked/local38 passed/ci_failure/running2/active4, assisted recovery true; reconnect and fixed A/B/C timers | PASS observation, no completed848 claim |
| LIVE finalization | Not authorized; delivery_finalized=false | NOT TESTED |

Tree **b14a0bb25ef7bfb82609c87f88a1f0d37b63b95b**, diff SHA **b7f49de89ffa98cf20f549a4cfdbfc8ce9263a995e23b484faa21e2264f685cf**
match the original candidate. Commit **cf41cad08434f930841ced57a773f35783a1f537** has complete single parent H.
Usage and agent_attempts are byte-equivalent to original; gross601376/cached559104/
net42272 input and1711 output tokens are observed. Reported cost **Unknown** (missing
observation), estimated0 shown separately. No recovery developer tokens/model call.
A/B/C complete rows/events and full workspace metadata/bytes unchanged. Receipt/lease full
rows unchanged. Whole database legitimately changed only cp_jobs/cp_job_events/
cp_task_telemetry and cp_continuity_proposals_id_seq/cp_job_events_id_seq; never claim entire
DB unchanged after execution. V3/retired824, configs, retained assets and history untouched.

## Resources, custody, backups and shutdown

| Stopped worker | Full container ID | Immutable image | Configuration SHA256 |
| --- | --- | --- | --- |
| executor | `d4d056f14883391a80fa4803bc2bb54b9c6814499d99cdf632d42fe7144b9489` | `sha256:3f10289e6b706a724419f58e7e3cfbb9373df39e6a84170dae845dc1d58db5e5` | `c0dd1028b4154542b773fe127a5ff9d3dac2301398c57db203bb8d495a2bfe13` |
| router | `f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6` | `sha256:422d41413115ce46c24a063a018f942dfd63e04205b167d0b97e6e4d10660319` | `f7fd0acc9ce7eb78f36bf4afb13c8ac051640411e542b4ce3037c51a5a4da5ee` |
| runtime | `9d046f4fe87ccc2db838b26131a85e07f222872510ebfbadbdc9efbc79b5cf23` | `sha256:59345373e0af3f9c799a7bc775aa782e92fb74aafe1d20793469a9342130730f` | `a4e27d7234243cdfffa3490664f1dee11939a275aa1d5d2a5b0ed20f2bd8f937` |

H verifier image `sha256:d9f553ac9a3376b33f0343f3f5ad014689ed383107ca64ceefd85a4a6f6c9d3b`.
Actual mandatory children **b1dbaec8404d55a2fba7797af143a8b459d31f41bd9fb495845a93c07a5598a2** and
**345402656cee67fe7b428fb1cfafbbed648626e1b9de73b757548066f4c8d342** exited0 and are retained OFF.
No task-owned container remains running. Historical old H/R2 workers and all12 preparation
fixtures remain stopped/retained. Router reused its original S image/input-equivalence
binding, never selected a provider/model; no route/model call was made by recovery.

At **2026-10-31T06:13:38.936460+00:00**, exact workers stopped and installed derived permit/original-V2-copy
moved no-overwrite/fsync into private `disabled-authority`, hashes verified intact. Ordinary
and artifact authority paths absent; provider auth absent. No logout/login, renewal, cleanup
or historical artifact deletion. Custody54 nodes under audited plan2d359434… is preserved;
original candidate source bytes/modes/tree/diff remain. Authorized custody/commit legitimately
changed workspace/Git metadata; we do not claim its entire post-execution filesystem is unchanged.

Private evidence: `/home/sonvh/.local/state/pcp848-r-recovery-v1` (0700). Original proposal:
`/home/sonvh/.local/state/pcp848-r-prepare-v1`; original/derived time-corrected files retained.
Prior consistent private backup **240271B**, SHA
**c14ef6b9c304bf4b5fa750a5d827c86be90a3c914342831367af85c419cb01c7**, with accepted restored-copy rehearsal unchanged.
Fresh after-backup **463469B**, SHA **5b283a97915a5addfac5f569b3c3f76312fe475a403d7648141121d3bc5c6c81**;
consistent custom dump and archive-list validation passed. Full after-DB SHA
**d725b95260f3e76476b9dc6b36186befd804e1cb778fb738b84fd4dda3800517**. After backup not separately restored in this session.
Private rows/proof/containers/screenshots/logs plus sanitized hashes retained; never publish
full manifests, auth or raw potentially sensitive job/provider payloads.

Keep running, unchanged: DB **8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8**;
N observer **da6c434797c46a3312f0ca185b20e0b5fbb9234ce137aee9f81ebc2fb9241660**;
HTTPS **601c552bd0562b947529a591b84c70570a1eaa556fb43e50a8c2ae0d76e362aa**.
**https://localhost:18443/dashboard** remains tokenless `loopback_readonly`, N source
85e415f1f53c8129056e2f04fb99a9b964b89609. Actual Chromium uses trusted TLS/default validation,
no login/form/cookies/manual injection/TLS-ignore. Live848 elapsed/observed execution
**45.339738s** is retained developer duration, distinct from verification/waiting/CI.
No VPN parity, unattended-run, benchmark or internal-CLI-compaction guarantee.

Exact idempotent scoped stop commands (already executed; retain DB/observer/HTTPS):

```sh
env -u DOCKER_CONTEXT -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  docker --host unix:///var/run/docker.sock stop --time 10 \
  9d046f4fe87ccc2db838b26131a85e07f222872510ebfbadbdc9efbc79b5cf23 \
  d4d056f14883391a80fa4803bc2bb54b9c6814499d99cdf632d42fe7144b9489 \
  f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6
```

Do not use Compose/up, broad stop/prune, permit restoration, reset or backup rollback.
Recovery authority ended operationally at this blocker; expiry remains13:15Z with no renewal.

## Measurements and evidence limits

Session recorded05:32:23.863801Z. Approximate prior timer bounds05:39:40–06:01:09Z
(**1289s**) are PM scheduling overhead, not developer execution/Owner active minutes.
Held mandatory8.020790s; apply command wall **205.313s**
(includes custody/verification/publication/CI polling), hosted workflow147s. Historical
returned developer duration45.339738s is not re-run. Evidence closeout/testing/CI is separate.
Operator gpt-6.1-sol; effort/tokens/cost/active Owner minutes Unknown. Requests for further
approval or interactive login0; observed Owner timing correction1. PCP counters1/2/1 retain
original developer invocation and now actual two mandatory phases/one delivery. This was
assisted recovery of a held job, not successful unattended ordinary development.

Evidence-branch local root checks1761 PASS/20.11s and Runtime continuity10 PASS/0.37s;
these do not include the task patch or replay848 mandatory verification.
Evidence847 required final-head CI is recorded in its PR checks/result receipt, distinct
from failing task850 CI. No source repair or acceptance is implied by documentation CI.
Main R and both Draft PRs unmerged; independent PM owns the concrete next repair decision.
