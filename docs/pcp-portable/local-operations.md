# Supported readiness, recovery and dashboard adoption

This is the accepted operational source contract and V4 decision packet, not a
change to the Constitution, approved baseline or retained V3 authority.
GH-815 and GH-822 are implemented together because the view must explain the
new durable verification/commit/publication states. No new service/state store.

## Current PM-finalized #831 checkpoint

[PM6501364012](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6501364012)
accepted exact task head4161ba059002c7aaf3fd35a88e3b0b80065c62b7 in review5700617139.
One supported authenticated `/v1/pcp-local/pm-review` POST completed same job:
completed/pm_review_accepted, delivery_finalized=true, receipt delivered/gen3,
lease released/gen1. Full checkpoint/proof/audit/progress unchanged; counters1/2/1.
No new model, verifier run, delivery, execution, build, permit or SQL repair.
The original blocked/error/preimage history below is retained, not current state.

Only the existing Runtime/Executor were started, exact configuration checked;
Router remained stopped. V2 was restored byte-identically under the explicit
finalization decision, original expiry2026-10-30T14:49:39.238744Z unchanged.
After shutdown its active copy was moved intact to release rollback file
`disabled-recovery-permit-v2-after-finalization.json`; original V2 audit copy
`disabled-recovery-permit-v2.json` remains. Neither is active permission.

Dashboard https://localhost:18443/dashboard now shows actual completed state and
delivered/released ownership; trusted browser timer/provenance/reconnect passed.
Same46 resources retained,3 running/43 stopped. Exact worker/dashboard stop
commands below remain valid. PM alone handles hold closure, task-ready/merge/
postmerge and evidence merge; keep mainR and both833/834 unmerged meanwhile.
Do not invoke another recovery/delivery/finalization or activate fresh work.
See [final afterimages/hashes](../project/history/2026-10-29-recovery832-live.md).

## Pre-finalization #831 execution and no-replay checkpoint

[Execution6499496019](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6499496019)
and [binding disposition6500237978](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6500237978)
authorized the completed same-identity registration/execution/delivery. [Actual consolidated record](../project/history/2026-10-29-recovery832-live.md)
is current; the [accepted packet](../project/history/2026-10-29-claim-recovery832.md)
and [earlier claim-only receipt](../project/history/2026-10-29-successor831-live.md)
retain their original premerge/blocked history.

Main/repair R=`1f9b5d50a18a7b93e6a22c6191d59985d4d3892a`; original task/baseline/
verifier/Router S=`b97ade581fecad4db2146258e5ca02c3902189e0`. Baseline
`pcp-local-successor-830-b97ade5-20261029`, canonical S clone, original #831 body/goal
and three allowed paths remain unchanged. Runtime/Executor were built once at R;
observer at 51349 was not rebuilt/swapped. Scoped retained credentials were validated.

