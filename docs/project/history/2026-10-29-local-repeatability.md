# #835 WorkReport and consolidated next-task packet

Authority: [WO835](https://github.com/sonvhse06072/personal-coding-platform/issues/835)
and [execution clarification6502893427](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6502893427),
continued by [PM6504158102](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6504158102)
after [independent review5702385825](https://github.com/sonvhse06072/personal-coding-platform/pull/836#pullrequestreview-5702385825).
One writer, `ai/835-local-repeatability`, `/home/sonvh/pcp-local-repeatability-835`.
Single [Draft PR #836 and exact-head CI receipt](https://github.com/sonvhse06072/personal-coding-platform/pull/836).
Engineering anchor `34c0e9ac99a057eef0a08a15f0c3828b3c1addfa`. The
[PM merge receipt6502481811](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6502481811)
supersedes earlier premerge instructions: 833/834 merged, stable-R hold closed,
postmerge40912349585 four suites PASS. No source-session main freeze.

## Result and evidence boundary

Phase readiness and supported local operator commands are implemented. Completed
status requires only authenticated read access; delivery avoids unused developer
quota/Router checks; PM readiness uses the actual finalizer in dry-run, including
Git identity, ownership, installed authority, remote review and CI. Finalization
compares full job/receipt/lease preimages atomically under the existing project
lock. It preserves verification/checkpoint/progress and never invokes a model.

The existing container client now has `app.pcp_local_task_queue session` and a
small Docker-only launcher. Default status is read-only. `finalize` sends at most
one existing PM-review POST and always reconciles durable state afterward; exact
completed retries send no POST. Generation comes from the observed lease, not a
hardcoded first-generation assumption. No arbitrary command/URL/SQL, implicit
admission, permit creation, new authority store or service was added.

**Retained A → ordinary B is now FIXTURE PASS.** The pinned CLI supports a
read-restricted named profile without an image/CLI upgrade or a new isolation
service. Enforcement was measured before replacing the broad directory guard.
The validator admits only an authentic completed/PM-accepted sibling with exact
original source/Git proof and delivered ownership. Unknown paths, drift, Git
escapes, arbitrary terminal flags and reservations still fail closed. A's path,
source files, full job/receipt, proof and counters remain unchanged; B acquires
lease generation2 through the existing storage method, with no model invocation.

The review's POST finding reproduced as15 failing/34 passing targeted cases before
repair. `IncompleteRead`, `BadStatusLine`, disconnected/reset connections and
truncated real loopback HTTP responses now reach one bounded read-only status
reconciliation; a second failed read reports sanitized uncertainty. There is never
a second POST. Delivery readiness now separates dependency health from operation
eligibility: already successful delivery belongs to PM, CI waiting/uncertainty
requires remote reconciliation, and only first delivery is eligible. The actual
mutation method also rejects successful/finalized delivery before counters or
publication, independently of readiness.

| Class | Result | Evidence |
| --- | --- | --- |
| SOURCE | PASS, independent acceptance pending | Same PR; phase/client/finalization and PCP-only adapter/retention changes. No Dockerfile, CLI pin, baseline, service configuration or CI edits |
| FIXTURE / RED | Reproduced | Original72b61b6 `TrustedReaders.refresh` with the new ordinary A→B test fails `pcp_local_foreign_workspace`; prior protocol/readiness RED above |
| FIXTURE / Git + PostgreSQL | PASS | 446 focused regressions: all eight real reader functions/original registrar, A finalization→B claim/queued job, lease1→2, exact reacquisition, concurrent requests, rollback/lost acknowledgement, stale CAS/restart, full-row drift and unrelated blocked receipt; proof/counters preserved |
| FIXTURE / physical container | PASS | Current Runtime R image/CLI0.160.0 plus candidate adapter overlay in disposable tmpfs; captured actual argv/environment/config, no `codex exec`/model request. Current-job Python/Git/read/write works; sibling read/stat/list, symlink, Git alternates/worktree, process routes, Git metadata writes, provider-home reads and network socket creation denied |
| FIXTURE / client | PASS | Real loopback HTTP parser failures reconcile a synthetic committed POST exactly once. Prior actual Docker launcher/client fixture remains evidence for the unchanged launcher, not deployment |
| LIVE / read-only | PASS | Existing dashboard/snapshot trusted HTTPS200, actual completed831/delivered3/released1/counters1/2/1. Existing workers remain stopped |
| LIVE / candidate adoption or B | NOT TESTED / NOT AUTHORIZED | No build/adoption, permit/baseline change, worker start, registration, inference, publication or finalization in installed PCP |

Git/PG tests use controlled external source/provider/Executor observations; they
are not physical Executor/Docker/GitHub end-to-end admission. The separate sandbox
fixture uses actual container/tool enforcement. The final accepted image still
requires the consolidated physical gate below. No fixture claims provider login,
model execution, live two-task throughput, browser retest or VPN parity.

Local required suites: Runtime2605/211 optional skips, root1755, Executor797,
Router132 PASS. The exact final hosted SHA/run/job counts are recorded in the
Draft PR verification receipt. All four hosted suites must actually execute;
documentation-classifier skips or earlier-head green do not establish acceptance.
The PR body holds the final SHA/run so recording it does not create an untested
successor documentation commit. The earlier72b61b6 run40922905063 passed5266/186
but was independently **not accepted**; it is not the continuation's CI receipt.

The earlier #835 all-Runtime PostgreSQL-enabled scan executed2765 passing tests and
found two **pre-existing, out-of-scope** plan-supervision fixture failures:
`test_initial_supervised_hold_rejects_mutated_ready_set` passes an unsupported
`continuation_key` keyword; `test_pr_acceptance_does_not_hold_but_durable_merge_does`
expects absent supervision instead of the retained initial released checkpoint.
Both reproduce with identical errors at the anchor using the same disposable DB.
No unrelated orchestration behavior/assertion was changed. Hosted CI does not
configure this optional DSN; it cannot establish these PostgreSQL cases as PASS.

Iteration repairs: the new client initially enlarged the old inspect image's
closed file inventory. Reusing the existing task-queue module resolves the actual
packaging seam without changing its protected Dockerfile/allowlist. T1 headings
and explicit unrelated STOP markers required by continuity tests were retained.
Initial fixture setup/cwd/socket/CA-selection errors were diagnosed before retry;
no live data reset, TLS bypass or repeated unchanged mutation was used.

Measured operator interaction: fixture finalization uses one named command and
three HTTP observations/actions (preflight, one POST, reconciliation); completed
retry uses one read and zero POST. Lost acknowledgement also uses one POST only.
This replaces ad-hoc payload assembly for this operation; it is not a claim of
measured end-to-end Owner time savings or unattended LIVE throughput.

## Measured isolation, implementation scope and reproduction

The initial shorthand `:workspace` read was a diagnostic, not acceptance of the
adapter boundary. Continuation inspected shipped0.160.0 help and generated schema,
then used config-only app-server `initialize`, `config/read` and
`permissionProfile/list` calls. Capturing the real `CodexAdapter.run` invocation
with only its subprocess mocked showed approval=never, memory disabled and network
false overriding hostile synthetic user settings. Replaying that legacy mode with
those overrides still read/stat/listed A and followed B's symlink to A.

The CLI's documented named permission tables are supported by the pinned binary
([vendor permissions reference](https://learn.chatgpt.com/docs/permissions)); the
measurement, not current documentation alone, establishes compatibility. Root and
global temporary reads are denied, the current workspace is writable, and immutable
`/usr`, `/bin`, `/lib`, `/lib64`, `/opt/venv` plus the CLI's minimal toolchain paths
are readable. Existing protected `.git` metadata stays read-only. The initial
minimal profile could not find Python because this image puts its launcher in
`/opt/venv`; adding that immutable input fixed the positive path. No bwrap package,
new mount/capability/service or CLI/image upgrade was installed.

A deliberate hostile config demonstrated that empty permission tables **merge**
with inherited workspace roots. The implementation therefore rejects user/system
config and nonempty or symlinked project/ancestor `.codex` directories before a
subprocess, and passes `--ignore-user-config --ignore-rules --strict-config`.
Empty sandbox-created protected directories are permitted. Existing provider auth
remains at the same `CODEX_HOME` for the CLI transport; tool commands cannot read
that home. No provider/service/publisher token is added to the child environment.
PCP-local only selects this mode; ordinary non-PCP adapter behavior is unchanged.

Exact additional paths and reasons under continuation6504158102:

- `services/runtime/app/adapters/codex.py`: supported named profile, config gate and
  opt-in PCP invocation; no extra environment/broker permitted in that mode.
- `services/runtime/app/pcp_local_worker_loop.py`: pin the measured CLI, select the
  profile, validate retained finalized workspace/source/receipt/Git proof and
  reject executable Git config/alternate/worktree escape before reading proof.
  Existing eight-reader and atomic registrar/reservation paths remain in use.
- `services/runtime/tests/test_codex_adapter.py`, `test_pcp_local_repeatability.py`
  and `fixtures/codex_read_isolation_probe.py`: source contracts, real Git/PG
  lifecycle/concurrency/failure regressions and reproducible physical capability.
- Existing readiness/client/delivery paths and their tests repair the two review
  findings. This records delegated tightening scope, not new Owner authority over
  baselines, policies, images or future live operations.

Reproduction on a separately authorized **disposable** Runtime fixture: first
inspect the exact64-hex ID, accepted image, no mounts/ports, network none, UID1000,
read-only root, cap-dropALL/no-new-privileges,512MiB/1CPU/128PIDs and64MiB noexec tmpfs.
Then, from accepted source (never target a live worker):

```sh
# Standalone process; failing assertions stop only this command.
docker --host unix:///var/run/docker.sock exec -i EXACT_DISPOSABLE_CONTAINER_ID \
  python - < services/runtime/tests/fixtures/codex_read_isolation_probe.py
```

For this source session, only the candidate adapter module was loaded from tmpfs
into the retained R-image fixture; no candidate image was built. The checked probe
asserts hostile-config rejection, actual adapter argv/sanitized environment,
current-job positive paths, every denied route above, network denial and unchanged
full synthetic A file hashes. It creates only synthetic `/tmp/pcp-probe-*` data;
no auth file/login/inference/Runtime API/DB. Private logs and source/probe hashes
are under `/home/sonvh/.local/state/pcp-repeatability835/continuation`.
SHA256: checked probe log `619b8cdd4aa0452a81db46c36a7c213de21b97a840a9b07780724098aeaf9174`;
446-test log `51448334839acdfb67d5b09122de79b912c10a8b8e26182993455f75b3ce3751`;
retained synthetic sandbox archive `4ab5fbc42fe5aed8a3abe90bfcde76b1bc3288d55d205e37e8f5989ce21a1764`.

Retained validation additionally compares full DB snapshots before/after Git and
requires the producer's exact branch/baseline/verification/review bindings. The
persisted PM assessment must have no blockers and the matching head/source; its
`eligible` flag may correctly remain false when automatic merge is disabled.
No new merge permission, proof refresh, chmod, rename, deletion, backup substitution
or alternative instance is used to make ordinary B admission pass.

## Fixture resources and retained LIVE identities

Private evidence `/home/sonvh/.local/state/pcp-repeatability835`; isolated root
`/home/sonvh/pcp-repeatability835-fixtures`. All task-owned fixtures are stopped
at handoff; containers/volume and evidence retained, no prune/removal.

| Owned fixture | Exact container ID | Image / bound |
| --- | --- | --- |
| `pcp-repeatability835-postgres` | `31c6e3c644409b6eced47f6fa19d72c86cd5f2ccb01efe366c6c4d1233674084` | PG17 `sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27`; volume `pcp-repeatability835-postgres-data`; only isolated Unix socket bind |
| `pcp-repeatability835-probe` | `6d30d5f751895679d44847f9bf9d43bdec15b1b2af6e23064ebf47a6c400373e` | Reviewed Runtime R `sha256:0b4d39efde3cdb12be9b650bfb74477bd4d800dcf3e457235e9bea4db2da6bde`; no bind mounts |
| `pcp-repeatability835-client` | `abf587a5fefb302ca7e8cc930f6e118681750f02c2c37e101dec19ab3c3ef933` | Same Runtime R; only read-only #835 app and synthetic server binds |

Two short help/version probe containers with the same task prefix are also stopped
and retained. Continuation shutdown: PostgreSQL exit0; idle sleep probe exit137
from scoped Docker stop timeout, OOM=false (probe process had already returned0).
The prior client exit137 and sandbox-help exit101 are retained history, not a
new test failure. The probe's synthetic tmpfs Git data was archived before stop. Each substantive fixture used network none/no published ports,
512MiB memory+swap,1CPU,128PIDs, cap-dropALL/no-new-privileges. Runtime probes used
UID1000/read-only root and64MiB noexec/nosuid/nodev tmpfs; PG used UID999. No fixture
mounted V3/V4 data/source/credentials. PG first-start socket initialization failure
was reconciled against its initialized PG_VERSION, then the same container started;
no populated DB was reinitialized. Tests used disposable schemas in `postgres`.

If reconciling a later stop acknowledgement, inspect these exact IDs first:

```sh
docker --host unix:///var/run/docker.sock stop --time 15 \
  31c6e3c644409b6eced47f6fa19d72c86cd5f2ccb01efe366c6c4d1233674084 \
  6d30d5f751895679d44847f9bf9d43bdec15b1b2af6e23064ebf47a6c400373e \
  abf587a5fefb302ca7e8cc930f6e118681750f02c2c37e101dec19ab3c3ef933
```

Existing LIVE Runtime `d6fb53f17809e9b11a0e82ecadd1e7c250c8183d84305645c66557cfea6fd285`,
Executor `403553246e43f86b5b38918f3a287d26165654c3919dc5ae5be7543266d269fb` and Router
`f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6` remain stopped.
Running unchanged: DB `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8`,
observer `5d6b3e9b578745877f162f9c34e4413cc855a40a8c4281c32d3c6ed711b05411`,
HTTPS frontend `d22a5bf0ef1adee16464c27ccab10bf3cf22dc7320fa65ed5a995fbd5ea4daf2`.
Their optional scoped stop commands remain in [operations](../../pcp-portable/local-operations.md#v4-shutdown-and-retention);
#835 does not stop them. V3/#824 and all historical credential/rollback assets remain.

## One next-release adoption packet — preparation, not execution permission

**Gate 0: acceptance and scope.** PM independently reviews this Draft PR, exact
head/four executed hosted suites and the boundary above. PM controls merge and
postmerge. Let **P = `<PM_ACCEPTED_POSTMERGE_SHA>`**, filled only from that receipt
after this measured read-isolation implementation is independently accepted. Do not silently
substitute future main. A separate integrated physical WorkOrder must name P,
release bindings, task and resource envelope. No old831 activation/permit is reused.

**Gate 1: immutable frame and exact next task.** Propose a new revision
`pcp-local-repeatability-<P12>-<approval-date>` with source P; append to the registry,
never edit `pcp-local-successor-830-b97ade5-20261029` or its S authority classes.
The registry/config diff must contain only that successor plus the separately
approved `active_revision` change, source checkout P, actual measured image IDs,
fresh task identity and targeted/full test paths below. Keep exclusive lease=true,
isolated_clone, bounded developer, executor-only publisher, no production/merge,
and the reviewed model/resource envelope. Activation remains a later checkpoint.

Proposed small useful task: extend the accepted read-only evidence summary with
deterministic `by_class_and_outcome` counts, retaining existing totals, strict
input validation and `fixture_evidence_is_live=false`. Exactly three allowed paths:

- `scripts/pcp-light-evidence-summary.py`
- `tests/test_pcp_light_evidence_summary.py`
- `docs/pcp-light/evidence-summary.md`

Require empty/mixed-class/outcome, malformed/duplicate/mixed-SHA and CLI tests;
both configured verifier phases include `tests/test_pcp_light_evidence_summary.py`.
No I/O beyond local JSON, no network/Runtime integration, no policy or authority
inference. No issue number/body hash/budget approval is invented here: PM first
publishes the exact task and fresh authority, then binds the immutable issue/body/
base P/baseline/allowed paths and deterministic job ID through ordinary admission.

**Gate 2: build and bind.** In a new private `releases/repeatability-<P>` directory,
create a detached clean P checkout and `git archive P services/runtime
services/ddev-executor services/router`; reject unsafe members/symlinks and hash
the archive, service trees and recipes. Use the existing accepted build procedure
in the [832 packet](2026-10-29-claim-recovery832.md#1-accepted-source-custody-and-build)
as the recipe, with a new reviewed script bound to P, not that historical script's
old identity/permit/install steps. Pin Node base
`sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d`, Python base
`sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5`, Codex0.160.0,
OpenCode1.19.4 and UID/GID1000 unless the separately accepted boundary changes a pin.
Only the private build recipe replaces its FROM with the approved digest; commit
no Dockerfile edits. Build serially with `--iidfile`, revision/instance labels,
private logs and the service-only archived context. Record actual IDs, hashes and
full configuration fingerprints; labels alone are not provenance.

Runtime and verifier must carry the accepted P code/profile. Reuse Executor R and
Router S only if their complete service-input trees/pins equal P and the later
decision explicitly accepts that measured reuse; keep their actual source labels.
Otherwise build that changed role once from P. Do not rebuild/swap observer merely
for docs or this client. Inspect shipped content/modes, immutable executable askpass
outside noexec tmpfs, Docker20, toolchain, non-root/read-only/nonrecursive mounts,
resource limits and network peers. Repeat the checked credential-free isolation
probe against the actual new image (no candidate overlay) and verify its adapter
bytes/profile match P. Check absence of user/system/project config before any
model launch; retain an unexpected config for disposition, never silently delete
it or change provider custody. Old whole-root sandbox behavior cannot pass Gate2. Do not import privileged service tokens into the developer process.

**Gate 3: physical preflight and ownership.** Capture a consistent private DB dump
and full rows/sequences; reconcile completed831/delivered3/released1/counters1/2/1,
retired824 and every blocking reservation. Never reset/release them manually or
create another instance to evade them. Retain all old paths/proofs/containers.
Prepare exact reviewed Docker create/config diffs for only changed workers and
new source/profile bindings, keeping observer/DB/network IDs and scoped credential
custody. Revalidate retained provider login and publisher entitlement only after
the new WorkOrder permits it; genuine expiry needs Owner interaction, not copying
host/V3 credentials. No token in argv/chat/logs. Do not renew either old permit.

Use existing schema readiness under the real scoped role; initialize only through
the supported additive schema command if genuinely required/authorized. Status and
phase commands are in [operations](../../pcp-portable/local-operations.md#835-candidate-operator-interface-and-adoption-gate).
Fresh admission must pass all eight authentic readers/provider checks, retained-A
proof/read-isolation checks and current source P; `ready` does not grant authority.
Measure VPN connectivity only in the Owner's reported state; ask for an interactive
state change when ready to measure the other state. No global VPN/DNS changes;
unmeasured state is NOT TESTED.

**Gate 4: one ordinary task and completion.** After explicit admission authority,
record B's pending0→claimed1→running2 and exclusive lease generation2 without
changing A. Use existing normal one-shot entrypoint once; no auto-next-task. Retain
verification/tree/modes/single parent, honest usage and nondecreasing counters.
Before any publication retry reconcile actual remote branch/all-state PR/head/CI.
Use delivery readiness only for work actually pending delivery. PM independently
accepts exact task head; finalization readiness then one named `session finalize`
records completed/delivered3/released2. Read-only reconcile uncertain responses;
never refresh expected evidence to force success or rerun a fenced model.

**Gate 5: evidence and rollback.** Check the populated tokenless HTTPS dashboard
with normal certificate validation and real browser reconnect. Compare durable
before/after proof/counters and scoped role rights, capture private dump/manifests
and sanitized receipt, stop only named workers, disable fresh authority intact.
Keep DB/observer/frontend for Owner access. On a mismatch, stop dependent action,
preserve the same job/preimages and all failed build/HTTP/CI evidence. Retained old
images are rollback assets, not permission to replay consumed ownership. Never
restore a pre-admission backup over a later receipt or re-enable an expired permit.
Any rollback/adoption must use the later decision's exact IDs/config and reconcile
current data first. No production, force push, foreign workload or global changes.
