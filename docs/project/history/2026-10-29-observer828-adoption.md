# Observer828 adoption and successor preparation — 2026-10-29

Executed under [DEC-PCP-815-OBSERVER828-ADOPT-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6490872107).
One writer; no nested agents. Application source **51349be73b54ca2fb827a4becc30e00ba62acd7d**,
[accepted PR828](https://github.com/sonvhse06072/personal-coding-platform/pull/828),
[PM review5694269201](https://github.com/sonvhse06072/personal-coding-platform/pull/828#pullrequestreview-5694269201).
Reviewed/merged Git tree `eb700feb9e43f1b246d315476947e08d3106be78` matches.
[Postmerge CI40836381983](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40836381983)
executed structure1741/1 skipped, Runtime2540/134 skipped, Router132, Executor680:
**5093 passed / 135 skipped**. [Documentation PR829](https://github.com/sonvhse06072/personal-coding-platform/pull/829) is not a new application build.

## Result and evidence classes

**https://localhost:18443/dashboard** is available in `loopback_readonly` mode.
Open directly on the Owner machine: no login token/form/session/cookie. Other
local OS processes/users can read; this is the approved local-only exception.
Actual empty V4 state is "No admitted jobs", services not_checked/readiness
not_observed/quota unknown. No jobs or telemetry were invented to populate it.

| Class | Status | Executed evidence and limit |
| --- | --- | --- |
| SOURCE | PASS | Accepted SHA/tree/review/CI verified; three builds from that committed archive; application checkout stays clean/pinned. |
| FIXTURE | PASS |74 tests in the actual new Runtime image with network none: local auth, events/SSE scope/redaction, terminal timing, real recording/normalization/projected usage. Synthetic stores; not populated V4 or provider evidence. |
| PHYSICAL | PASS | Image content/modes/toolchains; non-root/read-only/noexec; immutable askpass; actual Nginx syntax/TLS/peer; real DB SELECT role and unchanged full rows/sequences. |
| PHYSICAL | PASS | Separate-container upstream refused/frontend403; header/Origin/control denial; own-host non-loopback probes had no connection. |
| LIVE | PASS | Fresh WSL Chromium, normal TLS validation, no injected cookies/token/form/session requests; six successful live polls, offline/reconnect, no page errors. Actual empty DB. |
| PHYSICAL | NOT TESTED | True second-machine LAN ingress. Own-host testing is not equivalent. |
| PHYSICAL | NOT TESTED | VPN ON/parity; current state not reconfirmed. Prior Owner-reported OFF remains historical. |
| LIVE | NOT TESTED | Provider/publisher entitlement, worker admission/recovery/publication. No credentials, dispatch or inference authorized here. |

## Release and provenance

Instance/root `pcp-local-adoption825-v4` / `/home/sonvh/pcp-local-adoption825-v4`.
Release `releases/observer828-51349be`; accepted application checkout `source/`,
separate from `/home/sonvh/pcp-observer828-adoption` on `ai/815-observer828-adoption`.
Private evidence `/home/sonvh/.local/state/pcp-observer828-adoption-v1` (0700).
Before mutation, exact old DB/pair/network/volume/configs and original pins matched;
available memory12.62GiB and all three measured backing paths had >20GiB free.

One actual sequential cached build each, new full-SHA tags
`pcp-local-adoption825-v4-{runtime,router,ddev-executor}:51349be73b54ca2fb827a4becc30e00ba62acd7d`.
No bootstrap rerun, old tag overwrite or label-only promotion. Combined committed
`services` archive SHA256 `78f1551f42c8da5a3cb8bfe222bfced58b49f19977b3d528ed12315c89728c99`.

| Service | Immutable image ID | Git service input tree |
| --- | --- | --- |
| runtime | `sha256:d7761e08e8f9318d38d948f1b3ea916825762cec45e47ead5f85c7567b5f586f` | `73066358c74f4a407a48e316e6b3fef517be0610` |
| router | `sha256:9f0d95058423067c82287976f8ecfed723f88e7cec17dddaf2aaea8e2ed8f46b` | `a8fe2fd51ab2bbd6046cbc6d88435ba043d99d83` |
| ddev-executor | `sha256:70a5d315c67199d01e470bf5921c8cf9a003c8ad2514d99b33173cd3546565c9` | `d599349233ae5e85ab46ac70105e0bb2c4286486` |

Exact reviewed pins: Node22-bookworm-slim digest
`de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d`, Python3.13-slim-bookworm
digest `93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5`,
Codex0.160.0/OpenCode1.19.4/DDEV1.25.4/Buildx0.37.0, UID/GID1000.
Archive ownership/symlink/secret/type checks and executable modes preserved;
only first FROM changed in private Dockerfile.local to its reviewed pin.
Build logs/archive/iid/context retained under release build/logs/artifacts.
These are operator-observed local build/content receipts, not signed OCI attestations
or acceptance of the unrelated parked H1b inspection-image provenance lane.

Offline packaging probes matched261 Runtime,29 Router,38 Executor shipped files
and executable modes. Runtime reports Python3.11.2/Node22.23.4/Git2.39.5; Router
and Executor Python3.13.18; Executor Docker20.10.24, Buildx0.37.0, DDEV1.25.4.
Actual rootfs writes and tmpfs execution denied. Packaged executable askpass at
`/app/app/github_askpass.sh` executes outside noexec tmpfs (username only; no secret).
All probes non-root/read-only/cap-drop/no-new-privileges/resource bounded, no
socket/source/credential mounts. Router/Executor worker services never started.

Retained diagnostic failures: readonly preflight assumed an IPAM Gateway key that
Docker omits, then separate local base tags that BuildKit does not require; actual
retained IPAM and exact digest builds were reconciled before mutation. Router
packaging initially expected examples/pytest.ini not shipped by its Dockerfile;
corrected to the actual COPY contract. The first dashboard harness missed
models.yml (10 failed/64 passed); accepted configuration supplied through stdin
into isolated tmpfs, then74 passed. No application repair or repeat build needed.

## Physical before/after and boundaries

Old source5ad/token mode → accepted51349/loopback_readonly. Only exact old
observer/frontend stopped; DB remained running. New Runtime binds namespace
127.0.0.1:18787 with `--no-proxy-headers`; host18787 publication removed. Frontend
shares its namespace, only host127.0.0.1:18443 published. Exact Host enforced;
frontend observed publication peer **192.168.64.1** in live `/proc/net/tcp`, never
broadened to its subnet. New observer env has no DASHBOARD_READ_TOKEN or provider/
publisher credentials; registry remains singleton/draft/inactive. No schema init.

Canonical sanitized before/after configuration diff SHA256
`156d75b44218681de44964b191a5080a5c6dddbdb997906d5a43e474ed443fc1`.
New Nginx config SHA256 `149fcd5e1678f2d65b3fcb2630c3db31a0f021c1eedeaafc187ad6eeb3b894a4`.
New private observer-env SHA256 `e32c5df8270f81ba0a0c447b9b727dafe549a737d298531eab9a5c7b42b7c5f6`.
Full configs/env are private; no passwords/tokens or private manifests published.
Old env/config/token/leaf/key exact copies retained and originals hash-equal.
Nginx image/cert/key and existing system/NSS trust unchanged; syntax and verified
TLS pass. No trust installation or global network changes. Leaf fingerprint and
precise stop/rollback commands are in [operations](../../pcp-portable/local-operations.md#actual-v4-https-observer).

Actual `pcp_dashboard_reader`: SELECT six observation tables, no superuser/create-
role/create-DB/write grants. Even after SET TRANSACTION READ WRITE, DELETE(false),
CREATE TABLE and nextval each denied SQLSTATE42501; probes always roll back.
All11 full table row sets and sequence values match before/after SHA256
`769faf639d8a973a68710527fc2af8a340b6dda71c4018226afab93c22fe9c74`.
All tables empty, no job/receipt/lease/usage counters created. Retained real V3
retirement proof/counters were not loaded, replayed or imported into V4.

Actual foreign Host closes connection; duplicate Host400; foreign/null Origin,
cross/same-site Fetch metadata and Forwarded/X-Forwarded/X-Real-IP403. Runtime
namespace controls/sessions/intake/retire/preview/OPTIONS403; frontend rejects
out-of-scope routes404. No Set-Cookie. Separate probe on the same V4 network:
bridge192.168.64.3:18787 refused; verified-TLS frontend403 both with correct
Host/Origin and with spoofed identity headers. Probe container stopped/retained.

Only identified own-host addresses tested: WSL172.22.16.140 refused18443/18787;
Windows172.22.16.1,172.19.128.1,192.168.1.61 timed out both ports. No subnet scan,
no second-machine claim. At08:04:33UTC the observer resolved DNS and verified TLS:
GitHub200, registry401, registry-auth404, OpenAI models401, all unauthenticated.
This proves transport only; no token/model call or provider entitlement. Current
VPN state awaited Owner confirmation; no state change requested/performed.

## Retention and exact resources

| Resource | Immutable ID | Final state |
| --- | --- | --- |
| V4 DB | `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8` | running, unchanged |
| New observer | `5d6b3e9b578745877f162f9c34e4413cc855a40a8c4281c32d3c6ed711b05411` | running |
| New frontend | `d22a5bf0ef1adee16464c27ccab10bf3cf22dc7320fa65ed5a995fbd5ea4daf2` | running |
| Old token observer | `41aabe0d4c63f23056bf4bd0a0fdeb4c0b91cfe6dc296f20f71f3f55db596823` | stopped, rollback |
| Old frontend | `3b5cc02c77e96847c2e04446e802c3ee20fbb770d30956f42c7911f3a3443cab` | stopped, rollback |

Network `4f39b2458e6bbb9cee83bcee01053d4022bc9e49aa4877f3815c1a1161d571d5`,
volume `pcp-local-adoption825-v4-postgres-data`, DB image
`sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27`,
Nginx `sha256:552e7481ca93ffccd046aa658dbbed22caefbc09c66fa7cd247cbb90b8a5c609` unchanged.
V4 total33: these three running,30 stopped. All22 original V3 exact IDs and four
retirement rehearsal resources remain stopped, restart policy no. Full scoped
inventory is private `final-retention.json`; old configs/token/images and original
before/after dumps/manifests retained. No resource deletion or foreign changes.
[Exact scoped shutdown and rollback](../../pcp-portable/local-operations.md#v4-shutdown-and-retention).
Rollback pair was preserved/checked, not switched back merely as a test.

## Successor decision packet — prepared, not installed

Private release `artifacts/` holds immutable mode0400 snapshots below. NEW revision
**pcp-local-successor-828-51349be-20261029**, source51349, statusDRAFT,
active_revision null. All50 protected paths exactly equal the accepted checker;
prior825 and827 revision definitions preserved unchanged. No approved baseline
rewritten. Installed instance/observer registries, autonomy and activation untouched.

| Artifact | SHA256 |
| --- | --- |
| `successor-828-draft.yml` | `d0cb78dd1f6e06a62719ae25c13f56c52f9415841b2f842d54e3c89a7d0debd1` |
| `project-baselines.pcp-local.yml.diff` | `f1910d060adca5e1f3df6b72733f4f8268c254b3a01e0e7603864b20e7df743d` |
| `projects-successor-draft.yml` (superseded, unsupported path) | `4593b2d51aa11a11b1de6beb96ce215e3fd1dbcaf56bcba64cdb4a122cb3c361` |
| `projects.pcp-local.yml.diff` (superseded) | `e3e6f8cc3373fdaa0ff725b4804a6ac0a1d0823a4c0a3706687d59a0105663a3` |
| `successor-image-bindings.env` | `c770f4ae79e0d3a4e1896facee19d74c128727783cfa2f4aee6b72f37d238f05` |
| `instance.env.diff` | `ceb1970f6fd741e076a6fd7abf6986fec946fbc521bd57a3bd24577823013710` |
| `successor-release.json` (superseded) | `82d690482dc35ea3acce9f0d4d8fdc61155ab5731195c2bf9be3c57e47ffce44` |
| `next-task-draft.md` | `7165385fa6d031d40dab1399704ee221e31eef8784da4a3f44d4768bd5876a24` |
| `projects-successor-canonical-draft.yml` | `88f878454b81af71f81bc4a90fc26428794f52039365852676ad8f9aad47bb2f` |
| `projects-canonical.pcp-local.yml.diff` | `89b2ce349ae5d1290909c851a3719f0403daeb87c51fe55befcd57a0623b6244` |
| `successor-release-v2.json` | `053ea5aa9cc3d7210cbb8a365a65972be0ffffaee56ed98892e51f0b102183e3` |

Registry delta: add the new51349 definition with the exact827 authority/reference
frame, retain both historical draft definitions; active_revision stays null.
Corrected project delta: path null → canonical
`sources/personal-coding-platform`, targeted/full
paths → `tests/test_pcp_light_evidence_summary.py`; registration/ddev/autonomy stay
draft/false/off. Image-env delta: source5ad →51349 and all three application image
IDs → table above; root/namespace/Postgres/UID/GID remain unchanged, profiles empty.
Full exact unified diffs are retained as named above, never applied. The existing
canonical5ad clone must first be retained before a later permitted source succession.
The alternate-path draft failed the actual Executor identity helper and is retained
as non-admissible; corrected canonical-path fixture passes. Baseline definitions
were not changed during this correction. Future source succession and worker
config/activation require their next execution permit.
No whole-Compose restart: it would also disturb preserved DB/observer resources.

Schema/config parsing PASS. Approved-baseline resolver correctly rejects the
DRAFT; concrete TrustedReaders constructor rejects missing operational delegation
before any executor/provider/DB request. These expected refusals establish that
preparation did not grant dispatch; they are not operational-readiness PASS.
Same-source image labels/IDs/Git input trees validated; no mixed-source waiver.

Additional admission seams, independently checked before final handoff:

- **SOURCE/FIXTURE:** the actual `_pcp_verification_image` helper with inspected
  image metadata accepts base51349 and rejects newer documentation base6a63f7d
  with `pcp_local_verification_image_identity_invalid`. Its rule is image revision
  == activation base_sha and verification_image == runtime_image_id. No image
  relabel/checker change: a newer main needs a separately reviewed matching
  build/binding decision. Merely regenerating the task body is insufficient.
- **SOURCE/FIXTURE:** `_pcp_identity` requires exactly the canonical source path;
  `sources/successor-51349be` fails, canonical path passes with fixture authority.
  No fixture approval is installed or presented as actual registration.
- **PHYSICAL/SOURCE:** actual V4 network peers are DB and observer828. The current
  worker allowlist permits only named coding-runtime/router/ddev-executor/db, so
  observer828 would cause `pcp_local_foreign_network_peer`. No worker observe
  request was made. Next PM permit must specify reviewed observer coexistence or
  a scoped scheduled observer pause; this session keeps the dashboard running.

These are remaining admission prerequisites, not tokenless-observer failures.
Private `admission-seams.json` preserves function results/actual network evidence.

Exact future task proposal (no issue created/admitted):

```text
<!-- coding-platform:pcp-remote-source:v1 -->
{
  "version": 1,
  "key": "pcp-local-evidence-summary-v1",
  "base_sha": "51349be73b54ca2fb827a4becc30e00ba62acd7d",
  "mode": "github_source_pr_only",
  "goal": "Implement a pure standard-library JSON evidence-summary CLI. Validate explicit SOURCE/FIXTURE/PHYSICAL/LIVE classes and PASS/FAIL/NOT_TESTED outcomes, required field types, duplicate IDs and one common full source SHA. Produce deterministic counts without promoting fixture evidence to LIVE. Accept empty lists; reject invalid inputs with nonzero exit. Add focused good/invalid/empty/duplicate/order tests and CLI examples. No network, subprocess, credentials, database, Runtime mutation or authority decisions.",
  "allowed_paths": [
    "scripts/pcp-light-evidence-summary.py",
    "tests/test_pcp_light_evidence_summary.py",
    "docs/pcp-light/evidence-summary.md"
  ]
}
```

Pure `verify_issue` accepted synthetic issue888 with this body hash; goal SHA256
`b3d8bbf7a58da8d15605d23670e02f4b3af9d2c966cdfdf8f45d424a41e47640`.
Synthetic owner/main values are fixture inputs, not live GitHub observations.
Acceptance includes good/invalid/empty/duplicate/order/source-mix cases, required
verification, exact Git tree/modes/single parent, recovery without model replay,
reconciled remote branch/Draft PR before uncertain publication retry and exact-head
CI/independent review. The2–4 allowed-path rule including a test is unchanged.

Remaining admission prerequisites, as one next WorkOrder: PM accepts physical
handoff and reviews a separately approved successor baseline/operational config;
resolves canonical source succession, image/base equality and observer/network
coexistence without losing old resources; records fresh ownership/reservation and expiring worker/Executor
activation; creates a real issue and re-reads exact trusted current main/body/goal;
provides scoped credentials only under that permit; proves readiness/schema/verify/
publisher behavior without a model before one clean authorized admission. If this
docs PR advances main, regenerate task base/body and separately authorize a
matching Runtime image/build-binding solution required by the existing checker;
do not silently advance baseline51349, relabel images or claim this preparation
already passes that gate. No use of old824 activation or result.
The historical retired job stays cancelled/incomplete_not_delivered, never delivered.

Local required root suite: **1742 passed**; `git diff --check`, relative links and
the two standalone stop/rollback blocks (bash syntax only) pass. Exact-head hosted
CI is recorded in this PR's validation receipt/checks. The unchanged trusted classifier treats the operations/checklist paths as full
scope; inspect actual execution/logs of all four suites at the final head.
Accepted application four-suite evidence is the distinct postmerge run above.
Developer has not self-approved or merged this handoff.