Same job `a8851f89dd3e4e582c697ec1fe6d8cdb` is **blocked / verified /
awaiting_independent_pm_review**, with receipt **running/gen2**, lease **active/gen1**.
One Luna/low invocation, two configured verifier phases 13+13 PASS, one delivery
attempt. Real [Draft PR #833](https://github.com/sonvhse06072/personal-coding-platform/pull/833),
head `4161ba059002c7aaf3fd35a88e3b0b80065c62b7`, branch `ai/a8851f89dd3e`;
[exact-head40898352672](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40898352672)
executed four suites: 5254 passed/166 skipped. No delivery retry, model replay or
self-approval. `delivery_finalized=false`; keep ownership until legitimate PM outcome.

### Consumed permit and exact first-start binding exception

Initial readiness failed because first Docker start changed only the optional
`HostConfig.OomKillDisable` JSON false→null on new Runtime/Executor containers.
Full original permit and pre-start snapshots were retained; no registration had
occurred. PM6500237978 explicitly authorized one successor after full same-ID,
original receipt/absent-side-effect, production-digest and two-stable-snapshot
checks. No global normalization, omitted fingerprint field, source repair,
replacement container or security/resource/config change was used.

Original permit bytes SHA256 `9133cf6a5995f019ccd3279c8f7fb452569b1961bf1406f28eadeaf3b042bc4a`;
successor `083637a98ba1a63925181830e0b003d439188d86ccbb42393a627e154195c330`.
The complete successor diff changed only decision/record and the two affected
configuration hashes. **Original validity remained 2026-10-29T14:49:39.238744Z to
2026-10-30T14:49:39.238744Z.** No renewal or extra 24h. Original activation remains
unchanged and disabled, expiry 2026-10-30T10:51:28.134568Z.

Both permits now reside intact in release
`releases/claim-recovery-1f9b5d50a18a7b93e6a22c6191d59985d4d3892a/rollback/`
as `disabled-recovery-permit.json` and `disabled-recovery-permit-v2.json`.
Private operator evidence is `/home/sonvh/.local/state/pcp-recovery832-live-v1`.
`prepare-successor-permit.py` was an earlier proposal with broader validity and
was **never applied**; it is superseded by PM6500237978 and the executed exact
`install-binding-v2.py`. Neither script grants future permission.

### Read, review and stop; never replay

Open **https://localhost:18443/dashboard** directly; no login/token/cookie.
It now projects the real job, verified fixed duration, reported-cost Unknown versus
estimate 0, and exact PR/CI. Its SELECT-only reader remains available while workers
are stopped. A stale observation does not authorize a retry. Read-only plan's
`model_invocations=0` describes that operation, not the job's historical one call.

The supported worker client remains `python -m app.pcp_local_task_queue` (default
plan); dedicated endpoints are documented in the accepted packet. Final plan was
`verified_delivery_only`, but delivery already has ci_success: do not call deliver
redundantly. No run-once/execute/reset/new issue/SQL lease release is appropriate.
Independent PM must first review #833 and its actual proof/CI, then separately govern
any supported `/v1/pcp-local/pm-review` finalization/merge and scoped worker/permit
restoration. Recheck current source, original expiry and consumed ownership. No
automatic chain of successor permits, no backup restore over consumed live state.

The exact R Runtime/Executor and reused S Router below are already stopped. If a
later stop acknowledgement needs reconciliation, inspect those exact IDs first;
this standalone block stops only the three approved workers and retains all data:

```sh
bash <<'SH'
set -eu
unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
timeout 90 docker --host unix:///var/run/docker.sock stop --time 15 \
  d6fb53f17809e9b11a0e82ecadd1e7c250c8183d84305645c66557cfea6fd285 \
  403553246e43f86b5b38918f3a287d26165654c3919dc5ae5be7543266d269fb \
  f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6
SH
```

V4 retains 46 containers, 3 running/43 stopped. DB/observer/frontend IDs and scoped
optional stop commands below are unchanged. Old S Runtime/Executor containers are
retained under `-retained-S-<first8ID>` names, not restarted. All V3/#824 evidence
and earlier restored-copy fixture resources remain untouched/stopped. No pruning,
volume removal, worker image rollback/replay, credential reset or baseline rewrite.
Future fresh work requires a separate immutable successor frame and ownership
resolution; current receipt and baseline are not a free slot.

The earlier restored-copy fixture remains separate, stopped, with restart=no:
`cc373616aff0b6a0143aca906ada559b87200ab4ea6a4f26d93c7a81ea5580c8`.
Its volume/private dumps/manifests are retained. If a later stop needs
reconciliation, inspect that exact ID before using the scoped command:

```sh
docker --host unix:///var/run/docker.sock stop --time 15 \
  cc373616aff0b6a0143aca906ada559b87200ab4ea6a4f26d93c7a81ea5580c8
```

## Readiness and schema

Before admission, authenticated `GET /v1/pcp-local/readiness` aggregates blockers
for all activation switches, scoped author/committer identity, schema/role rights,
actual Runtime test tools, trusted source/Router/Executor/publisher and non-model
provider account observations. The same check precedes receipt registration in
`run-once`. It invokes no development/evaluation model, registers no job and
runs no DDL. Missing schema does not silently initialize itself.

Install only the supported additive schema under the dedicated PCP database
owner, using the reviewed image and its scoped DATABASE_URL. This explicit
operator operation is separate from observation/startup. In an authorized owned
Runtime process, supply this Python through stdin (no credential on argv):

```python
from app.storage import Storage
from app.pcp_local_readiness import initialize_schema
initialize_schema(Storage())
```

The installer locks its schema operation and executes core, receipt, telemetry
and quota DDL in one transaction. Repeated installation is additive/idempotent.
It never calls `Storage.init`, planning/orchestration ensure, startup recovery,
job repair, legacy cancellation or receipt/lease reset. It verifies table and
sequence permissions afterward; an existing incompatible schema or wrong role
is a retained blocker, never a reason to reset/reinstall data. Runtime's role
needs SELECT/INSERT/UPDATE/DELETE on required tables and USAGE/SELECT on their
sequences; no superuser or cross-project grants are introduced.

Executor gives each new PCP job repository local identity `PCP Local
<pcp-local@localhost>`. Readiness verifies both author and committer construction.
Global Git configuration and Owner authorship are not imported. The publisher's
askpass script is now an immutable image input, executable from the read-only
application tree. It contains no credential and does not generate executable
files in `/tmp`. Readiness executes its username-only probe and reads repository
push permissions/PR access. No read-only check can prove a future GitHub write
will succeed; publication still reconciles actual remote results.

## Same-job recovery

Successful authoritative verification is persisted before Git starts, with the
full source file manifest, actual Git tree (including modes), recomputed exact diff,
parent/branch, route, authority and lease. The candidate identity is captured before
verification and compared afterward; it is never refreshed to accept drift. Both
normal commit and recovery validate the resulting tree and complete single-parent
list before marking execution verified.

- `held`: development outcome uncertain or no new complete proof. No replay.
- `verified_uncommitted`: known verified tree; delivery-only recovery may claim
  the same job through exact-row CAS before one commit attempt.
- `commit_uncertain`: commit intent persisted. Reconcile HEAD, sole parent,
  clean worktree, full manifest and exact cumulative diff. An unknown/absent
  commit remains blocked; never blindly retry it.
- `verified`: accepted local result and actual commit retained; publication
  uncertainty preserves metadata and reconciles remote branch/PR before retry.

The existing authenticated delivery endpoint owns recovery; there is no new
SQL reset API, generic resume or replacement job. Under the project operation
lock, receipt and lease rows are locked and checked, and the complete expected
job row must still match. No usage/counter field is rewritten. Duplicate/stale
recovery fails closed. Required CI and independent PM finalization remain intact;
only legitimate finalization advances the receipt and releases the lease.
Telemetry side-effect failure logs its class without raw SQL/secrets and cannot
replace the primary exception or fabricate acceptance. Failure-checkpoint errors
are attached to the primary exception rather than masking it.

The old held #824 job is a separately approved **Owner-assisted forensic
salvage**, not evidence that the new normal recovery ran in V3. Its original
failure, private before/after/evidence map and CAS journal are retained. This
branch is never hot-loaded into that installation.

## Connectivity

Readiness uses actual service/provider/GitHub requests and records the affected
service plus DNS/TLS/transport or HTTP failure. It has no VPN-presence or broad
`/1` route veto. Allocation conflicts must be established from actual intended
allocation/ownership evidence; a broad VPN route alone is not that evidence.
Retain the already working instance DNS configuration. No global, Windows, VPN
or shared-Docker DNS mutation is part of this source change. VPN on/off parity
has **not** been tested in this session.

## Read-only dashboard rollout packet (not deployed)

The existing `/dashboard` and session cookie are reused. PCP requests read only
PCP jobs/receipts/leases/events and existing quota observations in a repeatable
read transaction. No orchestrator/schema initialization, admission, model,
preview control or privileged action is reachable from the view. Foreign job
IDs fail closed. Existing event cursor/replay routes retain their read-only
contract; the PCP view refreshes a bounded snapshot every three seconds.
Unknown quota/cost/tokens remain Unknown. Missing auth, empty, blocked, stale,
offline and unavailable observations remain distinct. Local verification and
hosted CI have separate fields; links use the fixed repository and observed IDs.

Adoption prerequisites: independent PM review; all four hosted suites executed
at final PR head; eligible merge under the recorded PM disposition; postmerge suites; a separately scoped
image build and physical rollout. No such rollout or new pilot is authorized by
this source delivery. Keep the original V3 source/images/DB untouched.

The following is the retained **default token-mode** setup. The explicitly
authorized current local exception is documented under [Actual V4 HTTPS observer](#actual-v4-https-observer); do not use this older port/session example for it.
For a separately authorized default observer deployment, use the reviewed Runtime image,
singleton PCP registry, scoped read database access and a dedicated nonempty
`DASHBOARD_READ_TOKEN` in the service's private env file. Retain the existing
container isolation, mounts, DNS and other service roles. The exact additional
Compose settings for the Runtime are:

```yaml
services:
  coding-runtime:
    environment:
      PCP_RUNTIME_STARTUP_MODE: pcp_local_dashboard
      PCP_LOCAL_INSTANCE: ${PCP_LOCAL_INSTANCE:?}
      PCP_LOCAL_SOURCE_COMMIT: ${PCP_LOCAL_SOURCE_COMMIT:?}
    ports:
      - "127.0.0.1:18787:8787"
```

This mode starts no worker and needs no provider login or live activation.
It rejects all job/action/preview endpoints. No publisher credential is an UI
login. Session cookies remain Secure/HttpOnly/SameSite=Strict, so access must use
an approved **HTTPS** local reverse proxy/tunnel to the loopback upstream; plain
HTTP is not an accepted login path. Reuse the existing approved HTTPS ingress;
its host/certificate configuration is an explicit physical rollout prerequisite,
not an implemented/deployed endpoint in this PR. Do not publish port 18787 to
all interfaces. Configure the declared instance/source from the verified image
manifest, not arbitrary browser input.

Smoke after authorized adoption: health reports observation-only/not-checked
services; read login/snapshot works over HTTPS; action endpoints return 403;
inspect exact job/receipt/lease without changing them; disconnect the browser
and verify the job is unaffected. Stop only exact owned observer resources on
failure; retain data. Do not start #824 or another pilot as a dashboard test.

## Fixture evidence

`evidence/consolidation-dashboard/` contains labeled desktop/mobile screenshots
and a browser request/state report. The fixture reproduces the authentic
original held-job shape (213 local tests, no PR/CI) with synthetic observation
metadata. It is not connected to V3 and proves no physical rollout.

Reproduce with an already installed Chromium and optional developer Playwright:

```text
python scripts/verify-pcp-local-dashboard.py --browser <owned-browser-binary> --output <evidence-directory>
```

The runner intercepts all fixture HTTP, checks read authentication, renders the
held job at 1440/390 px, checks overflow/page errors and exercises empty,
waiting-auth, unavailable, stale and offline views. It starts no server, downloads
no browser and calls no real provider/GitHub/Runtime/DB endpoint.

## Successor release adoption packet — prepared, not authorized

The original generic sequence below predates merge. PR825 is now accepted and
V4 has executed the separately authorized non-model subset; see the concrete
V4 packet below for actual evidence and the remaining protected/LIVE gates.

The [PM disposition](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6477295524)
ends further V3 retry scheduling and lifts the main freeze solely for an otherwise
eligible reviewed merge. It changes no database row, activation, source binding
or baseline. Retain #824 as incomplete assisted-salvage evidence: job
`51a11aa704362d84ae5c7b70e85741f1`, commit
`7b3833bdb06e59aabcad31e4ad2aed4ac5d003ea`, last reported delivering/verified,
publication blocked, receipt running/gen2 and lease active/gen1. The one-call
allowance is exhausted. Never use its activation or release its lease to validate
the successor. No fresh physical inspection is claimed by this packet.

The adopting PM/operator must fill and retain one release record containing
accepted PR head, merged source SHA, final-head and postmerge CI run/job URLs,
successor baseline revision/approval, physical permit/expiry, exact new instance
and root, pinned base digests/tool versions, three built image IDs, source/config
hashes, named resource ownership, resource capacity, HTTPS origin/certificate,
and the scoped validation job/issue identity. Missing values are STOP, not
permission to reuse historical values. This source candidate grants no build,
start, credential provision, activation, replacement-job or production authority.

1. **Accepted source and baseline.** Independently accept PR #825 after all four
   hosted test steps execute at its final head; PM alone handles eligible merge.
   Verify postmerge suites, clean checkout and exact merged SHA. Create and
   approve an immutable successor ProjectBaseline at that SHA through the normal
   authority process. Preserve the old V3 baseline definition and source pin.
   A new main or a green PR is not baseline approval. Resolve the retained active
   reservation through a separately approved ownership decision before any new
   work can be admitted; do not route around it with a replacement job.
2. **Build and source binding.** After a separate bounded physical permit, use
   `scripts/pcp-local-trusted-bootstrap.sh` from the clean accepted source with
   `--apply`, a fresh `--root "$HOME/<new-instance>"`, matching `--instance`,
   `--source-commit <merged-full-SHA>`, `--owner-approval <new-physical-comment>`,
   `--node-base node:22-bookworm-slim@sha256:<digest>`,
   `--python-base python:3.13-slim-bookworm@sha256:<digest>`,
   `--postgres-image postgres:17-bookworm@sha256:<digest>` and
   `--opencode-version <reviewed-pin>`. Run the standalone script, not a pasted
   mutating block in an interactive `set -e` shell. Its service-only `git archive`
   inputs, serial builds, full-SHA tags, source/instance labels, `.iid` files,
   `logs/build-inputs`, detached source clone and `prepared` receipt are the
   binding record. Preserve partial roots on failure; never reset/reinstall.
   Verify labels AND exact IDs against that record, source clone HEAD/cleanliness,
   singleton registry and successor baseline. Set activation `verification_image`
   equal to the exact Runtime image ID; never rebind V3 images/config.
3. **Scoped readiness.** Inspect only the newly named resources and validate
   capacity, owned network peers, mounts, nonrecursive bind and private tmpfs
   configuration. Retain the Docker20/nonrecursive and accepted tmpfs corrections.
   Start only separately permitted resources using the explicit Compose invocation
   in the README; bootstrap itself does not start them. Initialize schema using
   the schema-only Python entry above as the scoped owner, then repeat it and
   compare receipt/lease/jobs/usage before and after. Check table AND sequence
   privileges with the real Runtime role. Denied/missing prerequisites must appear
   together in authenticated readiness; restore only the approved prerequisite and
   require ready=true before admission. Readiness must create no job or model call.
   Check repository-local author/committer identity in a disposable owned job
   repository without changing global Git config.
4. **Publisher packaging.** In the exact Executor image, verify
   `/app/app/github_askpass.sh` is a regular executable mode 0755 from the accepted
   archive and that `/app` is immutable. With the actual private `/tmp` mounted
   noexec, execute only its username probe (`Username for HTTPS`) and require
   `x-access-token`. Never print the password probe with real credentials. Check
   scoped repository push permission/PR read access via readiness, then retain
   actual publication evidence in step 6. Source execution of the helper alone
   does not establish container/mount behavior.
5. **Authenticated observer.** Use `pcp_local_dashboard` and loopback port 18787
   settings above, a dedicated read token, scoped SELECT access, and the approved
   HTTPS ingress. Record exact image/source/instance and HTTPS origin. Verify
   unauthenticated snapshot/events reject, session is Secure/HttpOnly/Strict,
   foreign IDs reject, control routes return 403, and worker/model/schema counters
   do not change while polling/reconnecting. Compare projection to scoped stored
   rows: terminal outcome remains terminal when old; terminal duration is a fixed
   durable observation or Unknown; legacy usage without provenance is Unknown.
   Input cache-miss tokens require consistent gross/cache observations (or a
   provable gross-input zero). Partial sums are
   labeled partial, bounded attempt history cannot prove totals, and estimates
   never become provider-reported spend. Observer startup does not require or
   renew a live activation. Physical HTTPS and VPN parity remain unproven here.
6. **Meaningful physical recovery and publication.** Use only separately approved
   disposable fixtures/new validation work with exact ownership and source. Capture
   preimages and original verification proof before fault injection. Exercise a
   normal commit; verified-uncommitted recovery; lost acknowledgement after a
   successful commit; and publisher response loss after branch/PR creation. Verify
   exact tree/modes, sole parent, original proof, commit, same receipt/job/lease,
   nondecreasing counters and zero additional model invocations during recovery.
   Reject content/mode drift, extra parent, stale row and duplicate recovery;
   reconcile remote branch/PR before any retry and prove no duplicate publication.
   An absent uncertain commit stays blocked. Retain remote branch SHA, PR number,
   exact-head CI and PM outcome separately from local checks. Finalization/lease
   release requires the existing legitimate PM path, never fixture SQL repair.
7. **VPN ON/OFF matrix.** Use Owner-selected existing VPN states without scripts
   changing global VPN, Windows networking or DNS. In each state record UTC time,
   actual Runtime/Router/Executor readiness, provider account metadata (no inference),
   scoped GitHub API reachability and authenticated HTTPS dashboard access. Record
   DNS/TLS/HTTP failure classes only; no token/header/environment dumps. A broad VPN
   route is not an allocation collision. If one state is unavailable, mark it NOT
   TESTED or FAIL with evidence rather than infer parity from browser fixtures.
8. **Rollback and retention.** Before changes record exact owned IDs/config hashes
   and secure database/source snapshots. On failure disable only the new activation
   and stop only the explicitly owned new resources; retain their data, images,
   failure journal and logs. Never prune, down-v, reset usage, release an unresolved
   lease, change foreign resources or automatically restart an old worker against
   newer source. Reverting source/images requires its own compatible baseline/data
   check. Rollback is not restoration of permission to retry #824.
9. **Clean subsequent validation.** Only after acceptance, postmerge CI, approved
   succession/adoption and legitimate ownership resolution, define a new bounded
   WorkOrder/issue and physical permit. Its outcome and metrics are a separate
   record. Do not close GH-815/822/824 as delivered on source CI alone, and never
   report that clean validation completed historical #824.

## V4 successor and admission decision packet

Original source/HTTPS authority: [DEC-PCP-815-RETIREMENT-HTTPS-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6488558812).
Owner chat direction was recorded through delegated PM, not fabricated GitHub
identity proof. [Integrated evidence](../project/history/2026-10-29-retirement-https-v1.md)
supersedes the earlier no-retirement/no-ingress proposal. Original
[adoption evidence](../project/history/2026-10-29-adoption825-v4.md) remains retained.

### Accepted source and successor binding

V4 observer now runs accepted PR828 source
`51349be73b54ca2fb827a4becc30e00ba62acd7d` under
[decision6490872107](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6490872107).
Independent review/merge/postmerge four-suite CI40836381983 passed. One actual
Runtime/Router/Executor build each from that exact source resolves the prior
mixed-source preparation gap without relabeling old images or changing checkers.
Only the observer Runtime is deployed. [Full immutable mappings and receipt](../project/history/2026-10-29-observer828-adoption.md).

NEW private `pcp-local-successor-828-51349be-20261029` is DRAFT, active_revision
null. All50 protected classes and prior825/827 definitions are preserved; no
installed registry changed. Exact registry/project/image-env diffs and the
three-path task body are retained in the release artifacts named in the receipt.
The prior [825 candidate](../project/pilot-successor-825-candidate.md) and
[827 packet](../project/history/2026-10-29-successor-observer-packet.md) remain
historical, never silently advanced to include newer code.

Successor operational configuration, approval/activation and admission still need
their explicit PM checkpoint. The corrected draft uses the Executor-required canonical path
`/home/sonvh/pcp-local-adoption825-v4/sources/personal-coding-platform`. Its existing
5ad clone is preserved; a later permitted succession must retain that preimage
before installing a fresh clone. The earlier alternate-path draft was rejected
by the actual identity helper in a fixture, retained and superseded. The accepted
build checkout stays in the release directory.
At that historical preparation checkpoint registration/ddev/autonomy remained
draft/disabled/off; the current831 section above records subsequent activation. PR829 was accepted
and merged2ff29; active observer source remains51349. Under
[decision6492648806](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6492648806),
the [one final rollout/readiness packet](../project/history/2026-10-29-observer-worker-rollout.md)
supersedes the prior recurring docs-merge/build proposal. Finish the bounded
observer/worker source correction first; its independently accepted mergeS defines
one stable main window through admission/delivery. Build final worker images once
atS, preserve observer51349, retain/replace the canonical clone only at that later
checkpoint. Exact Runtime image/task-base equality is unchanged. A real main
mismatch requires reconciliation, not task-SHA-only editing or image relabeling.

### Observer/worker binding at the next rollout

Optional `observer_binding` belongs only to private activation. Full observer/
frontend container IDs, immutable image IDs, observer source, network ID and
configuration fingerprints bind the accepted pair. No binding keeps the original
four-peer rule; unknown peers, malformed bindings or drift reject. Never fill this
field from HTTP request data or refresh a mismatched expected fingerprint.
Read-only Docker metadata validates the exact role/config/mount/port topology;
frontend shares the observer namespace and contributes no bridge endpoint.
The existing observer keeps serving `https://localhost:18443/dashboard` without
login. Routine observer pause is not the solution. Physical coexistence of the
new worker code is a later gate, not established by inspect fixtures.

Review private configuration/file hashes and SELECT-only grants separately:
Docker configuration fingerprints include private env values but do not attest
contents of host-mounted files. Keep those inputs under trusted operator custody;
never print complete env or secrets in diagnostics/PRs. Replacements require a
new reviewed binding. The packet includes exact current physical IDs, digest
procedure, scope limits and all final source/baseline/activation/task templates.

Both Runtime source/worker/operational switches and Executor's separate source
switch must be approved. `GET /v1/pcp-local/readiness` precedes the one later
`POST /v1/pcp-local/run-once`; run-once itself repeats readiness and records the
receipt before admission. The PM-bridge source-check route is intentionally
unavailable in dedicated worker mode; do not use it as an extra registration step.
All eight concrete trusted readers and same-job recovery remain mandatory.
No current SOURCE-session worker start, source succession, activation, credentials
or dispatch is authorized by this procedure alone.

### Reviewed retirement procedure

**Postmerge execution completed under [record6489438739](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6489438739).**
PR827 merged at `ea6fc0ac5dd101068bf4fe6f8f8813495cc529bf`; CI40827639082
executed four suites successfully. The [actual receipt](../project/history/2026-10-29-retire824-execution.md)
records one original APPLY, preservation and shutdown. The procedure below remains
the audit trail; do not repeat APPLY or start old workers from this document. Known historical target:

- Instance/root `pcp-local-pilot815-v3` / `/home/sonvh/pcp-local-pilot815-v3`.
- Job `51a11aa704362d84ae5c7b70e85741f1`, issue824, source
  `0c968dd99199c73f3fbc89c0b59da168844e8f73`, assisted commit
  `7b3833bdb06e59aabcad31e4ad2aed4ac5d003ea`.
- Last reported delivering/execution verified, receipt running/gen2, lease
  active/gen1; one development invocation and213 passing local tests. These
  are expected history, not refreshed observations or permission to adapt proof.

The PM execution record must bind the actual accepted source SHA, independent
review/postmerge CI, approving authority and explicit retirement decision/reason;
original DB container/image/volume/network IDs; full Runtime/Router/Executor IDs;
DB name/system identifier/OID/schema; private backup custody; rehearsal identities;
exact original manifest digest and permitted operation. A URL/digest alone is
not approval. The trusted operator verifies the real record and records that
verification in a separate 0600 approval file, outside agent workspaces. The
CLI checks custody and exact contents, **not independent human identity**.
No agent, dashboard or worker is given this capability or these credentials.

1. **Quiescence and backup.** Read/reconcile original IDs against retained V3
   inventory and PM record. Workers remain stopped and activation remains off.
   Start only the exact original DB if needed. Confirm dedicated PCP database,
   no unexpected writer/claim, and headroom. In an isolated operator shell with
   `umask 077`, create a 0700 maintenance directory and take a consistent DB-only
   archive; never overwrite an existing backup:

   ```bash
   (
     set -eu
     umask 077
     # V3_DB_ID and MAINT come from the verified PM execution record.
     test ! -e "$MAINT/v3-before.dump"
     docker exec "$V3_DB_ID" sh -c \
       'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
       > "$MAINT/v3-before.dump"
     test -s "$MAINT/v3-before.dump"
     sha256sum "$MAINT/v3-before.dump" > "$MAINT/v3-before.dump.sha256"
     docker exec -i "$V3_DB_ID" pg_restore --list \
       < "$MAINT/v3-before.dump" > "$MAINT/v3-before.contents"
   )
   ```

   Preserve original workspace/Git/commit and prior journals; no push, reset,
   image/source rebind or publication. A backup does not grant permission to
   restore over the original database.
2. **Private connection and source.** Use a clean operator checkout at the exact
   accepted SHA and a verified Python environment with reviewed Runtime
   dependencies. `connection.json` contains only `DATABASE_URL` with the original
   scoped maintenance role/database credentials (0600 in0700 directory). Do not
   put credentials in arguments, logs, Git or chat. The CLI forwards PostgreSQL
   bytes through a temporary private Unix socket and fixed `docker exec` command
   to that exact DB container's localhost5432. It opens no host TCP port, mounts
   no socket into Runtime and installs no service. Actual authentication still
   applies. Host bridge reachability is not assumed.
3. **Capture full preimages once.** The command is SELECT-only, no Engine or DDL:

   ```bash
   python scripts/pcp-local-retire-job.py \
     --connection-file "$MAINT/connection.json" \
     --plan-out "$MAINT/original-manifest.json" \
     --job-id 51a11aa704362d84ae5c7b70e85741f1 \
     --instance pcp-local-pilot815-v3 --database-container "$V3_DB_ID" \
     --worker "$V3_RUNTIME_ID" --worker "$V3_ROUTER_ID" --worker "$V3_EXECUTOR_ID" \
     --decision-id "$PM_RETIREMENT_DECISION_ID" \
     --reason 'Retain incomplete pilot evidence without claiming successful delivery.'
   ```

   `plan-out` refuses overwrite. Review EVERY job/receipt/lease field, original
   commit/proof/modes/parent/usage and expected generations. The printed manifest
   SHA256 hashes canonical JSON, not pretty-printed file bytes. Unexpected state
   is a diagnosis/PM reconciliation, not an opportunity to refresh expected proof.
4. **Restored-copy rehearsal.** Under the PM-bound new rehearsal namespace, use
   the same pinned PostgreSQL version/image and a new private volume/network,
   no published DB ports. Restore `v3-before.dump` with `pg_restore --exit-on-error
   --no-owner --no-privileges` to the dedicated copy; never original volume.
   Retain an explicit copy-to-backup hash mapping. Capture a SEPARATE rehearsal
   manifest/approval bound to copy cluster/OIDs/container and visibly named
   rehearsal decision, with identical original business preimages. The isolated
   copy has no producer; its reviewed stopped Runtime/Router/Executor placeholders
   must be inert, no credentials/workspaces/model. Also retain direct proof the
   original producers stayed stopped. Do not repurpose the original approval for
   another database. Rehearse dry-run/apply/exact retry, rollback and lost-ack
   reconciliation; assert original result/error/verification/commit/counters and
   audit preimages unchanged. Retain dump/manifest/output hashes, then stop only
   rehearsal resources; do not remove the restored evidence.
5. **Separate approval and exact dry-run.** `approval.json` has exactly these
   fields: `decision_id`, `action: incomplete_not_delivered`, `manifest_sha256`,
   `authority: owner_delegated_independent_pm`, `approver`, `execution_record`,
   `accepted_source`, `operator`, and `attestation` equal to
   `I verified the independent PM execution record and exact scope.` The operator
   supplies this affirmative attestation only after verifying the actual PM
   record; this is not a generated signature or a developer approval substitute.

   ```bash
   python scripts/pcp-local-retire-job.py \
     --connection-file "$MAINT/connection.json" \
     --manifest "$MAINT/original-manifest.json" --approval "$MAINT/approval.json"
   ```

6. **Apply once and reconcile.** After successful rehearsal/dry-run and exact PM
   checkpoint, repeat the same command with `--apply`. It requires the clean
   checkout HEAD to equal accepted_source, observes exact stopped workers and
   database cluster through Docker, and serializes with claim/admission/recovery.
   One transaction locks full rows, stores before-images/approval/outcome under
   `checkpoint.pcp_local_retirement`, sets job cancelled/incomplete_not_delivered,
   blocks and increments the receipt once, releases the exact lease without
   changing ownership generation. Result/error/proofs/commit/history/counters
   are preserved; no delete, new job, model replay or delivered receipt.
7. **Uncertain acknowledgement.** Preserve the original files. Rerun dry-run with
   the SAME manifest/approval to reconcile; exact committed postimages return the
   original outcome. A subsequent identical apply is idempotent. Drift, a different
   decision or later lease ownership fails closed. Never reset counters, double
   release or generate fresh expected proof to force acceptance. Rollback of an
   interrupted transaction leaves all rows unchanged. An already committed
   retirement is not undone by restoring the original DB or removing its audit.
8. **Retain and stop.** Take a scoped after-dump/audit receipt and compare preserved
   evidence. Stop only exact original DB maintenance and rehearsal IDs; original
   workers stay stopped. Keep all volumes/images/Git/backup/approval/manifests.
   PM records ownership resolution separately from successor baseline/admission.
   Historical #824 remains incomplete/not delivered forever.

### Actual V4 HTTPS observer

**Open https://localhost:18443/dashboard directly.** Active authentication mode is
`loopback_readonly`: no token, login form, session request or cookie. This explicit
Owner-approved exception is only for the successfully latched singleton local
read observer. Default/worker/control authentication is unchanged. Other local
OS processes/users reaching loopback can read; remote anonymous access is denied.
Fresh WSL Chromium with normal certificate validation passed polling/reconnect;
no injected cookies or ignored TLS errors. V4 now contains the real831 job and
retained ownership; [current LIVE receipt](../project/history/2026-10-29-recovery832-live.md).
The [observer adoption receipt](../project/history/2026-10-29-observer828-adoption.md)
records its originally empty database, not current job state.

Runtime image `sha256:d7761e08e8f9318d38d948f1b3ea916825762cec45e47ead5f85c7567b5f586f`
listens only on namespace127.0.0.1:18787 with `--no-proxy-headers`;18787 has no host
publication. Nginx shares that namespace and Docker publishes only127.0.0.1:18443.
Nginx image remains `sha256:552e7481ca93ffccd046aa658dbbed22caefbc09c66fa7cd247cbb90b8a5c609`.
Exact Host `localhost:18443` and frontend peer192.168.64.1 are enforced; actual
socket peer remeasured. No forwarded identity trust, Docker socket, source mount,
provider/publisher credentials or activation. Read-only/nonrecursive binds,
non-root UID1000, all capabilities dropped and noexec tmpfs remain enforced.

Current private configuration root (0700):
`/home/sonvh/pcp-local-adoption825-v4/releases/observer828-51349be/config`.
Nginx mounts only config/leaf/key, never issuer key or DB credentials. Exact
unchanged leaf SHA256 fingerprint:
`85:16:F2:09:1D:CC:D4:89:D3:C9:81:84:26:2C:61:64:B8:ED:7B:2D:75:9E:BF:57:CE:F5:43:A9:54:E6:92:C6`.
Existing mkcert issuer fingerprint remains
`39:9F:71:13:39:6C:35:5F:C5:9A:B2:54:09:72:54:31:44:32:D4:07:59:3A:45:43:35:DD:D6:8F:B9:73:D2:14`.
No CA, certificate or trust-store change in this adoption. The prior Owner NSS
import remains in effect; its exact removal procedure is retained in the
[historical HTTPS receipt](../project/history/2026-10-29-retirement-https-v1.md).
Do not ignore TLS errors or install global trust as a fallback.

Syntax-tested routes allow only dashboard/snapshot/scoped events/stream reads;
other paths404, Runtime controls403. Foreign Host/Origin/cross-site/forwarded
identity denied. Separate-container upstream refused and frontend403. Own-host
non-loopback ports refused/timed out; true second-machine LAN NOT TESTED.
Dedicated `pcp_dashboard_reader` retains SELECT on six observation tables, no
sequence use, table writes or schema creation. Actual three permission denials
and identical11-table/sequence hash verified. No schema initialization, workers,
model calls or synthetic rows. Event/SSE redaction/timers/usage fixtures are
separate from this actual empty database.

Rollback assets remain at `observer-https` and release `rollback/`, including the
old private read token. It is absent from the new observer environment/mounts.
Only if restoring the retained token-mode pair: read that token in a private local
editor, enter its password form, never URL/chat/Git/logs/arguments. That old mode
uses Secure/HttpOnly/SameSite=Strict cookies and supported session DELETE logout.
No login is needed for the current deployed observer.

### VPN, scoped credentials and next admissible task

Scoped Runtime subscription login and Executor publisher credentials are retained
privately in the stopped831 workers. They were validated and used only under the
finite831 execution decision; no fresh task is thereby authorized. Revalidate
entitlement/expiry at a later approved action; never copy V3/host auth or reset
credentials merely because the session ended.

Measure connectivity in the Owner-selected existing VPN state, timestamp DNS/TLS/
HTTP and actual authenticated dashboard results. Current/second-state results are
in the WorkReport; an unmeasured state is NOT TESTED. No global VPN/DNS/hosts change.
An unauthenticated provider403/421 is reachability evidence, not usable entitlement.

Corrected next proposal: a small pure-standard-library **evidence-summary validator**,
with exactly three allowed paths:

- `scripts/pcp-light-evidence-summary.py`
- `tests/test_pcp_light_evidence_summary.py`
- `docs/pcp-light/evidence-summary.md`

Input is a local JSON evidence list with explicit class SOURCE/FIXTURE/PHYSICAL/LIVE
and outcome PASS/FAIL/NOT_TESTED. Validate types/required fields/duplicate identifiers,
reject unknown classes/statuses and mixed source identities, then emit a deterministic
summary preserving counts and unknowns. No networking, subprocesses, secrets, DB,
Runtime mutation or authority decisions. Acceptance includes good/invalid/empty/
duplicate cases, repeatable ordering, nonzero exit for invalid input and no promotion
of fixture PASS to LIVE PASS. The document describes CLI format and examples.
This is a proposal, not code implemented or a job admitted in this session.

PM creates a fresh issue within the later approved stable-S window after the
baseline/reservation decisions and before task-bound activation/readiness, pins
exact accepted source/baseline, fetched body/goal hashes and
these three paths. `verify_issue` still requires2–4 paths including a test file;
the prior one-Markdown proposal is invalid and withdrawn. Use one writer and the
existing approved low-cost resource envelope. Require normal verification, exact
Git tree/modes/sole parent, reconciled branch/Draft PR, genuinely executed final-head
CI and independent PM acceptance. Publication fault injection needs its explicit
non-model validation substep and remote reconciliation before retry. This clean
validation stays distinct from historical assisted #824.

## V4 shutdown and retention

Current evidence: `/home/sonvh/.local/state/pcp-recovery832-live-v1` (0700).
V4 retains46 containers, three running/43 stopped. Original831 evidence remains
at `/home/sonvh/.local/state/pcp-successor831-live-v1`. The prior observer828 receipt
remains retained. All22 V3 and four retirement rehearsal containers stay stopped.
Retain old images/configs/token, original
backups/manifests and every stopped probe, including diagnosed harness failures.
No prune/down-v/reset, V3 restart or retirement replay. The accepted application
checkout and frozen ea6 maintenance checkout both remain clean and pinned.

To stop ONLY the current frontend, observer and dedicated V4 DB, first compare
these IDs with the receipt, then run this standalone process (not executed as
part of the successful keep-available handoff):

```sh
bash <<'SH'
set -eu
unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
timeout 90 docker --host unix:///var/run/docker.sock stop --time 10 \
  d22a5bf0ef1adee16464c27ccab10bf3cf22dc7320fa65ed5a995fbd5ea4daf2 \
  5d6b3e9b578745877f162f9c34e4413cc855a40a8c4281c32d3c6ed711b05411 \
  8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8
SH
```

Scoped rollback to retained reviewed token mode, only while DB is still running
and old configs/images match the retained preimages. This does not restore DB or
undo retirement. Run as its own process; halt on any identity/config mismatch:

```sh
bash <<'SH'
set -eu
unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
D=(docker --host unix:///var/run/docker.sock)
old_obs=41aabe0d4c63f23056bf4bd0a0fdeb4c0b91cfe6dc296f20f71f3f55db596823
old_front=3b5cc02c77e96847c2e04446e802c3ee20fbb770d30956f42c7911f3a3443cab
root=/home/sonvh/pcp-local-adoption825-v4
for file in observer.env nginx.conf read-token localhost.pem localhost-key.pem; do
  cmp "$root/observer-https/$file" "$root/releases/observer828-51349be/rollback/$file"
done
test "$("${D[@]}" inspect -f '{{.Image}} {{.State.Status}}' "$old_obs")" = \
  'sha256:0391589bf34d58a3e3a4aae326539e9c46833fd44da591d4b57ca89904c0b1e2 exited'
test "$("${D[@]}" inspect -f '{{.Image}} {{.State.Status}}' "$old_front")" = \
  'sha256:552e7481ca93ffccd046aa658dbbed22caefbc09c66fa7cd247cbb90b8a5c609 exited'
test "$("${D[@]}" inspect -f '{{.State.Running}}' \
  8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8)" = true
timeout 60 "${D[@]}" stop --time 10 \
  d22a5bf0ef1adee16464c27ccab10bf3cf22dc7320fa65ed5a995fbd5ea4daf2 \
  5d6b3e9b578745877f162f9c34e4413cc855a40a8c4281c32d3c6ed711b05411
timeout 30 "${D[@]}" start "$old_obs"
timeout 30 "${D[@]}" start "$old_front"
SH
```

Reconcile uncertain starts/stops with exact-ID inspect before retry. Verify trusted
HTTPS login/read behavior after rollback; never relax TLS or local restrictions.
Rollback switching was prepared, not rehearsed against the live DB in this session.

## Tokenless observer next adoption

[Decision6489495501](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6489495501)
supersedes the intermediate ea6-only Runtime build plan: combine the Owner's
local-auth change with the next reviewed Runtime adoption, avoiding two builds.
Completed under decision6490872107 at accepted51349; the current receipt above
records actual tokenless deployment. The procedure below is retained for audit,
not authority to rebuild/restart again. The decision additionally authorized one
Router and one Executor build from the same source, preparation only.

Before rollout require independent acceptance, merge, actual four-suite postmerge
CI and the PM image-adoption checkpoint. Use a clean checkout of that exact merge,
never floating main. Keep the frozen maintenance checkout at accepted827 untouched.
Create a NEW private build/evidence directory and full-SHA image tag; refuse
preexisting paths/tags. Reuse the reviewed bootstrap procedure's committed archive,
symlink/ownership/secret scan and executable-mode-preserving permissions, but build
each of the three application images once under decision6490872107. Do not rerun
whole-instance bootstrap or overwrite prior V4 source/config.

Exact reviewed pins: Node
`node:22-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d`,
Codex `0.160.0`, OpenCode `1.19.4`, UID/GID1000. Archive
`git archive "$ACCEPTED_SHA" services/runtime` to the new context; retain its SHA256.
Replace only the first Dockerfile FROM in `Dockerfile.local` with that Node pin.
Build using `docker --host unix:///var/run/docker.sock build --builder default`,
`--file "$CONTEXT/Dockerfile.local"`, `--tag "pcp-local-adoption825-v4-runtime:$ACCEPTED_SHA"`,
`--iidfile "$NEW_EVIDENCE/runtime.iid"`, labels
`org.opencontainers.image.revision=$ACCEPTED_SHA` and
`org.pcp.local.instance=pcp-local-adoption825-v4`, build args
`CODEX_VERSION=0.160.0 OPENCODE_VERSION=1.19.4 DDEV_UID=1000 DDEV_GID=1000`.
Retain build output privately. Verify label/image ID against actual archive inputs,
toolchain and immutable askpass modes, non-root/read-only/noexec/nonrecursive mounts.
No unreviewed image or label-only source promotion. Router/Executor additionally
use the retained Python pin
`python:3.13-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5`,
DDEVv1.25.4 and Buildxv0.37.0. The actual combined services archive and all three
image IDs are in the [new receipt](../project/history/2026-10-29-observer828-adoption.md);
there is no longer a mixed-source gap for this prepared release.

Applied observer input diff (private destination; old preimages retained):

```diff
 PCP_RUNTIME_STARTUP_MODE=pcp_local_dashboard
-DASHBOARD_READ_TOKEN=<private existing value; retain only in rollback custody>
+PCP_LOCAL_DASHBOARD_AUTH=loopback_readonly
-uvicorn app.main:app --host 0.0.0.0 --port 18787
+uvicorn app.main:app --host 127.0.0.1 --port 18787 --no-proxy-headers
--p 127.0.0.1:18787:18787
 -p 127.0.0.1:18443:18443
```

Keep the exact SELECT-only DB role/actual empty V4 DB, singleton PCP registry,
HTTPS certificate trust, immutable mounts and fixed project scope. No worker/
activation/schema/provider/publisher credentials or source hotload. Fresh observer
and frontend IDs must be recorded; old containers/config/token stay retained for
rollback. Only the final accepted source/image binding changes at that checkpoint.

Nginx continues sharing the observer's network namespace, reaches only
127.0.0.1:18787, and publishes only host127.0.0.1:18443. Applied server changes:

```nginx
# Preserve existing TLS leaf/key/protocols and noexec temp-path configuration.
# Measured current Docker publication peer: 192.168.64.1. Reverify gateway and
# peer on the exact next namespace; STOP on mismatch, never widen to a subnet.
allow 192.168.64.1;
allow 127.0.0.1;
allow ::1;
deny all;
if ($http_host != "localhost:18443") { return 444; }
proxy_set_header Host $http_host;
proxy_set_header Connection "";
# Do not add/trust Forwarded, X-Forwarded-* or X-Real-IP. Client-supplied values
# reach Runtime unchanged and are rejected there, even from a local peer.
location = /dashboard {
    limit_except GET { deny all; }
    proxy_pass http://127.0.0.1:18787;
}
location = /v1/dashboard/snapshot {
    limit_except GET { deny all; }
    proxy_pass http://127.0.0.1:18787;
}
location ~ "^/v1/dashboard/jobs/[a-f0-9]{32}/(events|stream)$" {
    limit_except GET { deny all; }
    proxy_buffering off;
    proxy_pass http://127.0.0.1:18787;
}
location / { return 404; }
# Remove the existing /v1/dashboard/session location entirely.
```

The gateway allowance is a verified Docker loopback-publication transport detail,
not a trusted request header or remote-user credential. Before acceptance prove
that a separate isolated probe container cannot reach upstream on the observer's
bridge IP and gets denied at frontend even with valid Host/Origin/spoofed headers;
probe LAN/host non-loopback addresses too. If Docker forwarding makes an external
peer indistinguishable from the allowed publication peer, **HOLD tokenless rollout**
and retain token mode; do not broaden allowlists or change global networking.
Actual cross-container and own-host probes passed in the new receipt. A true
second-machine LAN test remains NOT TESTED; source fixtures establish neither.

Run Nginx syntax and real certificate-chain/browser checks before switching.
With default TLS validation and a fresh browser profile/no cookies, opening the
existing URL must display/poll without a token/form/session request/cookie.
Verify offline/reconnect, sanitized event replay/SSE, foreign Host/Origin and
cross-site rejection, denied controls, unchanged DB rows/counters and real
SELECT-only privileges. Health probes inside the observer namespace must send
`Host: localhost:18443`. Native same-origin GET may omit Origin. Other local
OS users/processes can read this view; this is the explicit Owner-approved boundary.

On failure stop only the new exact observer/frontend IDs, retain their logs and
restore the retained reviewed token-mode config/images under the rollout permit;
no DB restore, V3 resurrection, trust-store or global VPN/DNS change. Report actual
active auth mode. VPN OFF evidence is retained; VPN ON remains NOT TESTED until
Owner selects it and real probes run. No provider entitlement/inference follows
from connectivity success.
