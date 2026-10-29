# Successor831: physical rollout and reconciled admission stop

[DEC-PCP-815-SUCCESSOR831-LIVE-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6494028046)
authorized one integrated local session. Accepted PR830 source
**S=b97ade581fecad4db2146258e5ca02c3902189e0**, tree
`173ba174224888692561b08568c72265c10490ec`; postmerge
[40855733876](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40855733876)
executed structure1741/1 skipped, Runtime2540/134 skipped, Router132,
Executor780: **5193 passed/135 skipped**. These are accepted-source CI,
not proof of successful admission. Actual main remained S at all physical gates.

One operator/writer, no agents. Continuity worktree
`/home/sonvh/pcp-successor831-live`, branch `ai/815-successor831-live`.
Keep the follow-up PR unmerged until PM explicitly closes the stable-S window.
Frozen application/build source is a separate clean detached checkout at S.
No installed application patch or image relabeling occurred.

## Result and evidence classes

| Class | Result | Actual evidence and limits |
| --- | --- | --- |
| SOURCE | PASS | Accepted S/tree/CI, committed build inputs, exact issue/body/baseline bindings; source incompatibility below remains unresolved in deployed S. |
| FIXTURE | PASS, reproduction | 209 local tests: one explicit S failure reproduction plus existing dispatch regressions, using transactional doubles. They reproduce the defect and preservation, not a repaired source or actual PostgreSQL fixture. |
| PHYSICAL | PASS | Three serial builds, actual offline packaging/security/toolchain probes; clean canonical clone succession; consistent dedicated DB backup and real table/sequence role checks; actual worker/observer coexistence. |
| PHYSICAL | PASS, limited | Fresh V4 device login, authoritative available quota, Router choice, repository-scoped publisher read/askpass checks, readiness200/ready=true and all eight concrete readers. These checks failed to detect the later registration-policy contradiction. |
| LIVE | FAIL, reconciled | Exactly one run-once returned409 after receipt claim, before job insertion or model invocation. Receipt retained claimed/gen1; no job, lease, workspace, commit, remote branch or PR. |
| LIVE | PASS, observer only | Trusted Chromium, tokenless HTTPS,223 successful snapshot responses, no cookies/forms/page errors; dashboard stayed available during actual worker coexistence/admission attempt. |
| LIVE | NOT TESTED | Development, populated job timers/usage, verification, Git commit, publisher write and task-head hosted CI; no job reached those stages. VPN ON/parity and second-machine LAN remain unmeasured. |

No fixture data was inserted into V4. Its dashboard still displays **No admitted
jobs** because the current projection shows jobs, not a receipt without a job.
That empty display does not mean its admission reservation is free.

## Immutable physical bindings

Instance/root: `pcp-local-adoption825-v4` /
`/home/sonvh/pcp-local-adoption825-v4`. New release:
`releases/worker-b97ade581fecad4db2146258e5ca02c3902189e0`.
Private evidence root: `/home/sonvh/.local/state/pcp-successor831-live-v1` (0700;
private artifacts0600). Full inspect/env/activation/auth files remain private.

| S image | Immutable ID | Git service input tree |
| --- | --- | --- |
| Runtime/verifier | `sha256:6f057d0851e3c3e6daefc9509341683974c52d7e8256900a81b597fba7b55089` | `73066358c74f4a407a48e316e6b3fef517be0610` |
| Router | `sha256:422d41413115ce46c24a063a018f942dfd63e04205b167d0b97e6e4d10660319` | `a8fe2fd51ab2bbd6046cbc6d88435ba043d99d83` |
| Executor | `sha256:e784279da71bc00c2d4b0165a6f862e644d3298cec5c1b111d00e80964afa0f7` | `32251d92c0caeff8e2fde18680ed35c56247a81f` |

