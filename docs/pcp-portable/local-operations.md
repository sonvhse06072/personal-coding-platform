# Supported readiness, recovery and dashboard adoption

This is an operational source contract for the consolidation branch, not a
change to the Constitution, approved baseline or retained V3 authority.
GH-815 and GH-822 are implemented together because the view must explain the
new durable verification/commit/publication states. No new service/state store.

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

For a separately authorized observer deployment, use the reviewed Runtime image,
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
