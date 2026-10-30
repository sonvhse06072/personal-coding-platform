# #837 finalization preflight — exact directory metadata mismatch

[PM6524074680](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6524074680)
authorized finalization of the same job ccb57d244cfd1fc069a98fd8c17734a1 using
[independent review5712944983](https://github.com/sonvhse06072/personal-coding-platform/pull/841#pullrequestreview-5712944983).
Pinned packet: PR838 head0659bd89e064656b807af14ae6dce4a872f13c93,
[prior execution report](2026-10-30-r2-held837-execution.md).

## Result: BLOCKED before authority restoration

SOURCE/remote PASS: main remains R2 f02d9a14af33d9efeb99aa573d776aab3119dec1;
PR841 open/unmerged at b29bc64d082e8fff924142e5aef48e93a15ef482, sole Q parent;
authentic structured review5712944983 verdict pass/no findings, exact head and diff.
Task CI41058684258 remains successful, four actually executed suites already inspected.
No task verification, delivery, provider call, model, source repair or rebuild was performed.
Historical fixture evidence remains historical; no fixture rerun.

PHYSICAL preflight at13:44:30 UTC found exactly one frozen workspace discrepancy:
B's `.git` **directory** mtime_ns and ctime_ns differ. Every B file's bytes and complete
identity, all other directory identities, and A's complete workspace match. Device,
inode, mode, uid, gid, link count and size of the discrepant directory also match.

| Field | Frozen post-recovery snapshot | Observed now |
| --- | --- | --- |
| Path | B837 `/.git` directory | same |
| mtime_ns | 1793364984255976286 | 1793365011103344837 |
| ctime_ns | 1793364984255976286 | 1793365011103344837 |
| UTC | 2026-10-30T12:56:24.255976Z | 2026-10-30T12:56:51.103345Z |

The frozen workspace snapshot was captured before the previous session's supported
read-only delivery-readiness call. That call invokes `reconcile_commit`, including
`git status --porcelain`, which can create/remove an index lock and update directory
metadata. The observed timestamp falls in that interval. This is a plausible specific
cause, **not an independently recorded filesystem event**. No Git command was run
against B during this diagnosis; descriptor-safe snapshots preserve original evidence.
No expected manifest, permit, directory timestamp or file was refreshed to force equality.

The decision explicitly requires post-recovery afterimage reconciliation and says not
to refresh mismatched expected evidence. Therefore dependent restoration/start/finalize
was withheld. A default-dry-run flag mismatch is also understood: the accepted operator
CLI uses `session finalize` as its explicit mutation command; `--apply` is accepted only
for `verify-held`. No unsupported invocation was attempted and no CLI change is needed.

## Independent checks completed and retained state

Full live DB snapshot equals the prior post-shutdown snapshot. Job SHA256 remains
`7747b382271aa9dfb46e97ab146f815ec623581e21a7db61998e9a99276aaeb7`;
verification SHA256 remains
`0eac30b90dcf9da8a6bf2377a60cabbf0d6cf1edc8237b468887abca7e74a9b3`.
Receipt running/gen2, lease active/gen2, counters1/2/1, usage and complete checkpoint
remain unchanged. No finalization POST occurred; completed/delivered/released is NOT TESTED.
No events, telemetry rows or sequences changed. A831 unchanged; V3/retired824 untouched.

All original configuration bytes/modes/owners, exact worker image/config fingerprints,
observer dependencies, disabled authority bytes, original backup and expiry passed.
Fresh consistent private backup SHA256:
`d2f5d1739a99b801236f08fc887032e3fe894e8ae596aa2704adfbe0c39096e8`.
Private evidence directory:
`/home/sonvh/.local/state/pcp-r2-held837-prepare-v1/finalization`.
The prior original/observed snapshots are retained separately; no private manifests or
credentials are published. Original permit file dcd9411c, digest873e6e19, activationdef8bf73
and manifest6bec39b5 retain their full hashes recorded in the pinned report.

No worker started. Runtimee5d8a338/Executor9cba24de/Routerf03edbd9 remain stopped;
all authority files remain disabled intact. DB8b72a8d3, observer5d6b3e9b and HTTPSd22a5bf0
remain running,84 owned/81 stopped. Exact full resource/image IDs and scoped stop commands
are unchanged in the pinned report. No cleanup, replacement or global configuration change.

LIVE observer: https://localhost:18443/dashboard remains tokenless/local. Fresh normal-TLS
Chromium polling/reconnect verifies A completed and B still blocked/verified/ci_success;
it is not a completed-B dashboard claim. Fixed47.582929s and prior Unknown cost remain.
The old assisted_recovery label limitation is unchanged. No VPN/LAN claim.

## One concrete PM boundary proposal

If PM accepts the measured metadata-only delta, publish a disposition permitting the
same finalization after revalidation against BOTH retained snapshots, accepting **only**
B `/.git` mtime_ns/ctime_ns1793364984255976286→1793365011103344837. Require every other
field/file/full DB row/proof/counter/config/source/image/remote review/CI unchanged.
Preserve the frozen manifest and exact existing permit bytes; no successor or rewrite,
no timestamp reset, no new job or replay, same original2026-10-31T08:00:00Z expiry.
Any additional delta stops dependent mutation. This is a proposal, not an approval.

After that exact disposition, continue the pinned supported finalization sequence:
restore only the two approved files0600/single-link, start only necessary approved
workers, readiness with exact job and review5712944983, then ONE `session finalize`
(no `--apply` flag in this accepted CLI), followed by read-only reconciliation.
Router is needed only if the actual finalization identity/release observation demands it;
its permitted exact ID is retained. Require completed/pm_review_accepted,
delivery_finalized=true, delivered/gen3, released/gen2, counters1/2/1 and unchanged
proof/usage/checkpoint. Then actual terminal dashboard/reconnect, backup, scoped stop
and intact disablement. No merge/main movement; PM handles eligible merge separately.

One initiating Owner decision relay observed in this continuation. No authentication
interaction or command micro-approval; Owner active minutes unknown. This preflight
spent no model/mandatory-verification/delivery execution time. Prior recovery durations
remain evidence, not an unattended benchmark. Exact evidence-head CI is linked from
PR838 and the consolidated issue835 receipt. Deadline is unchanged; no automatic renewal.

Evidence checks: local root1755 passed; diff check passed. One concrete PM disposition
request was sent after completing the proposal; no response or permission is assumed.
No routine command approval or authentication interaction was requested.