New full-S tags; no old tag overwrite/bootstrap rerun. Committed archives,
Dockerfile-local first-FROM pin delta, build argv/logs and packaged file bytes/
executable modes retained. Pins remain the [merged rollout packet's](2026-10-29-observer-worker-rollout.md):
Node22 digestde170b3, Python3.13 digest93498f3, Codex0.160.0,
OpenCode1.19.4, DDEV1.25.4, Buildx0.37.0, UID/GID1000; actual Docker20.10.24.
Offline probes verified non-root, read-only rootfs, noexec tmpfs, immutable
executable askpass and toolchain. They had network none and no credentials.
This is local operator provenance, not signed OCI attestation.

Canonical `sources/personal-coding-platform` is a fresh clean detached S clone,
correct origin/owner, no alternates/hardlinks/symlink escape. Old clean5ad clone
was moved intact to release `rollback/canonical-5ad`; bundle SHA256
`c52154b040739c6a066340316b7c9a3f8fcfef7aa896a0b6fe61116b1ea58cdf`,
filesystem archive `8afd3db0ce64bfb7aa2f3a5a1283333d4c600e8e133086f7b29692e895c32a63`.
Its full file manifest remained identical. No running mount/CWD consumed it at
succession. No reset, cleanup or foreign workload mutation.

Real worker security: exact private network, nonrecursive binds, no host control
ports, non-root/read-only/cap-drop/no-new-privileges, finite CPU/memory/PID limits,
noexec tmpfs. Runtime had exactly config/workspaces/own-home mounts; only Executor
had Docker socket, canonical source and publisher token. Existing internal tokens
and observer configuration stayed unchanged. Private before/after env diffs,
create intents and complete applied Docker service specs are retained. The Compose
proposal was preparation; actual individually applied CLI specs are authoritative
and include Docker `BindOptions.NonRecursive=true`.

## Baseline, credentials and preflight

Installed at10:48:43UTC: NEW approved/active
`pcp-local-successor-830-b97ade5-20261029` at S. All50 protected classifications
and prior825/827/828 definitions preserved, schema/authority validation passed.
Project uses bounded isolated clone, exclusive lease true, native targeted/full
`tests/test_pcp_light_evidence_summary.py`, commit/push-ai/Draft PR enabled,
auto-merge/production false. No model/routing-policy changes.

Installed SHA256:

- `project-baselines.pcp-local.yml`: `0cdff53f95c5bcc15c780acee87d5d925d6c8cd9cf77afe60bca68a9da0a7021`.
- `projects.pcp-local.yml`: `21f5df8c08c38c65a6f861702b2de9d287e89a32656a4ceb81c958369c057983`.
- models: `a748faf933fe5c792679a687f2b0870f97fb6f6af8bd70887cc9bb4d8758844d`;
  policy: `cc71c65bec662e4726ee056525f0a02a6a1bfd9e1f09f92abad22a37b9c9d615`.

Actual nine Runtime tables/three sequences permitted to `pcp_runtime`; observer
SELECT-only/no sequence usage, no superuser/create privileges. No schema or grant
change was necessary; no new initialization/idempotence claim from this session.
Fresh Codex device login completed by Owner10:54:57UTC in V4's dedicated home;
no V3/host subscription auth/keyring copy or model-based login test. No inherited
Codex config/hooks/MCP, agent environment excludes service/DB/publisher credentials.
Same authorized retained repository publisher PAT loaded only in Executor;
actual owner/repository push metadata, PR/Actions/status reads and authenticated
Git read passed. Finite expiry **2026-11-04T08:29:46Z**. Write publication untested.
Readiness was200/ready=true/blockers[]/model0/registrations0; all eight actual
readers passed10:59:46UTC. Router selected `codex_gpt6_luna`, `gpt-6-luna`, effort
`low`; quota was authoritative/available. No inference consumed.

## Exact admission and diagnosed defect

Frozen issue831 body SHA256
`c05077c5838a3fb1fbd0ba53930f2348fc7ec52531a049df55761540ed000858`, goal
`b3d8bbf7a58da8d15605d23670e02f4b3af9d2c966cdfdf8f45d424a41e47640`.
Deterministic identity **a8851f89dd3e4e582c697ec1fe6d8cdb**; same three allowed
CLI/test/doc paths and finite2-call/900s/3-file/$0 contract. Issue bytes unchanged.
Activation installed once **2026-10-29T10:51:28.134568Z**, original expiry
**2026-10-30T10:51:28.134568Z**; file SHA256
`bfa447d7e79afe7f53267598d280beb084c6a88ebf6d8dcb5d22f9b05a5752a4`,
canonical digest `04687cdd66588566f0b4a5d6680fcfcc0f19f186c9dd26ed7187ececcd3c58c2`.
Observer binding used the approved retained hash8fc9a8cf without refreshing proof.

| UTC | Actual transition |
| --- | --- |
| 11:00:05.308206 | Source receipt inserted pending/gen0. |
| 11:00:10.091045 | Same receipt claimed/gen1, reserved deterministic job ID. |
| 11:00:20.495020 | Sole POST returned409 `pcp_local_launch_uncertain_do_not_retry`. |
| Before shutdown | SQL: zero jobs, zero leases; empty workspaces. Exact remote branch404, matching PR list empty. Read-only real registration gate fails `pcp_local_current_authority_changed`. |
| 11:04:34.795135 | Scoped stop/retention complete; original receipt and full DB snapshot identical across shutdown. |

Root cause: S `RuntimeTaskLauncher.require_registration` requires
`exclusive_project_lease is False`; approved rollout/WorkOrder/config require
True and the execution path later acquires the durable exclusive lease.
`TrustedReaders.authority`/readiness omit this predicate, so preflight passes
before the claim becomes stranded. Existing dispatch tests use False and miss
this integration. Read-only actual gate plus transactional-double reproduction
confirm the mismatch. No live retry, manual SQL, counter reset or configuration
weakening was attempted. There is no job row/proof/usage to invent; zero model
calls means none occurred, not a reset persisted counter.

## Backups, shutdown and dashboard

| Private artifact | SHA256 |
| --- | --- |
| Consistent `v4-before.dump` (28446 bytes) | `47d658bb98f42f7123e5314b080d238a11cdfbb1d7c4f9bf93e13cfa18457d75` |
| Consistent `v4-blocked.dump` (29082 bytes) | `2161e71599a83b57decb542c8e7c3b43d1c07678c21cbb416cba5836887abd8a` |
| Full blocked DB rows/sequences snapshot | `62491980c3c6ab686661035c43175bedb19cc3915e877c172598b018bce94dff` |
| Exact retained claimed receipt preimage | `32b527abe26e594c58fc4c96614cebd75bfe33883379f624b8c40088bde9540e` |

Both dumps have successful `pg_restore --list` evidence; no restored-copy rehearsal
is claimed for these new backups. DB differences are the actual source receipt plus two collector-status rows and
one authoritative quota snapshot from the Runtime telemetry collector. Quota
metadata already existed before admission; all sequences stayed unchanged.
No job/lease/event/fixture records were inserted.

New workers stopped cleanly, restart=no:

- Runtime `f8d63b9721d37883ad111fd1e3cd46b79cb39b8535cfadc856d5dff791ceb938`.
- Executor `cade4f36d11544a1bda50145a3d5095e7a92b7d561d1822e5d168196279479b8`.
- Router `f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6`.

All three packaging probes exited and are retained. V4 now39 containers:
**three running,36 stopped**. Old stopped workers safely renamed and retained.
All22 historical V3 containers remain stopped; V3 retirement/proofs/counters and
rehearsal/rollback resources untouched. Original activation moved intact to
release `rollback/activation-831-disabled.json`; active config path absent.
Original expiry unchanged. Scoped Runtime auth and finite publisher credential
retained privately for future reviewed same-identity reconciliation, unloaded
from running worker use. No credential transferred to observer.

Still running, unchanged:

| Resource | Exact ID |
| --- | --- |
| V4 DB | `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8` |
| Observer51349 | `5d6b3e9b578745877f162f9c34e4413cc855a40a8c4281c32d3c6ed711b05411` |
| HTTPS frontend | `d22a5bf0ef1adee16464c27ccab10bf3cf22dc7320fa65ed5a995fbd5ea4daf2` |
| Private network | `4f39b2458e6bbb9cee83bcee01053d4022bc9e49aa4877f3815c1a1161d571d5` |

Volume `pcp-local-adoption825-v4-postgres-data` retained. Observer image remains
`sha256:d7761e08e8f9318d38d948f1b3ea916825762cec45e47ead5f85c7567b5f586f`,
frontend `sha256:552e7481ca93ffccd046aa658dbbed22caefbc09c66fa7cd247cbb90b8a5c609`.
Mounted configuration hashes unchanged. **https://localhost:18443/dashboard**,
`loopback_readonly`: open locally, no token/login/cookie required. Default TLS
validation passed; no ignored TLS errors or injected cookies. Existing loopback
boundary preserved. [Exact scoped stop/rollback commands](../../pcp-portable/local-operations.md#v4-shutdown-and-retention)
remain valid; no blanket stop/down/prune or rollback executed.

## Source correction candidate, not physically adopted

After the exact cause and retained-state proposal were presented, Owner explicitly
approved source PR preparation for protected
`services/runtime/app/pcp_local_worker_loop.py` in this session. This is recorded
as Owner chat approval, not a fabricated GitHub-authored approval. Scope: shared
operational project gate, exclusive=True, readiness/registration consistency,
existing tests and continuity; no deployment or claimed-receipt recovery.

The candidate shares repository/main/registration/workspace/permission/native
verification predicates between `TrustedReaders.authority` (before source receipt
recording) and `RuntimeTaskLauncher.require_registration` (including inside the
locked insertion transaction). Both require boolean exclusive=True. Job/receipt/
lease CAS, source/baseline/image equality, stale observations, uncertain-outcome
no-retry and execution lease acquisition remain intact. No replay mechanism added.

17 new fixture regressions cover successful readiness then one actual registrar/
queue insertion with the approved configuration; missing/false/nonboolean lease,
revoked rights/native verification and wrong workspace permissions denied before
receipt recording; policy drift under insertion locks keeps the claim without
job or replay. Existing dispatch tests now use the actual approved exclusive=True
configuration. Transactional DB/provider/Docker boundaries are doubled; these are
SOURCE/FIXTURE evidence, not physical adoption. Focused265 passed. Two new tests
are also checked against a separate copy of original S to prove they detect the
old successful-readiness/failed-registration behavior. Full local verification passed: structure1742, Runtime2557/134 skipped, Router132,
Executor780 = **5211 passed/134 skipped** (Python3.12 host). Exact-head hosted
Python3.13 results are attached to the follow-up PR; skipped integration tests are
not actual database/container coverage. No full private config is published.

## Concrete next decision, not a replay instruction

1. Review the source correction proposal: one shared exact project-policy gate
   for readiness and synchronous registration, exclusive=True, with positive
   registration and pre-claim rejection/drift regressions. Owner approved the
   protected source path for this PR; independent PM review/merge/postmerge and
   physical adoption remain separate, and this candidate is not deployed.
2. Preserve the claimed/gen1 receipt. Existing `/deliver` requires a verified
   job and cannot recover this claim with no job. A reviewed same-identity
   recovery design must reconcile the complete original receipt, absent job/
   lease/workspace/remote effects, concurrent writers, rollback and lost ack.
   Neither run-once repetition nor manually creating/resetting a row is allowed.
3. PM must resolve stable-S/source/image/baseline succession before any corrected
   code can handle831. Current exact-image/task-base checks remain binding;
   no hot patch, relabel, stale-main waiver, issue-body edit or silent revision
   rewrite. No replacement issue/job or receipt disposition is authorized here.
4. Independent review/merge/postmerge and a concrete next physical checkpoint
   must bind any recovery release, credentials, original expiry and ownership.
   Developer does not self-merge or fabricate acceptance. Final task delivery,
   its tests/commit/Draft PR/CI and populated dashboard evidence remain outstanding.
