# PCP #800: remaining OCI acceptance gates and successor proposal

Status: **T3 research/evidence and unapproved ChangeProposal**, 2026-10-25.
This document grants no source implementation, producer, signing, Host or LIVE
authority. The accepted H1b3 implementation and its protected policy are unchanged.

## Outcome and scope

The current request to handle [#800](https://github.com/sonvhse06072/personal-coding-platform/issues/800)
resumes after SOURCE acceptance, rather than repeating PR #802. Canonical remote
`main` and the clean local source both identified
`4b2ff7472e201ab43876ef25a6f7d06b0b35354a` at this inspection. This is an
implementation observation, not a successor approved ProjectBaseline.

The [latest #800 PM outcome](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6392783715)
accepted [PR #802](https://github.com/sonvhse06072/personal-coding-platform/pull/802)
and explicitly left the issue OPEN for separately approved Host/OCI work.
The [continuity checkpoint](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6392825306)
retains that boundary. [Actual nine-path SOURCE consent](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6388248530)
does not authorize Host preflight, new tooling, signing keys, additional protected
paths or a new infrastructure design. The user request names the issue without
specifying a new protected operational decision.

Work in this continuation is limited to this T3 proposal and a compact T1
pointer. No executable, protected plan, profile, workflow, baseline or dependency
changes are included. No Docker/Buildx/registry/provider/DB/Runtime call, image
operation, credential access, Host preflight or Chợ Nhạc inspection occurred.
Repository Git inspection and public documentation research are source work.

## Exact source observations

| Reviewed source object at the anchor | Identity |
| --- | --- |
| Offline OCI inspector | blob `7bcfe7161cbd1596c47895f8b2bce360c65094b0` |
| Immutable source snapshot/checker | blob `44a38f61dc921d337603b3acf3f46a4a5ad93280` |
| Runtime application | tree `314ceeddf4a9a3c39edb748e99e290d06b3e9188` |
| Inspection Dockerfile SHA256 | `bace204f3fae06449981d7e90a5bd90e789e456e5f2abee6bfb0856555aff70b` |
| Dockerfile ignore SHA256 | `6e11a0630b755dcb3a5b027308ae0964642dc1d316217714388c4f843602af5e` |
| Wheel lock SHA256 | `63361fbbe8b76e25c080ff86954822301439c62a5ea5635f865001814ce49ff7` |

Recipe/ignore/lock hashes were recomputed from the clean anchored source. The
accepted source TAR contract remains 103 members / 1,740,800 bytes, SHA256
`cb766b4845bcf77759f51e74041a4e0e379ab37a869eeb99bb0b682bdbcfc39b`.
That TAR was not regenerated in this continuation. The Python base manifest
remains the checked-in `linux/amd64` pin
`sha256:4cea12ab7d78a3312c85f8cab19b6971d4fe9704da25443986c0bc20a6678850`;
no registry refresh or base config retrieval was performed.

The inspector intentionally enforces a 32 MiB outer archive, 8 MiB blob,
16 MiB expanded-layer aggregate and regular-file-only USTAR profile. Its runtime
environment matches exactly the six recipe entries; it grants no inherited-base
environment exception. It requires a PCP-specific supplementary source receipt
which BuildKit does not produce automatically. These are documented fixture
limits, not newly discovered bypasses or permission to loosen the policy.

An ordinary export therefore cannot be assumed compatible. OCI layers include
directories and links, and real base config/environment, export topology,
statement schema and scanner output need comparison with the selected producer.
[OCI layer specification](https://github.com/opencontainers/image-spec/blob/v1.1.1/layer.md)
supports the format distinction; exact Python-image contents remain unobserved.

## Decisions that must precede an executable Host plan

| Gap | Required evidence/decision | Current result |
| --- | --- | --- |
| Producer authenticity | An independently controlled producer and external root, exact signer identity, custody, revocation and offline verification policy | NOT_VERIFIED |
| Real OCI compatibility | Retained export from that selected producer, all descriptor roles, base config, inherited environment and attestation/receipt schema mapped to reviewed inputs | NOT_TESTED |
| Builder privilege/fallback | Reviewed bootstrap and cancellation design; immutable client/worker/frontend/scanner identities; no local-image fallback | NOT_APPROVED |
| Disk and egress | Enforcement outside the build worker, including redirects, byte ceilings and output/cache/temporary storage | NOT_ATTESTED |
| Ownership and import | Fresh scoped Host evidence, digest-consumer ambiguity handled, preserved full index and attestations across the actual transfer | NOT_ATTESTED |
| Health/DDEV | Separate permit plus #795 active-profile and UID/HOME reconciliation | NOT_AUTHORIZED |

The already accepted shared Docker Desktop direction does not itself approve a
privileged build worker. The previously researched
[Buildx v0.38.1 driver](https://github.com/docker/buildx/blob/v0.38.1/driver/docker-container/driver.go)
still contains privileged container creation and a local-image path after a
pull failure. Its tagged source was rechecked; the installed Host version was
not queried. A distinct builder name or a rootless image name cannot establish
a new isolation boundary.

[Docker's driver options](https://docs.docker.com/build/builders/drivers/docker-container/)
provide CPU/memory controls; that option set does not establish a hard disk or
egress-byte cap. Cache GC thresholds, free-space observations and a client timeout
cannot be substituted for those enforcement and worker-cancellation requirements.

## Recommended producer decision, with alternatives

**Recommendation:** first select an independently controlled producer outside
the existing shared Docker Desktop. Preserve one WSL + shared Docker Desktop
for the intended eventual consumer; this proposal does not mandate another
local distro or change the accepted deployment direction. An external producer
is only a candidate build location and requires separate architecture/security,
privacy and budget approval before provisioning or using it.

| Choice | Benefit and unresolved cost | Recommendation |
| --- | --- | --- |
| Independently controlled external producer; pinned public-key verifier with signing custody outside coder/worker | Avoids adding a new privileged builder to the shared local engine; requires named producer, secure signing integration and measured cost | Preferred direction for a detailed design, not permission to deploy |
| External producer with keyless identity and retained verification bundle | Avoids a long-lived signing key; needs exact issuer/workflow/source identity, roots, offline policy and private-repository disclosure review | Alternative after privacy and tool review |
| Shared local privileged builder plus separately trusted observer/signer | Retains local build location; must resolve worker privilege, real invocation observation, no-fallback, independent quotas/egress and cancellation | Not ready for an operational permit |
| Retain current HOLD | No new infrastructure, credentials, spend or operations | Default until an explicit successor decision |

There is no evidenced approved external producer or signing root to name today.
Do not invent an account, key fingerprint, tool digest, workflow SHA or quota.
Signing a user-supplied BuildKit JSON document authenticates an endorsement;
the signer must control or independently observe the actual build to authenticate
the claimed production. Verification must bind the approved producer and signature
to the artifact and expected invocation, as described by
[SLSA verification](https://slsa.dev/spec/v1.2/verifying-artifacts).

The private/FREE decision remains in force. GitHub's built-in artifact
attestations for private repositories require Enterprise Cloud under the
[current GitHub documentation](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).
No plan upgrade, public repository, transparency-log disclosure or signing
workflow is approved by this proposal. A remote Buildx driver is a possible
client transport, with explicit TLS settings in
[Docker's documentation](https://docs.docker.com/build/builders/drivers/remote/);
TLS transport alone does not authenticate build history or enforce its resource
envelope.

The business-value gate favors a single inspection-image producer and retained
evidence, without a new permanent registry, generic signing service or worker
framework. Measure one-time setup, recurring CI/storage/signing cost, verifier
maintenance and Owner interventions before committing that scope. No recurring
service or monetary envelope is accepted here.

## Future one-time PLAN_RO contract (design only)

Proposed decision family: `DEC-PCP-800-H1B3-PLAN-RO-V2`. This is distinct from
SOURCE consent and every BUILD/VERIFY/ROLLBACK/HEALTH permit. No operator command
is included for immediate execution.

The actual permit must bind an exact source SHA, reviewed inspector hash,
operator identity, expiry and one-use ID. It must name the allowed WSL/engine
context and PCP-only candidate resource identities before any query; unknown
or changing identity STOPs. Prospective maximum: 300 seconds, 10 seconds per
read-only subprocess and 32 KiB redacted report; no registry/provider request,
bootstrap, filesystem provisioning or Docker mutation. These bounds are not
implemented by this document.

The permitted report would cover source cleanliness, selected Unix context and
engine fingerprint, Docker Desktop provider, version-only client metadata,
`pcp-local` DDEV registry collision and exact PCP-only resource candidates,
including stopped containers. Do not run DDEV hooks or commands that can
bootstrap a builder. Builder collisions must be checked against approved exact
identities; do not adopt an existing builder or enumerate all builder contexts.
Do not read host Docker credential files or provider homes.

Queries must remain scoped to approved PCP candidates. A name/label match is a
candidate, not positive ownership. Unlabeled or foreign consumers that cannot
be safely established remain UNKNOWN; do not inspect Chợ Nhạc to resolve the
uncertainty. This means no shared image overwrite/deletion can be authorized
from a filtered count. Report only fixed classes/counts/fingerprints; keep raw
foreign IDs, mounts, paths and secrets out of GitHub. This read-only phase may
finish with controlled STOP and cannot grant BUILD authority.

## Build, verification and rollback acceptance contract

The prospective source/image chain is reviewed commit -> immutable Git blobs ->
canonical source TAR -> approved base platform + 18 hashed wheel inputs ->
authenticated producer invocation -> complete OCI graph -> external-root
verification -> separately permitted consumer/import -> HEALTH. Each arrow
needs actual evidence. BuildKit max provenance alone does not prove which wheel
bytes pip installed; the authenticated producer receipt must record that input
observation and bind the image, provenance and SBOM digests.

Retain a complete OCI-layout export and metadata with independently recorded
catalog/index/platform/config/layer and statement digests. Treat the supplementary
receipt as a signed sidecar if attaching it would rewrite the image index; a
future schema must specify which index is signed and avoid digest cycles.
Do not invent a BuildKit-native third attestation. Prove the actual transport
preserves both the runnable manifest and attached provenance/SBOM. Docker documents
that attestations attach to an index and the classic image store cannot retain
them; standalone `local`/`tar` exporter JSON is also distinct from an OCI image
graph. [Docker attestation storage](https://docs.docker.com/build/metadata/attestations/).

| Phase | Required permit and evidence | STOP/rollback boundary |
| --- | --- | --- |
| PLAN_RO | Exact one-use read-only permit and sanitized fresh report | Unknown source/context/ownership/version/collision -> STOP; mutate nothing |
| BUILD | Selected approved producer, complete immutable component pins, reviewed invocation/context, enforced resource/egress envelope, cancellation proof | Missing root/enforcement/pin or any fallback -> STOP before build; one attempt, no automatic retry |
| VERIFY | External verifier/root, retained complete graph and producer receipt, exact source/base/material/config/statement checks | Unsigned/unknown signer, mismatch, unsupported export, outage or incomplete offline roots -> STOP; preserve evidence |
| IMPORT | Separate exact consumer-store permit and index/attestation retention proof | No implicit load/tag or legacy-image fallback; reject changed digest/store semantics |
| ROLLBACK | Exact newly created resource IDs, creation journal and positive ownership/consumer revalidation | Unknown/pre-existing/shared resource -> preserve; no prune, broad deletion or old-stack stop |
| HEALTH | Separate #795-aligned start/health permit, image/config pin and no-worker profile | Localhost GET /health only; no jobs, DB, credentials, model or background poller |

The existing candidate envelope (4 CPU, 4 GiB memory, 6 GiB disk, 2 GiB egress,
900 seconds) is a proposal with **NOT_IMPLEMENTED** enforcement, not permission
to spend those resources. Include builder/scanner bootstrap, base/wheels,
temporary decompression, cache, output and retained evidence in a future ledger;
record network directions separately. A deadline must terminate the actual worker,
not just its client. Missing enforcement requires a new explicit risk decision;
do not silently relabel a measurement as a limit. These are security/resource
boundaries, not routine continuation gates based solely on task counters.

## Exact successor SOURCE scope, not approved implementation

Proposed family: `DEC-PCP-800-H1B3-REAL-OCI-SOURCE-V2`. Only after producer
selection and review of a separately authorized real export, the following
six-path compatibility change is the initial bounded candidate:

| Path | Existing class | Candidate change |
| --- | --- | --- |
| `scripts/pcp-local-oci-evidence-plan.py` | human_owner_protected | Bounded real-layout inspection; keep integrity/authenticity/Host authority separate |
| `profiles/pcp-local/oci-evidence-plan.example.yml` | human_owner_protected | Versioned real-export expectations and distinct receipt binding; retain null operational authority |
| `docs/pcp-portable/h1b3-oci-evidence-plan.md` | human_owner_protected | Explicit successor profile and pinned base-config/producer mapping; preserve accepted profile history |
| `tests/test_pcp_local_oci_evidence_plan.py` | tests | Real-shape and fully rehashed negative fixtures with documented provenance |
| `docs/pcp-portable/README.md` | narrative | Reconcile SOURCE/Host handoff and supported profile |
| `docs/project/current-state.md` | mutable_execution | Compact exact execution/checkpoint evidence |

This proposed list grants no edits. It includes no signer adapter, dependency,
workflow, registry, Dockerfile, wheel lock, parked Compose or baseline change.
Do not bolt cryptography or privileged operations into the compatibility parser.
A signature implementation or producer workflow needs its own exact-path SOURCE
proposal after the root/tool/custody decision. If the selected real export needs
a changed recipe, dependency or another path, revise the proposal before coding.

Layer link metadata must not turn into filesystem extraction or execution.
Consider hashing opaque compressed layer bytes and bounded streaming diff-ID
verification, rather than interpreting OS filesystem entries as source-context
members; source TAR must retain its strict no-link policy. Before allowing
inherited environment, independently pin and review the exact base config plus
the recipe overrides. Do not permit arbitrary extra environment to make a real
export pass. Unsupported compressors or excessive budgets still STOP.

Required future negative tests include wrong source/base/config/index/material,
min-as-max provenance, absent/substituted SBOM or receipt, full graph rehash after
unsafe command/User/env mutation, directory/link metadata without extraction,
oversize/decompression/depth/truncation/duplicate inputs and replayed phase permits.
A future authenticated-verification lane must additionally reject unknown or
revoked signer, wrong issuer/identity, signature/subject tampering, unapproved
workflow revision, artifact-supplied roots and offline/outage fallback. Code PRs
require all four actually executed hosted suites plus independent PM COMMENT and
expected-head merge; source fixtures never replace real producer/Host UAT.

## Current delivery and next safe decision

This documentation-only continuation changes exactly this evidence file and
`docs/project/current-state.md` on `ai/800-oci-next-gate-proposal`, delivered in
[Draft PR #807](https://github.com/sonvhse06072/personal-coding-platform/pull/807).
Local diff whitespace, relative-link, six-candidate-path/classification and T1
size checks passed; no protected path changed. It requests PM review, not
merge or operational approval. The trusted-main
classifier permits T1/T3 docs-only service-suite skips; root Structure and doc
authority remain required. Local system Python has no pytest; no package or Host
tool was installed to compensate. Hosted results must be reported separately.

**Next decision:** Owner/PM should select the producer direction above, then
record a named producer/root/cost design and exact SOURCE scope. A generic
"continue #800" or approval of this evidence PR cannot authorize Host actions.
PLAN_RO, BUILD, VERIFY, IMPORT, ROLLBACK and HEALTH each still require an exact
separate operational decision when their prerequisites exist. No presently
complete Host permit can be honestly offered while producer/root/pins/enforcement
remain unknown.

#800 stays OPEN; #795 Host/DDEV STOP; #752 PARKED with no blocked-egress retry;
#595 HOLD; F2/T01/Guardian frozen; Chợ Nhạc STRICT NO-TOUCH. Authenticated
provenance NOT_VERIFIED, image reproducibility NOT_TESTED, worker LIVE STOP.
