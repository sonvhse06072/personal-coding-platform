# H1c offline DDEV installation plan (#795)

**SOURCE implementation for review; physical installation NOT AUTHORIZED.**
[Actual Owner consent #6394295965](https://github.com/sonvhse06072/personal-coding-platform/issues/795#issuecomment-6394295965)
approves `DEC-PCP-B22C1-H1C-CLEAN-DDEV-PLAN-SOURCE-V1`, subject to
[PM conditions #6394267432](https://github.com/sonvhse06072/personal-coding-platform/issues/795#issuecomment-6394267432)
and [implementation WorkOrder #6394309665](https://github.com/sonvhse06072/personal-coding-platform/issues/795#issuecomment-6394309665).
The [eight-part proposal](https://github.com/sonvhse06072/personal-coding-platform/issues/795#issuecomment-6393130053)
contains the research and prospective installation checklist. Source anchor:
`a97bb3fb4901a425a53743a37d818caea15a3b29`, after T1-only #804; no approved
ProjectBaseline revision has advanced.

## Scope and value

The smallest useful source change prevents installation plans from silently
inheriting legacy hooks, secrets and shared-resource privileges. It adds a
supplied-data validator, not an installer, service, Host wrapper or worker.
It uses Python stdlib and existing PyYAML only.

Exactly seven paths are authorized:

| Path | Authority / change |
| --- | --- |
| `profiles/pcp-local/ddev-install-plan.example.yml` | New protected draft data schema/example |
| `scripts/pcp-local-ddev-install-plan.py` | New protected offline validator |
| `tests/test_pcp_local_ddev_install_plan.py` | New synthetic/static tests |
| `scripts/check_project_doc_authority.py` | Protected; register the three new protected paths |
| `docs/pcp-portable/h1c-ddev-install-plan.md` | New protected technical plan |
| `docs/pcp-portable/README.md` | Narrative/source checkpoint |
| `docs/project/current-state.md` | Mutable T1, under 15,000 UTF-8 bytes |

Trusted main does not yet classify the three new paths. PM must manually match
all four protected paths with actual consent; a PR metadata check verifies
declared scope, not human identity. Existing A3 templates, registries/baselines,
legacy root `.ddev`/public/bootstrap, OCI/provenance checkers and pins,
Runtime/Router/Executor, CI and all foreign projects remain outside this diff.

## Immutable inputs and honest evidence roles

The strict JSON example is a YAML subset. It separates `expected`, `observed`,
`verification` and `authority`. The source snapshot is embedded **data**; the
checker never opens these four repository paths or runs Git:

| Reviewed input | Git blob | SHA256 |
| --- | --- | --- |
| `profiles/pcp-local/.ddev/config.yaml` | `525d2798dcd60ea745839b4f2f127d2b6e700ea4` | `b350c76fad14e88886bff3519f08050f1928a01da789c57be4ab254f22457b0f` |
| `profiles/pcp-local/.ddev/docker-compose.platform.yaml` | `95c41ce6c696488cac70354daa99116fc296c9bd` | `5dfb39789f89f8396917726e0515027fdc07433508fc00fc6add3e780b3a7a6b` |
| `config/projects.pcp-local.yml` | `9935771e9ef22c2f6b48f36a15c045a31d57e642` | `880383618e9a629f12e70932ed38a430bf2927e12e84e14c235b673b33c5f8ae` |
| `config/project-baselines.pcp-local.yml` | `21a0a97731643e3cec7b5786e118c5c49df79826` | `c5ffea92761c3bd9a8e6e0d3a5fa3437fd379582cbe1e7f653b4aef69aa39052` |

Exactly four regular `100644` entries are allowed. Their origin/commit claims
must match the frozen anchor and canonical repository, and their actual UTF-8
bytes must reproduce both Git blob identity and SHA256. Duplicate/extra/missing
entries, changed modes, reformatted bytes, unknown paths and repinned expected
values STOP. Only exact accepted YAML reaches `safe_load`; arbitrary supplied
YAML, aliases or tags never reach that parser.

`SUBMITTED_PINS_ONLY` means the submitted byte identities match reviewed pins.
It does **not** verify a Git commit object's membership, actual checkout
origin/cleanliness, filesystem topology, producer identity or Host state.
Self-reported `clean`, signer and Host-ready fields are not accepted proof.
Tests separately compare the example bytes/hashes with the unchanged checked-in
source files. No live checkout or Host metadata is probed by the CLI.

## Parked contract and cross-project threat model

The fixed PCP-only DDEV project remains `pcp-local`, with no hooks and only the
optional `pcp-inspect` service. The unresolved image, non-runnable command and
`pull_policy: never` remain intact. Draft project `path:null`, false autonomy,
disabled DDEV and `active_revision:null` remain unchanged.

The parked Compose deliberately uses `${DDEV_UID}:${DDEV_GID}` and
`HOME=/home/coder`; H1b3 image policy requires `65532:65532` and `HOME=/tmp`.
The validator reports `PARKED_USER_HOME_MISMATCH`, not runtime UAT readiness.
A supplied effective config is accepted for structural comparison only if it
matches the entire parked graph, including values. New web/DB services,
images/builds, ports, env, mounts, command, user, privilege or profile overrides
STOP. Even a plausible active image/config requires a future protected successor.

One existing WSL2/shared Docker Desktop is the selected architecture. Names,
labels, directories and per-project networks do not isolate daemon privilege.
Root `.ddev` includes old image-builder/Antigravity hooks, extra services and
credential/socket mounts. Copying two template files over that directory leaves
other overrides available and dirties immutable source. Root `public/index.php`
also advertises unavailable legacy services. No such overlay/copy is performed.

Official DDEV v1.25.4 research shows lifecycle effects beyond a custom service:
startup can acquire Buildx, generate config, create DB/snapshot/global cache
volumes and replace the shared router. Compose rendering writes files, and
stop can run hooks/change router state. The referenced version is a research
anchor, not an installed-version observation or upgrade permission.

The checker rejects supplied inherited env, extra files, any candidate resource
collision/unknown owner, extra effective services and shared effects. This
includes stopped/unlabeled resources, DDEV registrations, global router/cache,
networks, images, ports, SSH/provider homes, legacy hooks/addons/commands,
Compose/Docker overrides, worker flags and old DB/jobs/leases. Empty arrays mean
**no supplied evidence**, never proof that the Host has no resources. Actual
Host ownership, consumers, hosts/cert changes and image availability remain unknown.

## Future layout, phases and journal

No paths or directories are created. Proposed layout beneath a future
Owner-chosen installation root:

- `source/<reviewed SHA>/`: canonical immutable source; never a DDEV launch root.
- `instance/`: minimal reviewed launch files and inert public content, no full
  repository copy; exact draft registry copies, no credentials or legacy state.
- `evidence/`: private ownership/phase metadata outside container mounts.

All actual roots/IDs/proofs start null. Supplied paths are checked lexically
using `PurePosixPath`: no relative/Windows/network/system paths, traversal,
symlink declarations, sibling-root overlap or ancestor/descendant foreign-root
collision. A plausible layout still STOPs `HOST_LAYOUT_NOT_ATTESTED`; a boolean
exclusive-owner claim cannot attest filesystem absence or ownership.

| Prospective phase | Required later gate; current result |
| --- | --- |
| SOURCE_INSPECT | Submitted source consistency only; overall STOP |
| HOST_PLAN_RO | Separately authorized minimal physical ownership/version/collision proof; STOP |
| SOURCE_PROVISION_APPLY | Separately reviewed private-source provisioning, new exclusive root and exact frozen payload; STOP |
| RENDER_REVIEW | Explicit writing phase with generated/effective config evidence; STOP |
| FIRST_START_BASE | Verified OCI prerequisite plus ancillary web/DB/router/tool images, global effects and resource/egress approval; STOP |
| FIRST_START_INSPECT | Protected active successor, effective runtime values and scoped health-only start permission; STOP |
| HEALTH | Bounded loopback GET /health inside exact new inspection container, no agent/job/provider/DB access; STOP |
| ROLLBACK | Exact proven-new container IDs and separately approved bounded stop; preserve DB/artifacts; STOP |

The prospective idempotency key binds the fixed source SHA, four input pin
records, project, exact root, fixture install ID and plan revision. An unsigned
null-root **SOURCE_INSPECT-only** receipt may compare byte-identically and
produce `NO_OP_PROPOSAL`; this is no executed phase or authoritative journal.
Operational phases, partial state, root/revision/key/previous-key drift and
replay reject. No source record can create/start/retry/stop anything or reset
consumed execution budget. Complete real Host journaling remains unimplemented.

Rollback metadata never grants ownership. Requested IDs missing from claimed
new IDs reject; foreign/shared consumers reject; even matching self-claimed
new IDs/proof remain `ROLLBACK_NOT_AUTHORIZED`. No global DDEV stop/delete,
prune, `down -v`, DB reset/migration/import, network removal or generic cleanup.
Future rollback preserves new DB, files, images, volumes and evidence; unknown
state must be retained. PostgreSQL's system initialization is not application
data migration. No legacy data is inspected or adopted.

## Bounds, API and unresolved #800 prerequisite

Only `--check` and one optional explicit plan data path are accepted. No
prepare/apply/render/start/stop/rollback flags, subprocess, Git/Host API,
network, signer, credential access or plugin adapter exists. The explicit
data file uses one no-follow/nonblocking open, regular-file check, bounded read
and before/after metadata check. No broad enumeration or mutable path reread.

Enforced input bounds: 256 KiB JSON, depth 20, 12,000 nodes, 64 KiB strings and
256-character keys; fixed source inventory and strict schemas. Duplicate keys,
YAML syntax/tags/aliases, floats/non-finite/huge numbers, cycles, unknown fields
and injected successful verification/permits reject. Errors print fixed codes
without paths, IDs, environment values, tokens or foreign data.

Host CPU/memory/disk/egress/time limits, observed usage and enforcement proof
remain null. Supplied overrun/timeout claims reject; even internally plausible
numeric reservations reject as unenforced. `observed.deadline_seconds` denotes
claimed consumed wall time for the same prospective limit, not a real clock
measurement. No build timeout/quota/egress/cancellation monitor is installed.

#800 still lacks an independently authenticated producer/external trust root,
real image/export/import compatibility, privileged builder/no-local-fallback,
worker/scanner/tool pins, hard disk/egress and shared ownership/cancellation
proof. The H1b3 fixture profile also excludes ordinary OS-layer layouts.
H1c does not provision/accept an image, override that policy or authenticate a
producer. DDEV ancillary images/builds are separate unresolved inputs.

The coherent example can report `PCP_H1C_STRUCTURE=PASS`, while **every CLI
invocation exits 2** and reports `PCP_H1C_RESULT=STOP`, checkout NOT_ATTESTED,
parked User/HOME mismatch unresolved, OCI provenance NOT_VERIFIED,
`PCP_H1C_HOST_INSTALL=STOP`, `PCP_H1C_DB=STOP`, `PCP_H1C_LIVE=STOP` and
`PCP_B22C1_LIVE=STOP`. Missing actual trust/ownership is an independent protected
gate; it is not a task-counter continuation limit.

## Verification and handoff

Synthetic tests cover coherent parked input/config/receipt data; source
origin/commit/blob/mode/inventory drift; untrusted YAML blocked before parsing;
malicious effective values, inherited env, legacy extras, unknown/shared or
stopped/unlabeled resource ownership; fake/expired phase permits, OCI/Host
claims, paths, journal replay/partial state, resource overrun, unsafe rollback,
parser bounds and critical CLI STOP/exit 2/redaction. No test establishes Host
safety or an installed worker. Required local counts and exact-head hosted CI
are recorded in the Draft PR/T1 handoff.

PM independently reviews all seven paths/four protected consent references and
negative fixtures, writes COMMENT and checks four actually executed hosted
Structure/Router/Runtime/Executor suites on exact PR HEAD before expected-head
merge. Postmerge real4 on exact main belongs to PM. Keep the implementation PR
Draft until that review; developers do not approve/merge or activate Host.

The future one-time setup should reduce repeated Owner terminal work. H1c
inspection cannot poll issues/run tasks/publish PRs; no-per-ticket WSL depends
on separately approved B1/B2 credentials, trusted launcher, egress and worker.
#752 remains PARKED/no blocked-egress retry; #595 HOLD; G1/F2/T01/Guardian frozen;
Chợ Nhạc STRICT NO-TOUCH.

Source references: [DDEV config](https://github.com/ddev/ddev/blob/5da91aeb9ebab0b0e66171c450b72099308d332c/docs/content/users/configuration/config.md),
[Compose merge/profiles](https://github.com/ddev/ddev/blob/5da91aeb9ebab0b0e66171c450b72099308d332c/docs/content/users/extend/custom-compose-files.md),
[startup](https://github.com/ddev/ddev/blob/5da91aeb9ebab0b0e66171c450b72099308d332c/pkg/ddevapp/ddevapp.go),
[shared router](https://github.com/ddev/ddev/blob/5da91aeb9ebab0b0e66171c450b72099308d332c/pkg/ddevapp/router.go),
[render writes](https://github.com/ddev/ddev/blob/5da91aeb9ebab0b0e66171c450b72099308d332c/cmd/ddev/cmd/debug-compose-config.go),
[stop effects](https://github.com/ddev/ddev/blob/5da91aeb9ebab0b0e66171c450b72099308d332c/cmd/ddev/cmd/stop.go).
