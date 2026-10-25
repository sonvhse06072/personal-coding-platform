# H1b3: offline OCI evidence SOURCE proposal (#800)

**SOURCE implementation for review; physical Host plan UNAPPROVED.** Decision
`DEC-PCP-B22C1-H1B3-CODEX-OCI-HOST-EVIDENCE-SOURCE-V1` covers source, tests and
one Draft PR only. [Actual Owner consent #6388248530](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6388248530)
accepts [PM conditions #6388172916](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6388172916)
and [WorkOrder #6388267083](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6388267083).
The research anchor is `main@7b8b2617973285365a6e4efe79b0d4e350ad64bf`.
No baseline revision or operational permission changes here.

## Exact source boundary

The nine changed paths are:

| Path | Authority |
| --- | --- |
| `profiles/pcp-local/oci-evidence-plan.example.yml` | Protected, new |
| `scripts/pcp-local-oci-evidence-plan.py` | Protected, new |
| `tests/test_pcp_local_oci_evidence_plan.py` | Tests |
| `scripts/pcp-local-image-provenance-plan.py` | Protected |
| `tests/test_pcp_local_image_provenance_plan.py` | Tests |
| `scripts/check_project_doc_authority.py` | Protected |
| `docs/pcp-portable/h1b3-oci-evidence-plan.md` | Protected, new |
| `docs/pcp-portable/README.md` | Narrative |
| `docs/project/current-state.md` | Mutable T1 continuity, <15,000 UTF-8 bytes |

All three new policy/tool/document paths are registered protected. The trusted
main-base authority checker cannot retroactively classify them on this PR;
PM must manually verify all five against real Owner consent and PR metadata.
The source recipes, parked Compose, root `.ddev`, CI,
registries/baselines, Runtime, Router and Executor remain outside this change.

## Immutable source/input ledger

`immutable_source_snapshot(expected_commit)` requires a full commit SHA, exact
current HEAD, canonical source root/origin, non-root operator, clean tracked and
untracked state, and absence of the existing Docker/worker override variables.
Read-only Git commands have sanitized environment, no shell, bounded output
and a 12-second deadline per child. Only `100644 blob` entries are allowed;
executable modes, symlinks and submodules STOP. Each blob's size and Git object
identity are checked. The application tree must remain
`314ceeddf4a9a3c39edb748e99e290d06b3e9188` (100 Python files).

The same frozen Git bytes determine membership, hashes and the in-memory TAR.
No working-tree path is read after hashing or sent as a build context. The
checkout is checked again before returning; head/dirty/origin drift STOP.
The immutable manifest and parked profile are read from that same commit.
The private Git-data reader alone issues no authority and performs no staging
side effect. Legacy pure byte helpers remain available for regression tests.

Actual locally generated source bytes reproduce the reviewed contract:

| Input | Identity |
| --- | --- |
| Source TAR | 103 regular members; 1,740,800 bytes |
| TAR SHA256 | `cb766b4845bcf77759f51e74041a4e0e379ab37a869eeb99bb0b682bdbcfc39b` |
| Dockerfile SHA256 | `bace204f3fae06449981d7e90a5bd90e789e456e5f2abee6bfb0856555aff70b` |
| Ignore SHA256 | `6e11a0630b755dcb3a5b027308ae0964642dc1d316217714388c4f843602af5e` |
| Lock SHA256 | `63361fbbe8b76e25c080ff86954822301439c62a5ea5635f865001814ce49ff7` |
| App content SHA256 | `33f73dd0064300d8a0945e81fa66c4ac7858999b9a3d685d33ba7b9ad12b1530` |
| Base platform manifest | `python:3.13.17-slim-bookworm@sha256:4cea12ab7d78a3312c85f8cab19b6971d4fe9704da25443986c0bc20a6678850` |

Tests generate the bytes before comparing these values, inspect every member
and content, and repeat with reversed input ordering. USTAR paths are sorted;
mode 0644, uid/gid/mtime zero, no links or extra input. Tests read HEAD's immutable
objects and verify this unchanged tree/inventory/hash contract, including in
shallow postmerge checkouts; they do not depend on historical commits being
downloaded. This is source-payload reproducibility, **not image reproducibility**.

The new example duplicates the 18 approved wheel name/version/SHA256 records
from the existing lock; a test compares every record with actual lock bytes.
Neither those published wheel hashes nor unsigned build materials prove that
pip consumed those wheels. A prospective supplementary producer receipt binds
the exact source SHA, TAR, recipe, ignore, app, lock, base and all wheel inputs
to the selected image plus provenance/SBOM statement digests. BuildKit does not
automatically emit that PCP-specific receipt. Its schema is proposed evidence,
not an installed signer, authenticated producer or new supply-chain service.

## Retained OCI layout and offline inspection

Retained OCI layout is the provisional transport. No registry/account is
provisioned; `--load` into a classic Docker store may discard attestations.
The source inspector accepts supplied data only; it neither exports nor imports
images. Its plan is strict **JSON (a YAML subset)** despite the `.yml` suffix:
duplicate keys, YAML aliases/tags, unknown sections and artifact-provided
trust-root/verifier/success claims STOP. Expected pins, observed data,
verification and authority are separate. Observed outputs, source release SHA,
producer, trust root, signature verifier and every Host phase permit start null.

The prospective graph profile is deliberately narrow:

1. Uncompressed USTAR envelope containing only `oci-layout`, `index.json` and
   `blobs/sha256/<digest>`. No extraction, traversal, duplicate names, links,
   directories, sparse/PAX/GNU extensions, external URLs or trailing payload.
2. Layout catalog `index.json` selects exactly one OCI image index. That index
   selects exactly one `linux/amd64` runnable manifest and one `unknown/unknown`
   attestation manifest. Catalog, selected index, image manifest and config
   have distinct recorded digest roles. An attestation platform never becomes
   the runnable image. Extra/nested indexes and unknown graph types STOP;
   graph traversal has fixed depth and no recursive reference following.
3. All supplied blob names, SHA256 values, sizes, media types and cross-links
   are checked. Config platform and ordered rootfs diff IDs match bounded
   plain/gzip layer bytes. Every blob must be referenced. Blob hashes are
   computed once to avoid repeated-reference CPU amplification.
4. Attestation annotations bind the runnable manifest digest. Exactly three
   in-toto v1 statements bind that same unique subject: SLSA v1 provenance,
   SPDX 2.3 SBOM, and the proposed PCP source-input receipt. Config and predicates
   cannot substitute for one another. Receipt sibling statement hashes match.
5. Provenance requires BuildKit build type, fixed recipe/local frontend request,
   base material digest/platform, nonempty LLB definition, source metadata,
   completeness fields and exact real-layer descriptor mappings. A claimed
   `mode=max` flag or min-only predicate cannot satisfy those checks. This is
   validation of max-shaped **submitted assertions**, not evidence of a real
   builder invocation. The pinned BuildKit documentation's `request=true`,
   `resolvedDependencies=false` example is modeled explicitly; it cannot claim
   complete pip resolution. SBOM contains the 18 pinned wheel versions with
   unique package IDs and complete DESCRIBES relationships; this is no
   vulnerability scan, executable file audit or proof of installed wheel bytes.

Enforced parser ceilings: envelope 32 MiB, each blob 8 MiB, each JSON document
2 MiB / 20,000 nodes / depth 24, 128 TAR members, at most 32 runtime layers and
16 MiB aggregate expanded layer bytes. Plain or single-member gzip only;
concatenated/truncated streams and decompression bombs STOP. These are fixture
inspection limits, **not sufficient to admit the real Python base image**.
Image layers with directories/links/PAX also STOP in this profile, including
ordinary OS-image layouts. Future real-export compatibility, safe link policy,
larger resource envelope and source changes require separately reviewed scope;
no actual BuildKit export or Host VERIFY UAT is claimed here.

The read-only data CLI accepts `--check`, optionally a plan path, optionally an
OCI TAR path. A single no-follow/nonblocking open checks regular-file identity,
size and metadata before/after the bounded read. Evidence paths/content are
never printed. No Docker/Buildx/network/process/signing/Host adapter exists.
The older source checker still accepts only `--check` and always exits 2.

## Three independent outcomes

| Outcome | Matching synthetic fixture | Meaning |
| --- | --- | --- |
| Integrity | PASS | Submitted bytes and narrow graph/ledger agree |
| Authenticated producer provenance | NOT_VERIFIED | No approved independent producer, external root or signature verifier |
| Image reproducibility | NOT_TESTED | No independent repeat build |
| Overall / Host / Runtime / LIVE | STOP / exit 2 | No operational permission, even if integrity passes |

There is no toggle, environment variable or mock verifier that can turn an
integrity result into authentic provenance. The future verifier adapter is
design-only. An Owner signature on self-reported metadata would endorse the
claim without independently proving production. CI green and SHA256 matching
are also insufficient. The private/FREE GitHub decision does not provide
built-in private artifact attestations; do not assume Enterprise capabilities
or introduce signing keys/workflows to fill this gap.

CLI outputs retain `PCP_H1B3_RESULT=STOP`, integrity separately,
`PCP_H1B3_AUTHENTICATED_PROVENANCE=NOT_VERIFIED`,
`PCP_H1B3_REPRODUCIBILITY=NOT_TESTED`,
`PCP_H1B3_HOST=NOT_AUTHORIZED`, `PCP_H1B3_RUNTIME=NOT_AUTHORIZED`,
`PCP_B22C1_LIVE=STOP`. Malformed/unsupported evidence never falls back to a
tag, cached local image, label, registry or weaker verifier.

## Host phases and enforceability: all unapproved

| Phase | Current result | Independently checkable future prerequisites |
| --- | --- | --- |
| PLAN_RO | STOP | Fresh exact resource/consumer/ownership inventory and scoped Owner read-only permission |
| BUILD | STOP | Approved builder isolation architecture, immutable worker/frontend/scanner pins, no fallback, exact input bytes, egress and resource enforcement |
| VERIFY | STOP | Retained complete graph, approved independent producer/signature verifier and external root; real export compatibility and negative UAT |
| ROLLBACK | STOP | Exact new resource IDs, ownership/consumer proof and tested bounded cancellation/stop; preserve all old images/DB/volumes/evidence |
| HEALTH | STOP | Separate inspection-service start/health permission, scoped config, no jobs/DB/providers and truthful degraded response |

The example's CPU 4, memory 4 GiB, disk 6 GiB, egress 2 GiB and 900-second
deadline are **prospective numeric ceilings / NOT_IMPLEMENTED**. The parser
does not enforce Host quotas, egress, redirects, cancellation or elapsed build
budget and rejects claims that it does. These values are no resource permit.

Unresolved: Buildx's tagged docker-container driver sets `Privileged: true`;
its image-pull failure can fall back to local worker images. A unique builder
name/cache/label does not isolate a shared Docker daemon or satisfy no-fallback.
Do not patch or invoke Buildx to hide that risk. Worker/scanner digest pins,
hard disk quota, endpoint/redirect/byte enforcement, guaranteed cancellation,
refreshed ownership and producer trust root require a new architecture/risk
decision and exact scoped phase approval. No generic cleanup/prune is allowed.

## Review and verification handoff

Focused tests cover actual Git-object canonical bytes, dirty/origin/head drift,
symlinks/submodules/modes/extra/missing blobs, one frozen snapshot, deadline and
output limits; synthetic OCI positive integrity and adversarial rehashed graph,
predicate/subject/material/ledger substitutions, min/max confusion, malformed
JSON/TAR/gzip, missing/extra bytes, output role confusion, fake ownership,
resource/expired phase permits and critical STOP/exit 2 cases. Tests use no
network, container, signing key or Host resources.

PM independently reviews the exact nine-path diff, all five protected consent
references and negative tests, then writes COMMENT. All four GitHub-hosted
Structure/Router/Runtime/Executor suites must actually execute on exact PR HEAD;
service skips cannot replace them. PM alone handles expected-head merge after
all gates and four actual postmerge suites. Until that review the PR stays
Draft; this document asserts no merge, authentic provenance or Host success.

#752 remains PARKED with no blocked-egress retry/bypass; #595 HOLD;
G1/F2/T01/Guardian frozen, worker LIVE STOP; Chợ Nhạc STRICT NO-TOUCH.

## Source references

- [OCI layout specification](https://github.com/opencontainers/image-spec/blob/v1.1.1/image-layout.md)
- [OCI descriptor specification](https://github.com/opencontainers/image-spec/blob/v1.1.1/descriptor.md)
- [BuildKit v0.34.1 SLSA v1 min/max structures](https://github.com/moby/buildkit/blob/v0.34.1/docs/attestations/slsa-provenance.md)
- [BuildKit v0.34.1 attestation storage](https://github.com/moby/buildkit/blob/v0.34.1/docs/attestations/attestation-storage.md)
- [Buildx v0.38.1 docker-container driver](https://github.com/docker/buildx/blob/v0.38.1/driver/docker-container/driver.go)
- [Docker attestation persistence limitations](https://docs.docker.com/build/metadata/attestations/)
- [GitHub artifact attestation availability](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/use-artifact-attestations)
