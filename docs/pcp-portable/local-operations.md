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
full source file manifest, exact diff, parent/branch, route, authority and lease.

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
at final PR head; eligible merge only after the retained pilot's frozen-main
binding has a legitimate disposition; postmerge suites; a separately scoped
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
