# #837 supported finalization — completed with retained evidence

[PM6524074680](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6524074680)
authorized finalization of the same job ccb57d244cfd1fc069a98fd8c17734a1 using
[independent review5712944983](https://github.com/sonvhse06072/personal-coding-platform/pull/841#pullrequestreview-5712944983).
Pinned packet: PR838 head0659bd89e064656b807af14ae6dce4a872f13c93,
[prior execution report](2026-10-30-r2-held837-execution.md).

## Finalization completed — 2026-10-30 13:58 UTC

[PM6524535370](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6524535370)
accepted only the measured preflight directory timestamps under
[finalization6524074680](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6524074680).
Both snapshots, original manifest/permit bytes and Oct31 08Z expiry were preserved.
Revalidation passed with no additional drift. Only Runtime and Executor started;
Router was not required by finalization and stayed stopped. Supported readiness PASS,
then ONE `session finalize` WITHOUT `--apply`, HTTP200, read-only reconciliation PASS.

B837 `ccb57d244cfd1fc069a98fd8c17734a1` is **completed / pm_review_accepted**,
`delivery_finalized=true`, review5712944983, receipt **delivered/gen3**, lease
**released/gen2**. Complete checkpoint/proof, verification, original usage and progress
are unchanged; counters **1 model / 2 tests / 1 delivery**. No model, mandatory-test,
delivery replay, admission, rebuild, guard change, timestamp reset or merge.

At13:59:09 UTC the two workers were stopped, authority disabled intact again; all three
approved workers are stopped. DB/observer/HTTPS remain running. A831 full row/workspace
unchanged; retired824/V3 and historical resources untouched. Main remains R2; task,
canonical and verifier Q; PR841 headb29bc64d and PR838 remain unmerged for PM.

LIVE dashboard https://localhost:18443/dashboard remains tokenless loopback_readonly.
After shutdown, normal-TLS Chromium showed both jobs completed, B delivered3/released2,
fixed47.582929s across seven200 polls and offline/reconnect, no cookies/forms/page errors.
Known old assisted_recovery label limitation remains; this is assisted recovery, not
an unattended benchmark. PM now reviews finalization evidence and owns merge ordering.

## Final afterimages, resources and evidence classes

SOURCE: same accepted R2 workers; no application edits. Task PR841 retains exact head
`b29bc64d082e8fff924142e5aef48e93a15ef482`, accepted review5712944983 and genuinely
executed task CI41058684258. FIXTURE: prior tests remain historical, none rerun here.
PHYSICAL/LIVE finalization and terminal dashboard: PASS. Merge: NOT PERFORMED.

The final transaction changed only B job status/result/error/updated_at, receipt
state/generation/updated_at, and same-owner lease state/updated_at. Every other job
field, complete checkpoint/progress and all other DB tables/sequences equal the
pre-finalization snapshot. This direct supported transaction did not append events or
refresh advisory telemetry; no such side effects are claimed. Raw result now contains
authenticated PM review, refreshed CI evidence and merge eligibility; it does not merge.

Every workspace file's bytes and complete identity remained unchanged. A's full
workspace is identical. During the supported readiness/finalize path, B `.git`
directory timestamps advanced from1793365011103344837 to1793368712622285043;
all its other fields and all other directories remain identical. This post-operation
observation is recorded separately, without rewriting either preflight snapshot or
extending the one-time preflight exception. No speculative Git diagnostic was run.

| Retained artifact | SHA256 |
| --- | --- |
| Fresh pre-finalization backup | `3bc90d4d52775e8d3ae3de44bdebed08e006772aefad062c2b81bdea8f97fbcb` |
| Completed post-shutdown backup | `0b1b99a72359a25fd408bf71fea7aa9305c29dff8fe8f84961a8329fe6b78d95` |
| Completed job canonical afterimage | `ea7ef67adcdc2c0e480bd7fe874e885939838e525f9d58e94161a16d09de0574` |
| Unchanged verification | `0eac30b90dcf9da8a6bf2377a60cabbf0d6cf1edc8237b468887abca7e74a9b3` |

Private evidence is under the same session's `finalization/resume/`: exact decisions,
fresh remote review/CI, full snapshots, preflight, one-command receipts, backup, logs,
browser evidence and byte-identical `disabled-authority/`. Original authority copies,
original/observed workspace snapshots and manifest remain retained separately.

Stopped Runtime `e5d8a338fc1d321900cb077dd2bb0abbe12ea5035ee92dc124779dd48cd83f70`
and Executor `9cba24defa79151e0ef787263ba03296a733eab8c4e309c9d262877b63aad66a`;
Router `f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6` never started.
All exact full configuration fingerprints and images remain those in the pinned
[execution resource table and scoped stop commands](2026-10-30-r2-held837-execution.md#runtime-identities-and-scoped-shutdown).
Running DB `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8`,
observer `5d6b3e9b578745877f162f9c34e4413cc855a40a8c4281c32d3c6ed711b05411`,
HTTPS `d22a5bf0ef1adee16464c27ccab10bf3cf22dc7320fa65ed5a995fbd5ea4daf2`.
84 owned containers:3 running/81 stopped. No new containers or images.

## Timing, operational lessons and next safe action

UTC: revalidation13:57:39; exact restoration13:58:05; two workers Running13:58:09;
readiness13:58:25; completed reconciliation13:58:32; retained shutdown13:59:09;
terminal browser/reconnect13:59:37. Readiness3.884s and finalize7.576s monotonic;
durable execution remains47.583s. Review/decision waiting is separate from execution.
One initiating disposition relay in this continuation; zero additional interactive
prompts/authentication steps. The earlier finalization preflight had one explicit PM
boundary request. Owner active minutes remain unknown; no unattended-run claim.

Operational lesson: label exact filesystem snapshots by phase and distinguish content/
Git proof from directory metadata affected by supported read inspection. Preserve raw
snapshots; do not silently normalize unexpected preflight drift or generalize this
single exception. Index-lock causality remains unproven. A future non-mutating-inspection
investigation requires reproducible evidence and separate scope; no live experiment here.
The PM corrected its CLI instruction: `finalize` itself mutates; `--apply` belongs only
to `verify-held`. Operators must check the accepted CLI contract before invocation.

PM can now review finalization evidence and decide eligible task/evidence merge ordering
and release of the R2 hold. Neither PR was merged; no new baseline/admission is implied.
Authority remains disabled with original2026-10-31T08:00:00Z expiry, no renewal.
Optional PostgreSQL failures, VPN/LAN unknowns and old observer label limitation remain.
Final evidence-head CI is recorded in PR838 and the consolidated issue835 receipt.

## Historical initial preflight: blocked before mutation

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
