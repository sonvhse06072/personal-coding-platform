# PCP Local Trusted Fastpath — GH-815 PR-A

**SOURCE implementation for review; physical installation and Codex LIVE are
STOP.** PR-A prepares an independent local instance. It does not dispatch a job,
activate a ProjectBaseline, start DDEV/PostgreSQL, or prove deployment health.
PR-B supplies the dedicated admitted execution path. The old portable installer,
root `.ddev` hooks, inspection-image/OCI workflows and legacy database are not
installation dependencies for this path.

Authority: [V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6438475541),
[V2](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6438904126),
[V3](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6440446016).
V3 retires legacy compatibility as a product requirement. Useful historical
input validators retain their own frozen fixtures; they do not gate this install.
Physical deletion of old resources remains a separately scoped operation.

## Source planning, available now

From a fresh PCP source checkout, run this standalone script (no host packages):

```bash
bash scripts/pcp-local-trusted-bootstrap.sh --dry-run \
  --root /home/sonvh/pcp-local-new815 \
  --instance pcp-local-new815
```

Planning checks repository identity, source/Codex pin and destination syntax,
prints the service/image plan, and writes nothing. It never calls Docker/DDEV,
reads credentials or claims resource availability. The destination must be
absent, its parent must exist, and neither path may overlap the source checkout.
Use a fresh root; do not reuse `/home/sonvh/pcp-local-b2f3` or consumed receipts.

## One-time preparation after separate physical delegation

Requirements: Ubuntu WSL2/Linux, existing Docker Desktop integration, DDEV,
Git and ordinary shell tools. No host PHP, Python, Node, Codex or PostgreSQL is
required. The normal Runtime Dockerfile includes Codex; `Dockerfile.inspect`
does not. Do not substitute the historical inspection image.

The future operator supplies `--apply`, the same root/instance, the exact clean
reviewed `--source-commit`, and a **new physical** `--owner-approval` issue-comment
URL. The URL records the delegation; this shell script cannot authenticate human
consent. SOURCE approvals are not physical permits. Also supply reviewed
`--node-base node:22-bookworm-slim@sha256:<digest>`,
`--python-base python:3.13-slim-bookworm@sha256:<digest>` (or a concrete 3.13 patch
tag with digest), and `--opencode-version X.Y.Z`. These values are deliberately
not guessed or resolved over the network by dry-run.

Apply performs only preparation:

1. Refuse ambient daemon/Compose/activation overrides and matching containers
   (including stopped ones), volumes, networks or local image tags. Docker query
   failure is STOP. Atomically claim a fresh root; never adopt existing data.
2. Archive committed service inputs, substitute only the pinned base in staged
   copies of the existing three Dockerfiles, and build unique instance/SHA tags.
   Use the explicit local Unix socket and built-in default builder; never select
   or create a global builder or follow an ambient remote Docker context.
   Pass the checked-in Codex pin, explicit OpenCode version and host UID/GID.
   Keep build logs, image IDs, input pins and source SHA. Compose consumes those
   exact image IDs with `pull_policy: never`, not global legacy tags.
3. Clone only PCP source locally under `sources/personal-coding-platform` and
   pin it detached. Prepare separate `workspaces`, `runtime-home`, `executor-home`
   and `instance` directories. The instance receives only the hook-free profile,
   PCP-only registries and model/routing config; it inherits no root `.ddev` files.
4. Generate fresh internal API tokens in one non-root, networkless, read-only
   Runtime-image container with only the fresh output directory mounted. Service
   files are mode 0600. No provider or GitHub credentials are copied/provisioned.
5. Leave Compose profiles empty, registry draft/path-null, baseline inactive and
   worker flags absent. No DDEV command, DB initialization, provider call or
   service startup occurs. A completed exact retry returns a read-only no-op;
   partial setup or changed inputs STOP and retain all evidence.

This is a practical reproducible **source/version and image-identity** workflow,
not bit-for-bit reproducibility or independent supply-chain attestation. Existing
Dockerfiles still resolve Debian packages and some Python transitive/range
requirements at build time. Retain logs and built image IDs; do not assume a
later rebuild yields identical bytes. External OCI signing/GHCR/SBOM research
is not a prerequisite for the accepted local development risk posture.

## Activation and one real WorkOrder remain separate

After PR-A/PR-B review, exact-head four-suite CI and postmerge verification, the
Owner can delegate one bounded physical pilot once. Before any DDEV start,
verify the exact DDEV project registration/name and freshly recheck Docker
collisions; preparation does not reserve DDEV's global name. DDEV's shared
router/network and ancillary images are not an isolated daemon. Account for
these shared dependencies without stopping, inspecting or cleaning foreign
projects. The install template publishes no PCP service ports.
[DDEV project commands](https://docs.ddev.com/en/stable/users/usage/commands/)
allow addressing a named project; never run lifecycle commands from legacy root.

PR-A's real Runtime image serves `pcp_local_inspect` health using the unchanged
startup implementation. That is a useful health stage, not an inspection-only
image or a worker. Router/Executor have explicit service dependencies and scoped
configuration; PostgreSQL is the fresh instance's DDEV `db`. Runtime cannot
start ordinary PCP execution merely by changing an environment flag: PR-B must
install dedicated admission/startup and preserve legacy SOURCE replay denial.

Later activation binds the singleton registry to the exact new source path and
approved delivery permissions, creates an approved immutable ProjectBaseline
revision at a known reviewed authority commit, and activates it separately.
Preparation never fabricates a revision or updates an approved revision in place.
Keep `developer_permission_mode: bounded`; broad `trusted_project` enablement
is not part of this scope.

Provider login belongs only in the new dedicated Runtime home; GitHub publisher
credentials belong only to Executor. Runtime/agents receive no Docker socket,
source repository mount, host HOME, host keyring or publisher credentials. Only
Executor receives the socket and source root; this remains a powerful capability
on shared Docker, not hard isolation. PR-B must verify the actual developer
credential/workspace boundary and admitted issue/model/budget/lease before work.
No source/fixture result proves that physical boundary or provider entitlement.
The PCP source clone retains tracked files, but its legacy `.ddev` is never the
platform instance; future job verification must use reviewed job configuration.

## Failure, retry and rollback

A failed build/setup preserves the root, logs, image IDs and intent. Do not retry
against a partial root, delete it automatically, overwrite tags, reset a database,
or create a replacement job. Diagnose the recorded failure first. A completed
retry is only a no-op receipt acknowledgement, not health or integrity attestation.

Preparation starts no persistent services, so its rollback is to leave the
prepared instance OFF. After separately approved activation, stop only the exact
new PCP services under the scoped operational delegation; preserve DB/jobs,
workspaces, source and image/log evidence. Removal of any root/image/volume needs
separate exact ownership/dependency checks. Never prune shared Docker, operate
Chợ Nhạc, or resume historical jobs as part of bootstrap.

## Acceptance

Focused tests use temporary source fixtures and strict fake Docker/DDEV commands;
no real Docker/DDEV/DB/provider calls are allowed. Required hosted CI runs root,
Router, Runtime and Executor suites at the exact PR HEAD. Physical health,
credential separation, real Codex issue-to-Draft-PR delivery and zero per-task
Owner interaction remain **NOT ATTESTED** until the approved pilot supplies them.
