# #835 WorkReport and consolidated next-task packet

Authority: [WO835](https://github.com/sonvhse06072/personal-coding-platform/issues/835)
and [execution clarification6502893427](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6502893427).
One writer, `ai/835-local-repeatability`, `/home/sonvh/pcp-local-repeatability-835`.
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

**Sequential B admission remains blocked.** A legitimately finalized fixture job
retains its exact workspace/proof/counters and released lease, but an ordinary B
still hits `pcp_local_foreign_workspace`. A real sandbox probe shows why allowing
that directory now is unsafe. The WorkOrder explicitly permits a precise boundary
proposal while independent work completes; the guard is deliberately retained.
This PR does not claim full A-to-B repeatability or permission for the next LIVE task.

| Class | Result | Evidence |
| --- | --- | --- |
| SOURCE | PASS, subject to independent acceptance | Phase/client/finalization changes; unchanged admission and credential gates; no Dockerfile, policy, baseline, service configuration or CI edits |
| FIXTURE | RED reproduced | New phase regression against anchor fails `collect_readiness() got an unexpected keyword argument 'phase'`; retained completed A rejects B in actual `TrustedReaders.refresh` |
| FIXTURE | PASS | 388 focused tests, including real temporary Git and isolated PostgreSQL roles/schemas; normal recovery, modes/content/parents, receipt/lease fences, atomic finalization, full-row drift, concurrent requests, rollback, lost acknowledgement, exact retry, revoked authority/unapproved review and no model replay |
| FIXTURE | Boundary demonstrated | Credential-free Codex0.160 `:workspace` sandbox reads a sibling job file; no model/auth/network call. A terminal DB flag alone cannot grant safe retention visibility |
| FIXTURE / physical container | PASS | Existing Runtime image plus read-only candidate source, network none: actual launcher/container client makes exactly one authenticated GET status, reports zero mutation requests; synthetic HTTP response only |
| LIVE / read-only | PASS | Existing dashboard and snapshot HTTPS200 with pinned existing CA verification, no auth/cookie; actual completed831, delivered3/released1, model1/test2 observed. Existing worker IDs remain stopped |
| LIVE / candidate adoption, B admission | NOT TESTED / NOT AUTHORIZED | No build/adoption, worker start, baseline/permit change, registration, inference, task publication or finalization in installed PCP |

Local full suites use the repository CI commands. Router132, Runtime2583 (185 optional skips), Executor797 and root1755 passed.
The exact hosted PR head/run and executed job results are recorded in the
Draft PR verification receipt. All four hosted suites must actually execute;
service skips from a documentation-only classifier are insufficient. The PR body
holds the final SHA/run so recording a run does not create an untested successor
documentation commit. Earlier-head runs never establish final acceptance.

An additional all-Runtime PostgreSQL-enabled scan executed2765 passing tests and
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

## Sequential-workspace boundary proposal (not implemented or approved)

Runtime mounts the whole workspace root; the developer shares its UID. Executor's
existing observation validates the current job and exact container/source mounts,
but does not attest ownership or read isolation of retained siblings. Runtime's
current root-directory exclusion is therefore material, not merely inconvenient.
Actual isolated command, using only synthetic files in the probe's tmpfs:

```text
codex sandbox -P :workspace -C /tmp/job-b -- cat /tmp/job-a/proof
exit 0; output retained-fixture-proof
```

Proposed boundary: keep the existing Runtime/Executor services and per-job paths,
but use a reviewed, pinned Codex permission profile that restricts **reads as well
as writes** for each developer invocation. Its read allowlist must be only the
current exact job, necessary immutable toolchain/libraries and the existing scoped
provider home; workspace-root/sibling reads are denied. Writes remain current-job
only. Do not change provider/publisher credential custody or network policy.
The exact shipped CLI's ability to enforce this profile is **not verified**;
the follow-up source/fixture decision must prove it before selecting/adopting it.
No fallback to the measured broad-read profile is permissible.

Acceptance for that decision, in one bounded source/fixture follow-up:

1. Demonstrate denied sibling enumeration/read/stat and escape via symlink, Git
   alternate/worktree metadata or `/proc`; demonstrate successful current-job
   read/write and normal toolchain use with no new credentials/model invocation.
2. Only after enforced read isolation, replace the broad root exclusion with a
   Runtime-owned retained-workspace validator. Require exact deterministic path,
   no symlink/foreign resource, full trusted job/source/receipt/commit/tree/mode/
   parent/proof binding and finalized/released ownership. Reject unknown, drifting,
   incomplete or reserved siblings; terminal status alone is insufficient.
3. Run actual A finalization then ordinary B admission/registration through all
   eight readers and the existing registrar. Keep A bytes/path/proof/counters;
   prove B generation2 lease ownership, duplicate/stale/concurrent claims and
   restart/lost acknowledgement fences. Test Runtime and Executor together.
4. Independently review any protected sandbox/security/config changes. No source
   approval, green CI or this PM record invents an exact-path Owner amendment.

No chmod, rename, deletion, backup substitution, separate instance or forged
proof is an acceptable workaround. The present PR can be reviewed for its
independent improvements while this prerequisite remains explicit.

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
and retained. Each substantive fixture used network none/no published ports,
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
after the required read-isolation implementation is also accepted. Do not silently
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
resource limits and network peers. The old whole-root developer sandbox cannot
pass Gate0/2. Do not import privileged service tokens into the developer process.

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
