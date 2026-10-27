# PCP Local native Compose — GH-815 V5

V5 replaces the PCP-local DDEV lifecycle with native Docker Compose and an
isolated Docker test container. It reuses Router, Runtime, Executor, PostgreSQL,
CodexAdapter, durable admission/lease and GitHub delivery. Other managed projects
retain their existing stack-specific behavior. The legacy `.ddev` profile and
historical inspection/OCI artifacts are not this installation path.

**SOURCE preparation only. Host/LIVE is STOP.** V5 source approval does not
resume Physical Pilot V1 or authorize a new issue, credentials, build or service.
[Owner V5 approval](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6447953456)
requires a separate Physical Pilot V2 after reviewed merge and postmerge CI.
V1 stopped before installation because DDEV start implicitly changes the shared
`ddev-global-cache`, independently of project mounts and isolated HOME.

## Planning

From a clean reviewed source checkout:

```bash
bash scripts/pcp-local-trusted-bootstrap.sh --dry-run \
  --root /home/sonvh/pcp-local-new815 --instance pcp-local-new815
```

Planning writes nothing and calls no Docker/DDEV/provider command. The root
must be absent, directly under the operator's HOME, named exactly as the
instance, with no symlinks or overlap with the source checkout. Planning does
not inspect Docker collisions or certify physical feasibility.

## One-time preparation under a future physical permit

Required tools: Git, ordinary shell tools, Docker and native Compose. No Host
PHP, Python, Node, Codex, PostgreSQL or DDEV installation is required. Use the
normal Runtime Dockerfile, not the historical health-only inspection image.

The operator supplies `--apply`, root/instance, exact clean `--source-commit`,
and a new `--owner-approval` issue-comment URL. The script checks syntax, not
human identity; verify actual consent, expiry and resource gates independently.
Known source/V1 physical approval URLs are rejected. Explicit inputs:

- `--node-base node:22-bookworm-slim@sha256:<reviewed digest>`;
- `--python-base python:3.13-slim-bookworm@sha256:<reviewed digest>` (a concrete
  3.13 patch tag is also accepted);
- `--opencode-version X.Y.Z` (build dependency only, not pilot routing authority);
- `--postgres-image postgres:17-bookworm@sha256:<reviewed digest>` (or a concrete
  17 patch tag with digest). Verify the Debian image's PostgreSQL UID/GID 999
  and sole declared data volume before physical activation.

Bootstrap refuses ambient daemon/Compose overrides and any matching containers,
volumes, networks or local service tags. It serially stages committed inputs
and builds only the three existing services with unique instance/full-SHA tags,
records image IDs/logs/pins, makes a detached PCP-only source clone and copies
`profiles/pcp-local/docker-compose.local.yaml` into `instance/`. It generates
fresh internal tokens and independent database passwords inside one bounded,
networkless Runtime-image process, then exits **without starting services**.
No provider or GitHub credentials are copied or provisioned.

`instance/.env` contains instance/source/UID/image identities and an empty
`COMPOSE_PROFILES`. Mode-0600 service env files contain only each service's
credentials. DB alone receives the bootstrap administrator password. Runtime
receives the separate `pcp_runtime` connection string; Router/Executor receive
no database credential. DB also receives that role's password in its own
mode-0600 env file. The non-secret DB-only `initdb/01-runtime.sql` uses PostgreSQL
17 psql's `\getenv` and quoted variable interpolation to create a non-superuser
Runtime role owning only the fresh `pcp_local` database/schema. SQL contains no
literal passwords and is readable by DB UID 999; its private parent root remains
operator-owned. Never dump service env files or mount them in a test container.
Initialize existing Runtime/receipt/lease schema DDL later inside that owned
database; never call legacy recovery or import old DB state.

## Native platform contract

All four services use profile `pcp-local`, restart OFF, no published ports,
explicit CPU/RAM/PID limits and the `${instance}-private` bridge. The explicit
`${instance}-postgres-data` volume replaces the image's sole data-volume mount;
there are no implicit global or anonymous volumes in the configuration. The
bridge permits required reviewed provider/GitHub egress; it is not a firewall
or a separate Docker daemon. Verify actual peers and egress before activation.

Runtime has only read-only config, its workspace root and dedicated HOME. It
has no Docker socket, source root or publisher credential. Executor alone has
the socket group, PCP source/workspaces, private HOME and later scoped publisher.
PostgreSQL runs non-root with owned persistent data and private temporary space.
The platform requests 4 CPU/5 GiB; one serialized verification adds 1.5 CPU/1 GiB.
SOURCE does not establish hard limits for the shared builder, incremental disk,
installed image behavior or available capacity; those remain V2 physical gates.

A future operator must explicitly address all Compose inputs, for example:

```text
docker --host unix:///var/run/docker.sock compose \
  --project-name <exact-instance> --project-directory <root>/instance \
  --env-file <root>/instance/.env -f <root>/instance/docker-compose.local.yaml \
  --profile pcp-local <separately-authorized-operation>
```

Never use default project/directory/env discovery, legacy root hooks, DDEV start,
global lifecycle commands, global builders or old tags. Recheck all named resource
ownership immediately before each future mutation. Digest-pinned PostgreSQL and
exact built service IDs must be locally available; `pull_policy: never` prevents
implicit substitution. Physical pull/build permissions remain separate.

Inspection health requires original draft/path-null registration, inactive
baseline and all task flags absent. Stop only the owned Runtime before promoting
configuration; install the new approved immutable baseline, singleton registry
and activation coherently, then start dedicated `pcp_local_worker`. Do not expect
inspect startup with promoted config. No baseline is approved/activated by
bootstrap or source acceptance. Keep `bounded`/`isolated_clone`, one writer and
production/auto-merge OFF. The existing `ddev.enabled`/phase-list keys remain the
mandatory-verification API contract; for PCP they do not invoke DDEV.

## Mandatory offline verification

Activation must bind `verification_image` **equal to** the exact
`runtime_image_id` (`sha256:...`). Executor verifies image ID, source-revision and
instance labels, denies image-declared volumes/unexpected environment, and
snapshots only the admitted workspace's exact source content outside developer
access. Root `.git`, `.ddev`, virtualenv and cache contents are excluded. Snapshot
hash/manifest and actual selected test files must match, including on retry.

Executor creates one named container per job/content/phase with no pull, non-root
operator UID/GID, read-only root, network NONE, capabilities ALL dropped,
no-new-privileges, 1.5 CPU/1 GiB/no swap and PID limit 256. Its only bind is the
owned snapshot read-only at `/workspace`, nonrecursive. `/tmp` is private bounded
tmpfs; HOME/TMPDIR point there. No socket, Host HOME, publisher/provider/service
credentials, shared cache, DDEV utility or router is included. Image/container
identity is checked before start; an existing name is refused, never resumed.

The Runtime image already supplies `/opt/venv/bin/python`, pytest 8.4.1, PyYAML
6.0.2 and Git. The container checks that actual toolchain before invoking the
explicit configured test paths. Its entrypoint `/usr/bin/timeout` must also exist
in the reviewed image; it bounds execution even if the CLI disconnects. Tooling,
transport, timeout and resource failures are infrastructure failures. Both
mandatory phases must run and succeed with a positive passed count; disabled,
missing, all-skipped, zero-test or failed checks never PASS. Existing Runtime
records executed commands and passed/failed/skipped counts and exact diff/source.
No image/package build is done by verification. Physical tool compatibility
remains untested until the separately authorized pilot executes it.

## Failure, evidence and rollback

Partial bootstrap retains intent, logs, image IDs, source and data; retry refuses
partial/different inputs. Exact completed retry is a read-only acknowledgement,
not proof of health or unchanged files. Never rebuild/reset to hide failure.
Snapshots and stopped test containers are retained. Repeated names refuse replay;
changed-content repair uses a distinct content identity only when existing
Runtime authority permits it. A deadline/uncertain attach stops only the newly
created container ID after fresh identity verification, never foreign resources.
No test cleanup deletes volumes, containers, snapshots or images.

Later physical rollback disables intake and stops only proven newly owned IDs;
keep DB, lease/receipt, job, counters, diff and logs. No `down -v`, prune, reset,
global stop, old PCP replay or Chợ Nhạc access. A new physical permit must bind
accepted source, baseline, actual images/tools, one issue/model allowance,
subscription entitlement/credentials, resource enforcement, staged health and
real mandatory tests/Draft PR/four-suite CI/independent PM outcome. SOURCE tests
and health alone prove none of those LIVE outcomes.
