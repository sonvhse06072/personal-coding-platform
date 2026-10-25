# PCP portable install — B1.1 (fresh WSL2 install only)

**Status:** first-install source implementation. CI can test safety and the exact shell contract with **fake Docker/DDEV**. A clean physical/virtual WSL2 transfer and real start are **NOT YET ATTESTED**; do not call this production-ready or say PCP automatically accepts tasks.

## Prerequisites

- WSL2 Ubuntu (or compatible Linux), one working Docker provider and **DDEV**. DDEV is already the canonical PCP lifecycle manager and requires Docker. Git is needed to obtain source. A regular, non-root user is mandatory.
- No host Python, PHP, Node/npm, Codex CLI, OpenCode CLI, Antigravity CLI or local PostgreSQL installation.
- Fresh checkout under the Linux filesystem. The existing `scripts/bootstrap.sh` is the **legacy** installer and is not used for this portable mode. Do **not** run this installer on a current legacy instance, Chợ Nhạc tree, G0/F2 or old G1 workspace.

## Initial preparation and start

From a **new** clone of `sonvhse06072/personal-coding-platform`:

```bash
bash scripts/pcp-portable-bootstrap.sh --check     # read-only diagnosis
bash scripts/pcp-portable-bootstrap.sh --prepare   # private env and scoped secrets
bash scripts/pcp-portable-bootstrap.sh --start     # explicitly start DDEV
```

For a one-step first install after inspecting the source and accepting Docker/DDEV side effects, use only the last `--start` invocation. Subsequent normal startup is still `ddev start`. All commands run in a **subprocess**, not an interactive shell with imported `set -e`.

The preparation tool requires an absent `.ddev/.env` (fresh) or an already private portable-mode `.ddev/.env` with `PCP_ANTIGRAVITY_MODE=disabled` and exact Codex pin. A legacy setup, unexpected secret files, symlinks or stale pins **STOP**, never undergo automatic credential/ProjectBaseline migration. It produces only its own ignored `.ddev/.env` (nonsecret) and existing service-scoped `.ddev/.env.<service>.local` files with private permissions. Never commit or paste these files. Retrying a failed setup only revisits the same portable-owned setup; it does **not** reset durable PCP jobs or their credentials.

The existing `scope-service-secrets.sh` and `n8n-control-plane.sh prepare-env` run **inside one disposable non-root `python:3.13-slim-bookworm` setup container**. It has a read-only rootfs, no network, no Docker socket, no mounted user home or external projects, and a read/write bind of **only this fresh PCP checkout** to create local files. The image may need to be pulled by Docker on first use; it is **not yet pinned to a multiarch digest**. The checked-in `config/tool-versions.env` is authoritative for the generated `CODEX_VERSION`.

`.ddev/config.yaml` remains unchanged and uses its existing `pre-start` host hook. Under the explicit portable flag, `scripts/antigravity-bridge.sh` exits before any host `agy`, Python, keyring, background process or settings mutation. On old installs without the flag, behavior stays unchanged. Antigravity Individual (host-keyring-dependent) is therefore **disabled** for portable mode until a separate container-safe authentication contract is accepted; do not mount/copy the owner's host keyring as a workaround.

After first start, Codex/OpenCode binaries run **inside coding-runtime**, not on WSL. Provider and GitHub authentication are separate one-time tasks scoped to the proper container/credentials; these are not performed by the installer. For example, only after checking the expected container identity, authenticate Codex via `ddev exec -s coding-runtime codex login`. A new recipient never inherits the previous owner's credentials. Source-merged PRs do not prove this auth mode, the actual model entitlement or the Runtime worker is live.

## Safety and known gaps

- `--check` is read-only. `--prepare` creates local configuration and scoped secrets, but never starts DDEV. `--start` requests DDEV boot **explicitly**; it does not create a coding job or call the model.
- The existing `ddev-executor` still gets the **host Docker socket**. This is a high-privilege boundary; internal Docker networks/project labels alone do not confine its Docker API. Do not infer isolation from the portable boot. Future B2 work needs a separate protected review.
- The Runtime image already includes Python/Node and Codex/OpenCode, but OpenCode still uses an unpinned default version in the existing build path. Do not claim fully reproducible supply-chain provenance until pinned separately.
- Existing n8n/Runtime/Guardian is not yet a proven unattended GitHub task consumer. The PC/WSL/Docker must remain running to work; when powered off, new tasks can queue but cannot execute.
- No automatic migration or rollout to an existing owner's PCP state is authorized, and **no interaction with Chợ Nhạc**, frozen T01/F2, #752 G1-T02, or Guardian is part of this task.

## Acceptance still pending

1. Actual clean disposable WSL2/Docker/DDEV installation (not simulated) with no host Python/Node/agy, scoped auth and no Docker cross-project overlap.
2. Validated startup, service health, restart persistence, scoped one-time provider login, source and secret hygiene.
3. B2 durable authenticated local task intake → Codex work → bounded tests → draft PR → exact GitHub CI → PM review → result. **Zero per-task WSL interaction after setup** is the product target, not an accepted result today.

References: [Phase B #764](https://github.com/sonvhse06072/personal-coding-platform/issues/764), [B1.1 #765](https://github.com/sonvhse06072/personal-coding-platform/issues/765), [DDEV hooks](https://ddev.github.io/ddev/en/stable/users/configuration/hooks/), [DDEV .env scoping](https://ddev.github.io/ddev/en/stable/users/configuration/environment-variables/).

## B2.1 — PCP-local GitHub task receipt (source implemented, DEFAULT OFF)

This is **not** the B2 background coding worker. Source-only [DEC-PCP-LOCAL-WORKER-B2-SOURCE-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/764#issuecomment-6368648027) authorizes a bounded task-identity and durable-receipt implementation without changing the active DDEV stack.

- Executor GET `/v1/github/pm-bridge/local-source/issues/{issue_number}?project_id=pcp-local` reads **only** `sonvhse06072/personal-coding-platform` and its current `main` SHA via Executor-owned GitHub credentials. It defaults to 403 unless `PCP_LOCAL_TASK_SOURCE_ENABLED=owner-approved`. This variable is **NOT** set by the checked-in Compose. Any historical F2/G0-scope executor, non-PCP project, foreign origin, or unregistered main branch is refused.
- Runtime POST `/v1/pm-bridge/local-source/check` remains behind the existing Runtime bearer check **and the independent disabled-by-default flag**. It also demands an explicitly registered `pcp-local` project with `base_branch: main`, an approved immutable ProjectBaseline and a separately pinned issue body SHA-256/base SHA. The current project registry has **no `pcp-local` project or baseline**, so this route **cannot process live work as shipped**.
- Only the exact `<!-- coding-platform:pcp-remote-source:v1 -->` Owner issue schema can pass: fixed repo/author/open issue number and permalink, matching current GitHub main, one digest-bound task, two to four exact PCP-light source/test/document paths with a test, and no extra commands/permissions. The issue body is untrusted data, not executable source or an authorization.
- `cp_pcp_local_source_receipts` is a new isolated PostgreSQL *receipt* table, created only on a separately admitted source check. A unique (repository, issue number) and (project, task key) prevent duplicate claims. Exact body/base/baseline/goal/paths must still match on idempotent rechecks. Initial state is `pending`, **not runnable**. Reuse never resets historic model budgets/counters.
- Pure state transitions `pending → claimed → running → delivered/blocked` are parked behind a different missing `PCP_LOCAL_TASK_WORKER_ENABLED=owner-approved` gate and an internal caller authorization; **no B2.1 endpoint calls them**, creates a job, writes a Git branch, dispatches Codex, approves a PR or merges.

This release introduces **no polling clock or background daemon**, Docker permission change, GitHub credential issuance or model call. It cannot make a PC run while powered off. Do not set either flag or create a live baseline as a shortcut; a separate protected B2.2 decision must cover startup, provider/auth, budget, isolated workspace/lease and tested Executor publisher before operational activation.

### Next acceptance steps

**B2.2 (not authorized by B2.1):** review the minimum active Compose/runtime project config, protected credentials and actual DDEV worker wiring; independently attest a safe disposable PCP-only project, then demonstrate one bounded issue → durable same-job Codex container worker → verified branch/draft PR → exact GitHub-hosted CI → PM handoff with zero Owner WSL actions after installation. Full Core G0/G1 trials #595/#752 are separate and remain HOLD/PARKED. Do not touch Chợ Nhạc or historical G1/F2 jobs.

## B2.2a — Local worker admission evidence (source-only, default OFF)

[Issue #769](https://github.com/sonvhse06072/personal-coding-platform/issues/769) adds a **pure, no-side-effect** worker evidence gate in `services/runtime/app/pcp_local_worker_admission.py`. It consumes an already validated `LocalSourceTask`, a durable `pending` receipt and independently observed project, active ProjectBaseline, workspace isolation, provider identity and budget facts.

**Do not switch it on for an existing install.** Both `PCP_LOCAL_TASK_SOURCE_ENABLED` and `PCP_LOCAL_TASK_WORKER_ENABLED` must equal `owner-approved` for the pure check to return anything but STOP. Neither variable is set in checked-in DDEV Compose, no PCP-local ProjectBaseline is approved/registered, and no Runtime route, startup hook, scheduled poller, claim/execute call or Codex subprocess invokes this module today.

Fail-closed checks include: fixed PCP repo/project, exact issue/body SHA and unchanged receipt generation 0 with no job, explicit registered `pcp-local` project, approved active immutable baseline, exact pinned main SHA, clean isolated clone, **no competing writer/lease, other project mounts or agent Docker socket**, verified pinned Codex CLI/model/effort with isolated credentials/no GitHub token/keyring in agent, and specifically Owner-approved bounded model/timeout/changed-path/cost ceilings. These are **trusted caller evidence fields**, not independent network/host attestations; never construct them from the model's response or GitHub issue text.

Even when every test fixture is positive the result is **`ADMISSION_EVIDENCE_CHECKED_NOT_DISPATCHED`** and sets `can_start_agent=false`, `can_claim_lease=false`, `can_publish_or_merge=false`. It performs **zero model calls, DB writes, Docker actions, network calls or retries**, does not reserve a lease and does not substitute for a just-in-time trusted Executor check at the later mutation boundary.

**B2.2b remains operationally gated:** to implement actual outbound task polling, durable job launch, provider execution and verified PR delivery through the existing Runtime/Executor, first approve minimal exact protected paths for project registration, ProjectBaseline, service credentials, network/Docker daemon privilege and DDEV service lifecycle. Do not use historical G1-T02 blocked egress overlays, resurrect Guardian, or reuse a historical PCP/Chợ Nhạc workspace. The first usable acceptance is still a real fresh disposable WSL2+DDEV install, container model auth, and one approved GitHub issue→Codex→CI→reviewed PR result with **zero per-task WSL interactions after setup**.

## B2.2b — Bounded source-only queue loop (not live)

The Owner approved [DEC-PCP-LOCAL-WORKER-B22B-SOURCE-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/764#issuecomment-6371353776) as **source-only** scope. The B2.2b implementation deliberately uses fewer than the 12 allowed paths. In particular it does **not** write a fictitious/active `pcp-local` ProjectBaseline, change `config/projects.yml`, alter DDEV Compose/secret mounts, or make the local host a provider worker without evidence.

- Existing Executor offers a **bounded read-only candidate list** (`GET /v1/github/pm-bridge/local-source/candidates?project_id=pcp-local&per_page=10`) for open GitHub issues with label `pcp-local-ready` in the **fixed PCP repository only**. It returns issue number, permalink and body SHA-256, *not* the raw body, and **never authorizes a task**. The label is discovery metadata, not Owner consent or a deployment trigger. The trusted PM must still pin/approve the exact body digest, base commit and baseline through B2.1 source admission.
- Existing PM Bridge exposes an authenticated **read-only** `GET /v1/pm-bridge/local-source/candidates` that forwards the bounded metadata and marks every item NOT ADMITTED. Both services refuse the request unless `PCP_LOCAL_TASK_SOURCE_ENABLED=owner-approved`; the current shipped Compose sets no such flag.
- `LocalSourceQueueStore.next_pending()` reads **only** the oldest `pcp-local` pending receipt from the durable B2.1 PostgreSQL table. It does not create a receipt, claim/clear/restart an existing job, scan other projects or even write an audit event.
- `pcp_local_worker_loop.LocalWorkerLoop.preview_once()` verifies the exact receipt, re-fetches the current issue/main from Executor, compares the preapproved SHA-256 and issue identity, obtains independently trusted workspace/lease/provider/budget observations through a **future, separately reviewed in-process attestor**, and applies the existing B2.2a admission gate. It returns `PCP_LOCAL_SOURCE_VALIDATED_NOT_DISPATCHED`; **no model/job/PR/delivery is executed**. No trusted attestor is installed today, so the source gate fails closed before any DB read.
- The source-only `execute_once()` kernel illustrates a future one-use path: a third `PCP_LOCAL_TASK_OPERATIONAL_ACTIVATION=owner-approved` gate and injected trusted launcher are required before even scanning. It binds a deterministic job identity to a durable generation-zero receipt with PostgreSQL compare-and-swap **before** a future job launch, and never retries uncertain outcomes. A queued acknowledgement is **not** task completion/PR merge. This kernel is **not wired into Runtime startup, an API endpoint, a scheduler, or any active provider adapter**; the operational flag is not set in Compose.
- The tests use faked Executor/PostgreSQL/attestor/launcher interfaces; they verify replay prevention, stable job IDs, digest/main/lease/source checks, no cross-project reads, denied settings and no blind model retry. They do not establish real container credential isolation, provider entitlement, or clean-machine transfer.

**B2.2c gate remains:** To make the worker actually receive a ChatGPT task and create an accepted PR with zero per-task WSL steps, the PM must independently review/approve an exact protected `pcp-local` project registration and immutable active ProjectBaseline; an installed trusted attestor using actual Executor/lease/runtime evidence; a real bounded durable Runtime job launcher; service-level outbound queue polling/startup and scoped GitHub publisher; and separately attested container-only Codex credentials, Docker socket/trust boundary, provider egress and cost ceiling. **Do not set B2.1/B2.2 flags or use G1-T02's previously blocked egress overlay as a workaround.** The existing Chợ Nhạc and historical T01/F2/Guardian remain untouched.

As of this source milestone, the **PCP worker is not running**. A GitHub label, candidate digest, passed unit test or positive proof fixture is never permission to bill a provider, mount an OAuth session or push code.

## B2-F1 #808 — trusted claim to normal Runtime queue (SOURCE candidate)

[Owner nine-path consent](https://github.com/sonvhse06072/personal-coding-platform/issues/808#issuecomment-6398481501)
and [WorkOrder](https://github.com/sonvhse06072/personal-coding-platform/issues/808#issuecomment-6398511086)
authorize this source/test increment only. The internal
`RuntimeEngine.dispatch_pcp_local_once` composes the existing receipt loop with
required in-process observation readers and a concrete normal-job registrar.
No reader/backend, route, scheduler or worker is installed by default. The
existing fixed-repository PM Bridge GitHub reader is reusable; no new adapter or
service is introduced.

Readers must independently supply short-lived, versioned project, baseline,
isolation, provider, budget, writer, publisher and registered-model observations.
Typed observations are an internal interface, not cryptographic authentication;
their real origin, mount/credential isolation and provider authority still need
separate physical admission. Missing/raw/expired/drifting observations STOP.
An exact issue is selected by the trusted caller; issue/label/model prose cannot
construct the readers. Revalidation occurs after claim and before insertion and
enqueue, including actual project/baseline policy and the registered model tuple.

After the existing claim CAS, one transaction serializes PCP-local registrations,
locks and checks the complete claimed receipt, denies any existing same-ID job,
unknown/nonterminal PCP writer or conflicting claim, and verifies lease identity.
The shared normal `cp_jobs`/event INSERT commits before existing engine enqueue.
The queued row is the PCP-only isolated-writer reservation; no direct-workspace
lease is acquired. All PCP-local `create_job` requests require the private
registration path; WorkOrder-ID-only reuse is unavailable. A failure around
commit/enqueue preserves the consumed claim and any committed job; no automatic
retry, replacement or counter reset occurs.

Synthetic success reports `runtime_job_state=queued`, `model_calls=0` and
`model_execution_proof=NOT_ATTESTED`. Active workers/occupied queues are rejected,
and these SOURCE jobs cannot pass `run_job` without a later execution-admission
change. Transaction-aware fake tests cover rollback/ambiguous commit, independent
Runtime claim races, full identity/collision/ownership and permission revocation.
They do not prove PostgreSQL concurrency on a real DB, container isolation or a
Codex turn. `main.py`, the parked profile and all three activation flags remain
unchanged; no Host/DB/provider call or worker startup is authorized. Exact-head
full4 hosted CI and independent PM COMMENT are required for SOURCE acceptance.
First real task, active baseline, installed readers, credentials/egress, startup,
publication and Host/LIVE acceptance remain separate gates. #752 PARKED,
#595 HOLD, historic jobs frozen; Chợ Nhạc STRICT NO-TOUCH.


## B2.2c0 — Isolated PCP-only draft startup (SOURCE ONLY / PARKED)

Owner scope: [DEC-PCP-LOCAL-WORKER-B22C0-ISOLATED-SOURCE-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/764#issuecomment-6378444225). This is source acceptance only, **not a Docker/WSL/DDEV deployment or a live worker**. G1-T02 #752 PARKED/NOT DISPATCHED; G0 #595 HOLD/NOT GO; F2/T01 frozen; Guardian PARKED; Chợ Nhạc STRICT NO-TOUCH.

Two new protected and *separate* files are `config/projects.pcp-local.yml` and `config/project-baselines.pcp-local.yml`. The project registry contains only `pcp-local`, fixed PCP repo identity, `path: null`, `registration_status: draft`, `isolated_clone` intent, DDEV execution disabled and no commit/push/PR/merge/production powers. The baseline registry has exactly `active_revision: null` and `revisions: {}`: **no approved baseline, source commit or authority frame**. Neither replaces `config/projects.yml` nor existing baselines.

The only new Runtime mode is `PCP_RUNTIME_STARTUP_MODE=pcp_local_inspect`. It accepts only explicit, absolute, correctly named, regular non-symlink PCP-local registry files in the same directory, with an exact parked singleton structure and all `PCP_LOCAL_TASK_*` activation flags absent. It calls no `engine.start()`, `Storage.init`, old PlanOrchestrator, publisher, queued-job replay, Codex, GitHub reader, Docker or provider. HTTP access is restricted to `GET /health`, which reports `degraded` without Router/Executor network checks. Middleware refuses requests without an entered lifespan and still refuses normal endpoints if mode env changes after startup. Selecting normal/legacy modes with a PCP-local registry or flags fails closed **before** legacy startup. This mode is not permission to launch on an existing environment.

### STOP conditions / next protected decision

STOP on an existing checkout, old PCP DB/job/lease/worktree/credentials, non-PCP project in the singleton, populated project path, active/approved baseline, shared Docker daemon/context without separate risk attestation, unreviewed Docker socket/mount rights, normal scheduler/publisher startup, unknown image/start hooks, copied OAuth/keyring, undocumented GitHub/model permission, network/egress rule, unbounded budget or absent verified rollback. Never retry/recreate/rename/bypass the earlier safety-blocked T02 egress overlay.

**B2.2c1 LIVE is NOT APPROVED.** A separately reviewed ChangeProposal must first attest a disposable standalone WSL2 distro/VM and **exclusive** Docker daemon/context, independent repo and state mounts, immutable approved PCP baseline with exact source/ref, container-scoped Codex and GitHub credentials, verified provider/network egress, bounded token/cash/wall budget, single writer/lease, safe rollback, trusted Runtime launcher/poller/Executor permissions and one real issue → Codex in container → draft PR → hosted exact-head CI → independent PM COMMENT → outcome. Setup may be one-time; no Owner WSL per task after that. No live activation without a new protected Owner decision.


## B2.2c1 Gate A — source audit (24 Oct 2026; not a physical attestation)

The Human Owner accepted the [B2.2c1 Phase B direction](https://github.com/sonvhse06072/personal-coding-platform/issues/777), but the original staged ChangeProposal still requires independently evidenced WSL2/Docker isolation, exact protected path approval, credentials and budget. [Audit evidence and limited A1 source proposal](https://github.com/sonvhse06072/personal-coding-platform/issues/777#issuecomment-6378821748) identify blockers without starting any service.

| GitHub source observation | Gate A meaning |
| --- | --- |
| `.ddev/docker-compose.platform.yaml` sets `/config/projects.yml` for Router, Runtime and Executor; no dedicated active PCP-local baseline | **STOP**: legacy multi-project registry still wired to the shipped stack |
| Runtime volumes bind host Codex/OpenCode credentials and gitconfig | **STOP**: fresh, container-specific provider identity not proven |
| Executor binds host Docker socket, project roots, host DDEV and gitconfig | **STOP**: a new Docker network/name is not an exclusive daemon security boundary |
| `.ddev/config.yaml` pre-start builds images and starts host-bridge helper; portable `--prepare` creates scoped secrets | **STOP**: `ddev start` and `--prepare/--start` are mutating, not audit steps |
| `scripts/pcp-portable-bootstrap.sh --check` is a read-only preflight candidate; current source pin is Codex 0.160.0, while OpenCode defaults to `latest` | Check actual tool/image provenance later on a dedicated disposable environment; no physical acceptance yet |
| Existing B2.2b worker loop has no installed trusted attestor/launcher/poller; PCP-only registry is draft with null path and inactive baseline | **STOP**: no worker is available to accept a real task |

A narrowly scoped **B2.2c1-A1 source-only inspection utility** is proposed on issue #777. Candidate source paths and tests are documented there; **no approval for those protected edits or live DDEV/Compose/Runtime/Executor changes is implied**. Its future physical output must be redacted, independently compared against a known-new WSL2 distro/VM and exclusive Docker daemon/context, and must not contain passwords, tokens, host keyrings, repository secrets or unrelated project paths. A script cannot establish independent daemon provenance merely by reading its own Docker network labels.

Until later Gate B approval, do not execute `--prepare`, `--start`, `ddev start`, image builds, Docker container create, new credential issuance, model calls, GitHub background polling or T02 egress configuration. All historical PCP state and Chợ Nhạc remain no-touch; B2.2c1 is **NOT LIVE**.


## B2.2c1-A1 — Read-only isolation prescreen (SOURCE ONLY; not LIVE)

**Owner authorization:** `DEC-PCP-LOCAL-WORKER-B22C1-A1-READONLY-SOURCE-V1` via [Phase B issue #777](https://github.com/sonvhse06072/personal-coding-platform/issues/777) and the Owner's explicit A1 implementation instruction. Only the A1 inspector script, fake-only tests, protected classification and this document are changed. No Docker/Compose configuration, ProjectBaseline, credential, Runtime or Executor behavior changes.

Run **only in a separately provisioned disposable WSL2 distro or Linux VM**, after independent confirmation that the checkout/daemon cannot access any historical project. This source prescreen is **not authority to inspect or operate an existing PCP or Chợ Nhạc installation**:

```bash
if (
  bash scripts/pcp-local-gate-a-inspect.sh --check
); then
  printf 'PCP_A1_WRAPPER=STOP_UNEXPECTED_ZERO_EXIT\n'
else
  result=$?
  printf 'PCP_A1_INSPECT_EXIT=%s\n' "$result"
  if (( result != 2 )); then
    printf 'PCP_A1_WRAPPER=STOP_UNEXPECTED_EXIT_CODE\n'
  fi
fi
```

The inspector runs as a conditional subshell: the `if`/`else` guard keeps an operator's parent shell alive **even with `set -e` enabled** when the expected exit code is 2. A bare `( script )` followed by `result=$?` is unsafe under parent-shell `errexit` and must not be used. The wrapper also reports unexpected success or other exit codes as STOP. The inspector uses **no host Python/Node** and performs no network requests, installation, model invocation, Docker mutation or DDEV startup. It checks only the canonical PCP checkout Git identity/HEAD, tracked file blobs, separate draft project/baseline settings and the legacy Compose credential/socket mounts and build hook. It then queries only three read-only Docker commands: `docker context show`, `docker context inspect --format`, and `docker info --format`. It never calls `ddev`, `docker ps`, `docker network/volume/image ls`, `docker run`, `docker build`, any job/DB API, GitHub API or credentials. Docker must use a local Unix socket; Docker Desktop and remote endpoints are rejected, though Unix-local by itself is not proof of exclusive Docker daemon ownership.

Output is a bounded key=value report: predetermined STOP reasons/statuses, exact PCP source Git SHA, SHA-256 hash of Docker daemon ID plus Unix endpoint, and an untrusted WSL/Linux kernel class. It prints **no host path, Docker endpoint, remote URL, raw daemon identifier, container name, upstream error, token or credential**. The fingerprint is only a comparison hint against separately obtained and verified disposable Docker Engine evidence; it cannot attest no historical mounts or shared daemon backing store. **Every `--check` exits code 2 and reports `PCP_B22C1_LIVE=STOP`, including a clean synthetic prescreen.** A zero exit or `PASS` would be misleading before physical attestation.

STOP on foreign/noncanonical source, symlink or drifted configuration, wrong runtime/worker flag, Docker connection environment override, root user, non-Linux target, nonlocal/Docker Desktop endpoint, bad source/metadata and anything lacking independent physical proof. Do not paste secrets or unsanitized Docker output into a GitHub issue. This script supplies no permission to activate the baseline, DDEV/Compose, Context, Runtime, Executor, task polling, provider credentials/egress, model calls or GitHub publishing.

**Next gate (NOT ATTESTED):** compare the fingerprint with independent records of a *newly provisioned exclusive* WSL2/VM Docker daemon/context/storage, then attest there are no foreign containers, volumes, networks, workspaces or mounts without inspecting existing Chợ Nhạc state. Prepare a distinct exact-path Owner approval for an immutable PCP-only ProjectBaseline, container-scoped auth, Executor daemon boundary, reviewed network/egress, bounded one-task budget and tested rollback. `#752 G1-T02` PARKED, `#595 G0` HOLD, F2/T01/Guardian frozen, Chợ Nhạc STRICT NO-TOUCH. The safety-blocked T02 egress overlay must not be retried, renamed or bypassed.

## B2.2c1 — Owner accepts ONE WSL + SHARED Docker Desktop (2026-10-24)

**Direction:** The Owner selected existing Ubuntu WSL2, Docker Desktop shared with other local projects, and DDEV. This supersedes the previous operational proposal for a mandatory second WSL / exclusive daemon, but **does not modify the approved Constitution trust boundary or grant a LIVE worker**. See [#777 decision](https://github.com/sonvhse06072/personal-coding-platform/issues/777#issuecomment-6379866815) and [scoped A2 proposal #782](https://github.com/sonvhse06072/personal-coding-platform/issues/782).

**Privilege residual:** Docker project labels, network names, separate DB volumes and Compose boundaries are not a security boundary against an Executor holding `/var/run/docker.sock`. It can access the shared engine. Agent/Runtime must never get the socket, host provider homes, unrelated sources or privileged GitHub delivery credential. Executor ownership/scope and post-compromise residual risk require separately reviewed protected changes before LIVE.

**A1 stays unchanged:** The old exclusive-daemon `pcp-local-gate-a-inspect.sh` intentionally exits 2 on Docker Desktop (`DOCKER_DESKTOP_SHARED`), as the Owner observed. Do not rename, bypass or adjust its guard. The new A2 source proposal provides a **separate reviewed shared-Docker resource ownership check**. No A2 inspection result alone may authorize model calls, cleanup or LIVE.

**Fresh PCP state; no unsafe cleanup:** Use a new PCP-only DDEV identity, clean DB volume, exact checkout and workspace roots with no legacy registry mounts when authorized. Do not restart the old Runtime, resume leases, reuse old sessions or delete old PCP DB which can include historical Chợ Nhạc-related records. Quarantine/leave parked old resources pending redacted read-only ownership inventory and resource-by-resource cleanup authorization. Forbidden without exact proof: `docker system prune`, `docker volume prune`, `ddev delete --all`, unscoped `docker compose down -v`, broad `rm -rf` or reuse of old `~/.codex` and host `.gitconfig`.

**Execution sequence:** [A2 #782](https://github.com/sonvhse06072/personal-coding-platform/issues/782) read-only ownership evidence and protected path approval → A3 reviewed new PCP-only Compose/DDEV and blank DB without model → B1 immutable baseline, fresh container-scoped auth, reviewed egress and explicit cash/calls/duration caps → B2 trusted Runtime/Executor launcher with lease/CI/PM review/recovery. Routine tasks target zero per-task Owner WSL actions after bounded one-time setup. No installed worker exists yet.

**Standing STOP:** G1-T02 #752 PARKED, never bypass previously safety-blocked egress; G0 #595 HOLD; F2/T01/Guardian frozen; Chợ Nhạc STRICT NO-TOUCH. Existing A1 and hosted CI are source proofs, not live evidence.

## B2.2c1-A2 — Shared-Docker PCP ownership preflight (SOURCE SCOPE APPROVED; LIVE STOP)

**A2 SOURCE ACCEPTED:** [DEC-PCP-B22C1-A2-SHARED-DOCKER-CLEAN-STATE-SOURCE-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/782#issuecomment-6381170343) covers exactly the A2 read-only inspector, fake-only regression tests, protected-path policy and this document. [PR #784](https://github.com/sonvhse06072/personal-coding-platform/pull/784) was merged after PM COMMENT and actual four-suite GitHub-hosted CI; [postmerge #40072483548](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40072483548) PASS (4,143/88 skipped). This approval **does not grant permission to run the inspector on the Owner host**, delete/migrate PCP legacy state, invoke Docker mutation, grant credentials or activate a LIVE worker. The shared daemon remains **not a Docker security sandbox**.

The script `scripts/pcp-shared-docker-ownership-check.sh` is designed to read only the canonical PCP source identity, draft PCP-only registry/baseline, Docker context/provider metadata and **five server-side label-filtered** Docker resource candidate lists: old PCP platform containers/volumes and the proposed PCP-only namespace's containers/volumes/networks. It emits only counts, a reviewed PCP source SHA and fixed STOP codes, never raw names/IDs, paths, secrets or project data. Unlabeled or differently labeled resources remain **NOT VERIFIED**; a label count never proves ownership, absence or safety for deletion. There is no inspection of historical PCP DB/jobs or Chợ Nhạc.

The inspector intentionally **always exits 2**, including for a clean shared-Docker candidate inventory, and reports `PCP_A2_CLEANUP=NOT_AUTHORIZED`, `PCP_B22C1_LIVE=STOP`. New namespace collisions, dirty checked-in source, activation flags, wrong Git identity, remote Docker endpoint, unknown provider and malformed output fail closed. Source/test CI cannot establish physical host correctness.

**Post-merge operator procedure (not executed or authorized by source approval):** first independently verify the exact GitHub-accepted PCP checkout and its clean source, record that this is an Owner-approved **one-time read-only WSL observation** on the shared Docker Desktop, and verify no unusual external Docker socket or provider credential overrides. Only after this separate operator decision may the existing approved script be invoked. A parent-shell-safe example under `set -e`:

```bash
if (
  bash scripts/pcp-shared-docker-ownership-check.sh --check
); then
  printf 'PCP_A2_WRAPPER=STOP_UNEXPECTED_ZERO_EXIT\n'
else
  result=$?
  printf 'PCP_A2_INSPECT_EXIT=%s\n' "$result"
  if (( result != 2 )); then
    printf 'PCP_A2_WRAPPER=STOP_UNEXPECTED_EXIT_CODE\n'
  fi
fi
```

The expected controlled result remains **exit 2 / STOP**; it must never be interpreted as LIVE or deletion authorization. Share only the bounded `PCP_A2_*` and `PCP_B22C1_LIVE` keys, not Docker stderr, raw IDs, environment, tokens or unrelated names. The command makes no Docker/DDEV mutations, but it still accesses Docker API metadata and should not run outside a separately approved one-time read-only inspection.

**After A2 SOURCE ACCEPTED:** The Owner reported a one-time read-only candidate-count inventory ([#782](https://github.com/sonvhse06072/personal-coding-platform/issues/782#issuecomment-6381693431)) and separately approved A3 **SOURCE-only templates** ([#786](https://github.com/sonvhse06072/personal-coding-platform/issues/786#issuecomment-6382223825)); these two facts do not authorize Docker mutations, deletion, host DDEV application or runtime jobs. A separate **A3 Host profile setup** gate remains before any clean PCP-only Compose/DDEV instance and blank database. Further B1/B2 approvals are required for active immutable baseline, fresh scoped credentials, network egress, budget, Executor permissions and trusted worker. No `docker system/volume prune`, `ddev delete --all`, old PCP DB/job resumption, Codex/provider calls or blocked T02 egress bypass.

## B2.2c1-A3 — PARKED PCP-only DDEV template (OWNER-APPROVED SOURCE SCOPE; NO HOST ROLLOUT)

**Explicit Human Owner SOURCE scope approval:** [DEC-PCP-B22C1-A3-PARKED-PCP-ONLY-DDEV-SOURCE-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/786#issuecomment-6382223825) authorizes exactly the two protected source templates, the static regressions, protected-path policy and this README, with reviewed GitHub CI/PM COMMENT/expected-head merge. The two files under `profiles/pcp-local/.ddev/` remain *source-only templates* — NOT an installed DDEV project, active baseline, credential grant or worker rollout. Source acceptance does **not** authorize running the template or changing the existing checkout's `.ddev/`, nor inspecting/deleting any old Docker/PCP/Chợ Nhạc state.

**Why outside the current `.ddev/`:** DDEV automatically loads `docker-compose.*.yaml` files from the active project's `.ddev` directory and executes `pre-start` host hooks. The existing legacy PCP profile contains old multi-project registry, host image builder and Antigravity bridge hooks. A3 templates are deliberately stored in `profiles/pcp-local/.ddev/` so an ordinary `ddev start` from the current checkout cannot load them. Never start DDEV from this template directory or copy it into the legacy root. [DDEV custom Compose](https://docs.ddev.com/en/stable/users/extend/custom-compose-files/), [DDEV pre-start hooks](https://docs.ddev.com/en/stable/users/configuration/hooks/).

**Intent (not executed):** the template's DDEV project name is `pcp-local`, no hooks, PostgreSQL 17; custom Compose has only optional `pcp-inspect` service (OFF in default DDEV startup). If independently activated later, its Runtime process is explicitly `pcp_local_inspect`, accepts only two *exact, read-only* PCP draft registry YAML file mounts, and has no Docker socket, host CodeX/OpenCode/Git homes, GitHub/provider tokens, broad project roots, Executor, Router, n8n, host port or default background poller. A3 does not build/pin the Runtime image or guarantee outbound network isolation: these require distinct provenance/egress gates before any runtime start.

**A2 host prereq (received, limited evidence):** The Human Owner supplied [A2 redacted counts](https://github.com/sonvhse06072/personal-coding-platform/issues/782#issuecomment-6381693431) from the existing Ubuntu/shared Docker Desktop at source `19e4d44777add751e1497675a6b1914289197e6b`: six old PCP-labeled container candidates, three old PCP-labeled volume candidates and proposed `pcp-local` namespace **zero labeled containers, zero volumes, zero networks**. The A2 script intentionally ended **exit 2 / STOP**, `CLEANUP=NOT_AUTHORIZED`, `LIVE=STOP`. No obvious label-filtered collision was observed for SOURCE review, but unlabeled/differently labeled objects, unrelated DDEV router state, cross-project mounts and old DB/job ownership are **NOT** attested; never infer authorization to stop/delete anything.

**Future application gate (NOT approved):** source authorization and successful GitHub-hosted CI do not grant permission to create a checkout, copy/apply profile templates, start DDEV, create volumes or build/pull images. A *different* exact Host/Docker/DDEV owner decision must first validate the new checkout's project name, rendered service graph and default hooks, image source/digest, shared-Docker resource collisions, absence of host credentials/socket mounts and independent rollback. This A3-S stage creates **no installer**. There is no migration/replay/cancel of historical PCP jobs/DB. Do not invoke `ddev start`, `docker build`, `docker run` or `--prepare` from this template.

**Remain STOP:** shared Docker socket is daemon-wide, not a per-project sandbox; a compromised Executor could affect other projects even with labels/networks. A3 does not give it a socket or run it. ProjectBaseline `active_revision: null` remains immutable; Model/Codex/Provider auth/network/budget/GitHub delivery/worker LIVE not approved. #752 G1-T02 PARKED with its egress overlay never bypassed; #595 G0 HOLD; F2/T01/Guardian frozen; Chợ Nhạc STRICT NO-TOUCH.

## B2.2c1-H1a — PCP-only Runtime image provenance plan (OWNER-APPROVED SOURCE; LIVE STOP)

**Source-only Human Owner approval:** [DEC-PCP-B22C1-H1A-RUNTIME-IMAGE-PROVENANCE-SOURCE-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/791#issuecomment-6385385554). Six exact files only, including two new protected source files, the protected A3 Compose template and the protected document authority policy. Source work and PR/CI are permitted; **Docker image build/pull/retag, DDEV start, new DB, old PCP cleanup, provider egress and worker LIVE remain prohibited**. No existing project `.ddev` or legacy image-builder was modified by this stage.

**Why H1a is deliberately fail-closed:** [Owner H0 report](https://github.com/sonvhse06072/personal-coding-platform/issues/790#issuecomment-6385186600) found a local Runtime image PRESENT but source revision label did not match, and provenance was NOT independently attested. The legacy Runtime Dockerfile has a floating `node:22-bookworm-slim` base and `OPENCODE_VERSION=latest`, with apt dependencies resolved at build time. The old `scripts/pcp-build-images.sh` would rebuild Router + Runtime + Executor and overwrite shared `:local` tags. Neither is a safe PCP-local remediation on Docker Desktop. Absence/mismatch of a revision label is **not evidence of tampering**, but it cannot be upgraded to trusted provenance.

**H1a historical source artifacts (schema superseded by the H1b draft below):** `profiles/pcp-local/image-provenance.example.yml` was introduced as an incomplete immutable-input contract with missing source/base/dependency/artifact/attestation evidence. `scripts/pcp-local-image-provenance-plan.py` is read-only; it accepts only `--check`, rejects dirty or foreign PCP Git sources, validates the fixed manifest schema and prevents mutable/foreign image references. It **always emits `PCP_H1A_RESULT=STOP` / `PCP_B22C1_LIVE=STOP` and exits 2**, even when a future manifest claims all fields. No image or credential is ever created, and local metadata cannot promote itself to independent attestation.

**H1a historical A3 Compose limitation:** H1a preserved the legacy `:local` reference with `pull_policy: never` and profile OFF. This could still run an installed legacy image if an operator bypassed the gates. The H1b draft below replaces that reference and adds an explicit non-runnable command; it does not activate the profile.

**Layers of evidence needed before future H1b:** (1) new exact Owner-approved Git source revision and file hashes, (2) digest-pinned base image and explicitly versioned build inputs (including OpenCode and OS dependency resolution, potentially an inspection-only reduced image), (3) unique PCP-local image/manifest digest and reliable Buildx `--metadata-file` output, (4) independently verified attestation/source-chain or an explicit separate Owner decision accepting lower assurance, (5) no-overwrite Docker builder/tag and resource-bound rollback. Docker warns that attestations can be lost with `--load` into the classic image store; external Buildx metadata and an image label are **not** cryptographic proof. [Docker Build attestations](https://docs.docker.com/build/metadata/attestations/) · [Buildx metadata-file](https://docs.docker.com/reference/cli/docker/buildx/build/).

**Next independent authorizations:** H1b source/build recipe expansion is required if existing Dockerfile, A3 structural tests or another protected path must change. A separate bounded Host operation decision is mandatory before any actual Buildx build, image import, registry push, DDEV install or new blank DB. Future B1/B2 gates still govern active PCP-only ProjectBaseline, container-scoped authentication, provider egress, explicit cost/time/call caps and trusted Runtime→PR delivery. The H1a plan is source-only: no per-task WSL operator automation is installed. #752 G1-T02 PARKED, #595 G0 HOLD, F2/T01/Guardian frozen, Chợ Nhạc STRICT NO-TOUCH.


## B2.2c1-H1b — historical inspection-image draft (#794; subsequently SOURCE ACCEPTED in #796)

**Authority / WorkReport:** [WorkOrder #794](https://github.com/sonvhse06072/personal-coding-platform/issues/794), starting source `15c18eefc13234efcda61c84f54a547d7a5bdebf` (verified canonical remote `main` before edits). Branch `ai/794-inspection-image-source`. Exact nine-path SOURCE proposal plus `docs/project/current-state.md`, which the Owner explicitly allowed for this draft in the implementation session. This addition by itself grants no protected-source merge or Host authority. Decision `DEC-PCP-B22C1-H1B-CODEX-PINNED-INSPECTION-RUNTIME-SOURCE-V1` is **OWNER-APPROVED SOURCE SCOPE**: the Human Owner replied "Phê duyệt phạm vi SOURCE của PR #796" to the explicit six-protected-path question in the implementation session. [Draft PR #796](https://github.com/sonvhse06072/personal-coding-platform/pull/796) records the exact paths and declared approval reference. This is a record of actual session consent, not independent GitHub identity attestation; PM must verify consent before merge. The manifest remains draft/untrusted. Source result is **DRAFT / UNRESOLVED**, not an immutable image release.

### Design comparison and selected draft

| Option | Attack surface / resource complexity | Assessment |
| --- | --- | --- |
| Reduced inspection image reusing existing `app.main` | Python base, six existing direct Runtime dependencies and their transitive wheels; no Node/npm, apt install, Codex/OpenCode, Git/SSH or tests. Existing application modules still contain legacy engine code; mode/registry guards are essential. | Preferred bounded draft. Reuses the existing no-state health contract and avoids a second backend/scheduler. Image size/time has **not** been measured. |
| Copy full Runtime Dockerfile with pins | Also needs pinned Node, CLI/npm trees, Python/OS packages and an apt snapshot; additional supply-chain and update burden for tools inspection never invokes. | Rejected for this stage. Legacy Dockerfile, image builder and Router/Executor images are untouched. |

`services/runtime/app/main.py` imports FastAPI/Pydantic and transitively HTTPX, PyYAML and psycopg. Constructors create engine/client objects and an empty queue, but do not start the engine or connect the DB. The existing `pcp_local_inspect` lifespan validates the two exact parked draft registries, skips secret hardening/DB initialization/engine/publishers, and returns health with `degraded`, Router/Executor `not_checked`, all coding adapters false. Its middleware rejects every other route and rejects a mode flip. This is an **inspection-only invocation of shared application code**, not physical removal of legacy code or a substitute for OS egress isolation.

The draft Docker CMD selects Python module uvicorn, asyncio/h11, WebSockets disabled, lifespan **on**, loopback `127.0.0.1:8787`, with no reload/workers or public port. No new entrypoint/application source is introduced. Compose stays profile OFF, `pull_policy: never`, two read-only YAML binds, no host secrets/socket/extra service. Its image is `pcp-local-runtime-inspect:source-unresolved-do-not-run` and command is `/PCP_H1B_SOURCE_ONLY_NOT_AUTHORIZED` (absent from the image). Both must be replaced by a separate reviewed source+Host change before future in-container health acceptance. A name/comment is not a daemon security boundary.

### Missing pins at the H1b checkpoint (successor H1b2 proposal below)

`Dockerfile.inspect` selects **linux/amd64, CPython 3.13 slim Bookworm**, with mandatory `PCP_INSPECT_BASE_SHA256` and no default, yielding `python:3.13-slim-bookworm@sha256:<reviewed digest>`. No actual digest has been resolved, invented or copied from a host image. `requirements-inspect.lock` is explicitly **UNRESOLVED**: direct-version candidates come from existing Runtime requirements, standard uvicorn protocol extras and pytest are omitted, transitive CPython 3.13 wheel versions/hashes remain absent. `pip --require-hashes --only-binary=:all:` must fail on this draft. Hashes must cover every direct and transitive wheel; no source builds, alternate index, floating version, CLI extra or network fallback. [pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/).

Registry/base-manifest resolution and target-platform package artifact verification require a separately approved evidence step. **Docker Hub/registry image lookup, image pull/build/import, lock resolution for the image: NOT RUN.** A temporary host test environment installs the existing Runtime development requirements solely for unit tests; its Python version, transitive selections and cached/downloaded wheels are **not image-lock availability or provenance evidence**. A reviewed successor must replace unresolved inputs and review the lock closure; offline syntax checks cannot prove wheel availability or compatibility.

Schema v2 binds the proposed source commit, recipe and lock SHA-256, canonical application-tree SHA-256, platform/mode, dedicated image manifest digest, config digest, Buildx metadata, provenance and SBOM hashes. The app-tree digest is SHA-256 of sorted relative POSIX paths, NUL, each file-content SHA-256 and LF; only `.py` inputs are admitted, symlinks/extra files/generated caches fail closed. The whole app is copied, so all of it is a build input. A later builder must stage **only** those reviewed tracked inputs from an exact clean source commit; context `.` does not authorize sending repository secrets/untracked files to a builder. No build wrapper is supplied here.

The checked-in example keeps `source_commit`/artifact/material hashes null. A future release verifier must consume an **external, separately reviewed evidence record** bound to the immutable recipe source SHA. Never try to write the containing commit's own SHA into its example (a self-reference), modify the approved baseline, or weaken the current exact-HEAD check to make it pass. Supporting real external manifests/build execution is outside this source-only checker and needs a separately scoped successor.

### Future BuildKit evidence plan (design only; no executable build command)

1. Approve exact source/pins/inputs first, then a separate bounded Host decision: fresh PCP-only builder/output namespace, resource/time/disk/egress caps, no collision/consumer overwrite, no legacy builder bootstrap or credential inheritance. A unique future staging tag could be `pcp-local-runtime-inspect:<source12>-<build-id>`; deployment identity must be the reviewed `pcp-local-runtime-inspect@sha256:<manifest>` (or separately reviewed registry mapping), never that tag alone. Builder/tool/frontend and SBOM-generator versions/digests also require evidence; none is silently resolved here.
2. Proposed build evidence uses BuildKit provenance **mode=max**, SBOM, and `--metadata-file` in a fresh immutable evidence directory. Preserve `containerimage.digest`, `containerimage.config.digest`, builder identity, exact build arguments/platform/source, input hashes, full provenance statement and SBOM. A future verifier must compare statement subject **manifest digest** and source/materials, keeping config digest distinct; compare original metadata/statement/SBOM bytes to their recorded hashes. Submitted hash fields alone prove none of those comparisons.
3. Preserve the complete OCI index plus attestation manifests in a separately approved registry or OCI-layout export. A classic Docker `--load` is **not** an acceptable attestation transport. Unknown stores, registry unavailability, missing/mismatched records or OCI import behavior STOP; no fallback to legacy `:local`, label trust or attestation removal. Containerd store support alone does not attest a particular image. [Docker attestations/store support](https://docs.docker.com/build/metadata/attestations/) and [Buildx metadata/export options](https://docs.docker.com/reference/cli/docker/buildx/build/).
4. Independent verifier/trust-root and registry/OCI identity binding must be reviewed outside the submitted manifest. Self-authored labels, local Buildx metadata, a declared verifier or even matching hashes cannot approve provenance. A lower-assurance path needs a distinct explicit Owner decision. Current `--check` always returns controlled **exit 2 / STOP**, including complete synthetic claims; it has only read-only Git/file operations and no verifier/network/Docker call.

### Verification, handoff and rollback boundary

Fake-only tests cover source SHA/dirty/foreign checkout, recipe/lock/app drift, malformed dependencies/hashes, image and attestation subject/material mismatch, unsafe protocol/mode, profile/port/credential/mount additions, unknown/classic store and unavailable verifier with no fallback. A synthetic copy of the actual application imports and enters its lifespan with socket/DNS/HTTP/DB/subprocess calls forbidden, omitted optional protocol libraries blocked, and verifies an empty worker/queue, no added tasks, health-only routes and mode-flip refusal. **This is local ASGI/source evidence, not Docker runtime UAT, pinned-base import proof or target CPython 3.13 wheel proof.** Root CI can skip this synthetic test when Runtime dependencies are absent; the Runtime suite separately tests the existing inspection lifespan.

Local Python 3.13 verification: focused **108 PASS**; root **1,337 PASS**; Router **132 PASS**; Runtime **2,145 PASS / 88 skipped**; Executor **637 PASS**; `git diff --check` PASS. These are local checks, not remote CI or independent review.

Required before SOURCE acceptance: Owner scope approval (received, as recorded above), exact-head hosted four actually executed suites (not skipped service suites), independent ChatGPT PM COMMENT review, expected-head merge by PM and postmerge real4. Never declare an approval field as received merely to make the authority check green. Build/pull/registry/DDEV/DB/credentials/provider/model/worker actions remain **NOT RUN / NOT AUTHORIZED**. #752 PARKED, #595 HOLD, F2/T01/Guardian frozen, Chợ Nhạc STRICT NO-TOUCH.

**Proposed one-step rollback for a later Host stage:** stop/disable only the new exact PCP-local inspection service and restore its previously parked profile reference, leaving all new evidence/artifacts and existing DB/images/volumes/builders intact. There is no running predecessor inspection service to roll back to. Exact resource identities, consumer checks and the stop mechanism must be approved/tested before that stage; no operational command, pruning, image removal or current Host rollback is authorized by this document.


## B2.2c1-H1b2 — digest, wheel and context SOURCE accepted (#797)

**Status: SOURCE ACCEPTED through [PR #799](https://github.com/sonvhse06072/personal-coding-platform/pull/799) and [continuity PR #801](https://github.com/sonvhse06072/personal-coding-platform/pull/801).** [Actual Owner approval](https://github.com/sonvhse06072/personal-coding-platform/issues/797#issuecomment-6387226124), [PM outcome](https://github.com/sonvhse06072/personal-coding-platform/issues/797#issuecomment-6387326210); subsequent research anchor `main@7b8b2617973285365a6e4efe79b0d4e350ad64bf`. Historical input research observed 2026-10-24 UTC / 2026-10-25 Asia/Bangkok. All values below identify source inputs; no built PCP image or trusted-build/Host approval follows. H1b3 below adds an offline evidence proposal under its own exact-path SOURCE consent.

### Base image: verified per-platform metadata, no layers pulled

Anonymous HTTPS registry metadata was fetched for `library/python:3.13-slim-bookworm` and exact version `3.13.17-slim-bookworm`. Their index bytes have SHA-256 `e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530`, matching the registry content-digest header. Exactly one index descriptor selects `os=linux, architecture=amd64`; its **image manifest**, not the multi-platform index, is pinned in the recipe:

```text
python:3.13.17-slim-bookworm@sha256:4cea12ab7d78a3312c85f8cab19b6971d4fe9704da25443986c0bc20a6678850
```

The manifest body SHA-256 matches that descriptor. Its config descriptor/body SHA-256 is `4412cecc4af63502bd64d4b862be90b306d4134759d45cde783514dafdd6d03c`; config confirms `linux/amd64`, `PYTHON_VERSION=3.13.17`. Index annotations name Docker-library source revision `e316b6c5b88b7c8e4806aa7626060c9bd8227e66`, independently readable [official recipe at that revision](https://github.com/docker-library/python/blob/e316b6c5b88b7c8e4806aa7626060c9bd8227e66/3.13/slim-bookworm/Dockerfile), which declares the same Python version. [Exact registry manifest endpoint](https://registry-1.docker.io/v2/library/python/manifests/sha256:4cea12ab7d78a3312c85f8cab19b6971d4fe9704da25443986c0bc20a6678850) requires an anonymous repository-pull bearer token; no account/host credentials were used or saved. Only index, manifest and config **metadata** were read; none of the four filesystem layers was fetched, no Docker command/image pull occurred. Labels/source annotations are corroborating publisher assertions, not independent signatures or proof of how the base was built.

`Dockerfile.inspect` uses the literal manifest digest with explicit `--platform=linux/amd64`; the build-arg escape has been removed. An ARM descriptor, the discovery index digest, a tag-only ref or a changed base fails source validation. This freezes the entire base filesystem as an input; it does not claim that upstream Debian's own original apt build was reproducible, that OS packages are vulnerability-free or that the image has run locally.

### Wheels: complete CPython 3.13 linux/amd64 lock, independently re-fetched

The six existing direct versions remain unchanged. A wheel-only resolver selected **18** direct/transitive distributions for CPython `cp313` / `linux/amd64`, including **three compiled wheels and fifteen pure-Python wheels**. The compiled PyYAML, pydantic-core and psycopg-binary files have tags `cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64`. The lock records exact filenames, versions, one SHA-256 per approved wheel, original `files.pythonhosted.org` URL, versioned PyPI JSON URL and the SHA-256 of the observed JSON receipt for every distribution. No sdist, alternate architecture, `uvicorn[standard]`, pytest, floating version or private index is admitted.

For every selected wheel, the versioned [PyPI JSON API](https://docs.pypi.org/api/json/) was checked for matching filename, `bdist_wheel`, non-yanked status, size and published SHA-256. Each artifact was **freshly fetched again from its HTTPS `files.pythonhosted.org` URL**, independently of pip's cache, and hashed: all 18 matched both PyPI's published hash and the resolver-downloaded file. Total wheel bytes: **8,805,631**. A JSON receipt is a point-in-time publisher record and can later change; wheel URLs plus content hashes are the immutable input identities. This is distribution-source/hash evidence, not a signed independent security audit or attestation of the future PCP image.

A fresh temporary **host CPython 3.13.15** environment installed this exact lock offline, with `--no-index`, the verified wheel directory, `--require-hashes --only-binary=:all:`; `pip check` reported no broken requirements. The real `app.main` source-copy import/ASGI lifespan test also ran under that minimal environment with DB/socket/DNS/HTTP/subprocess calls forbidden and without optional uvicorn protocol packages. This validates the wheel closure/imports on local CPython 3.13 ABI, **not a 3.13.17 base-container UAT, image build or OS loader proof**. Hash mode fails if a dependency/wheel changes or another unpinned dependency is needed. [Official pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/).

### Context: literal deny-by-default policy plus mandatory source staging

Docker supports a same-directory `<Dockerfile>.dockerignore`, which takes precedence over a root `.dockerignore`; this is the checked-in `profiles/pcp-local/runtime/Dockerfile.inspect.dockerignore`. [Official Docker context rules](https://docs.docker.com/build/concepts/context/). Its restricted form is `**`, then **102 literal file exceptions**, then **102 matching child-denial rules**. No directory reinclusion or Python wildcard is used. The data set is exactly the recipe, lock and the existing 100 application `.py` paths. Unknown Python files, `.git`, `.env`, old `.ddev`, docs, credentials, workspaces and foreign sources are excluded. Child denials matter: Moby's parent matching otherwise permits descendants when an allowed filename is replaced by a directory. Symlinks/file-directory collisions also fail staging.

Actual upstream [moby/patternmatcher v0.6.0](https://github.com/moby/patternmatcher/tree/347bb8d8d557f90d1b75cd8bca3c0177f380a979), including `ignorefile.ReadAll` and `MatchesOrParentMatches`, was compiled in a temporary research directory and run against **524 cases: 102 included / 422 excluded**. Go module checksum: `h1:GmP9lR19aU5GqSSFko+5pRqHi+Ohk1O69aFiKkVGiPk=`. Upstream source SHA-256: `patternmatcher.go` = `fc1b0f72111b7cd4eb32ebc0c8b5a1433fb6178eb0564b62280f1054af785222`; `ignorefile/ignorefile.go` = `85effca9cbe731413713d55f62dcb22e2ef8553138e3f1892daaae9d3581d3cf`. The lexicographically sorted JSON map (compact separators) result SHA-256 is `80635ae24ce7eeacbd1400d3f605d3594a37724a3a97b5fdf91a9135060bf4d6`. The test reproduces this matrix and fixed oracle result, and optionally compares the actual pinned helper via test-only `PCP_H1B2_MOBY_ORACLE`; CI performs no Go/module download. No new application dependency is added. To reproduce the helper, use the pinned module in a temporary Go program: read the policy with `ignorefile.ReadAll`, construct `patternmatcher.New`, and return `!matcher.MatchesOrParentMatches(path)` for each case from `context_cases()` in the test. Docker's documented special handling of control files is separate from matcher results.

A future authorized builder must consume **only the output bytes of `source_context()`**, never this repository root directly. The pure helper accepts already-read source bytes, verifies exact membership against the literal policy, enforces per-file/aggregate bounds, then makes a deterministic **in-memory** USTAR (regular files only, sorted paths, mode 0644, uid/gid/mtime zero). It neither writes an archive to disk nor invokes any builder. Tests open the resulting archive and verify every name/type/content and absence of all unlisted inputs. It contains 102 data files plus **one necessary build-control file**, the Dockerfile-specific ignore file: Docker sends ignore control metadata even when excluded from `COPY` access. This exception is explicit; no root `.dockerignore` or other repository file is included.

Observed staged payload: **103 regular files, 1,740,800 TAR bytes**, SHA-256 `cb766b4845bcf77759f51e74041a4e0e379ab37a869eeb99bb0b682bdbcfc39b`; app-tree SHA-256 `33f73dd0064300d8a0945e81fa66c4ac7858999b9a3d685d33ba7b9ad12b1530`. These bind this source-input snapshot; later authorized staging must regenerate and compare identities, reject dirty/untracked/symlink/generated inputs, and attest the exact source commit externally. There is **no build/stage/apply CLI** in this proposal: `--check` only constructs/validates bytes in memory, prints fixed redacted STOP evidence and exits 2. An invocation against arbitrary root `.`, remote/named context, alternate Dockerfile/frontend or an unreviewed staging wrapper remains prohibited.

### Provenance and future Host decision remain separate

Schema v3 adds the exact ignore path/hash and resolved input identities. `approval_state` stays `draft`; `source_commit`, app-tree release binding, all PCP artifact/config/image digests, metadata/SBOM/attestation identifiers and independent verifier remain absent. There is no self-referential source-commit pin, approved-baseline rewrite or automatic promotion of input evidence into trusted image evidence. Even fully populated synthetic claims return STOP; wrong source/hash/index/platform/subject/material/store and unsafe fallback still fail closed. **The parked Compose is unchanged and cannot run using its absent command.**

Future separately approved Host work must cap wall time, disk, CPU/memory and network to exact base/wheel/attestation endpoints; choose a fresh PCP-only builder/output namespace and verify no shared consumer overwrite; pin builder/frontend/SBOM generator and authenticate an independent verifier trust root. Bind source SHA plus recipe/lock/app/ignore/context identities to the built per-platform manifest, distinct config digest, any enclosing index, provenance subject/materials and SBOM. Keep Buildx metadata and original signed statements/SBOM bytes; verify their actual contents and signatures outside the submitted manifest. Use a reviewed registry or retained OCI layout; classic `--load`/unknown stores, registry outage or unverifiable import STOP with **no label, tag or legacy-image fallback**. [Docker attestation storage](https://docs.docker.com/build/metadata/attestations/). No trust root, registry, builder, signature key, resource allowance or model credential is provisioned by this draft.

**Local verification:** focused provenance/profile **124 PASS**, combined continuity/focused **146 PASS** with actual Moby oracle and minimal-lock Python; full Python 3.13 suites: root **1,353 PASS**, Router **132 PASS**, Runtime **2,145 PASS / 88 skipped**, Executor **637 PASS** (total **4,267 PASS / 88 skipped**); `git diff --check` PASS. Local results are separate from hosted CI and independent PM review.

**Handoff:** #797 SOURCE consent/review/merge is complete; its source/ASGI/oracle/hash evidence is no Docker UAT. Host/OCI and physical DDEV work still need their separate decisions. #752 PARKED/no blocked-egress retry, #595 HOLD, F2/T01/Guardian frozen, Chợ Nhạc STRICT NO-TOUCH.

## B2.2c1-H1b3 — offline OCI evidence SOURCE proposal (#800)

[Focused H1b3 plan and trust/phase matrix](h1b3-oci-evidence-plan.md) is the review source for this implementation. [Owner SOURCE consent](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6388248530) and [WorkOrder](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6388267083) authorize exactly nine source/test/docs paths and one Draft PR. H1b3 is SOURCE ACCEPTED through [PR #802](https://github.com/sonvhse06072/personal-coding-platform/pull/802), [PM outcome](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6392783715) and actual hosted full4; the physical Host plan is **UNAPPROVED**.

The older checker now freezes exact immutable Git objects, verifies inventory/modes/HEAD before and after, and generates the same canonical source TAR. It never stages the working-tree root. The new example uses strict JSON (a YAML subset), separates expected/observed/verification/authority and retains null output/root/permit fields. The new inspector reads bounded supplied OCI data only. It checks catalog/index/platform/config/layers, max-shaped SLSA assertions, SBOM and a proposed supplementary source-input ledger. Runtime config values bind to the unchanged pinned inspection Dockerfile, including User, exact Cmd/WorkingDir/env and no Entrypoint/ports/volumes; rehashed malicious-config regressions address [PM's P1 finding and repair WorkOrder](https://github.com/sonvhse06072/personal-coding-platform/issues/800#issuecomment-6392498819). The repaired SOURCE was independently reviewed and merged; its integrity checks do not authorize Host. No network, executor, signature adapter or Host capability exists.

Matching synthetic graphs may yield **integrity PASS**. Authenticated producer provenance remains **NOT_VERIFIED**, image reproducibility **NOT_TESTED**, and overall/Host/Runtime/LIVE **STOP / exit 2**. Its small strict USTAR fixture profile rejects ordinary OS-image link/extension layouts and oversized real exports; no real builder/export compatibility is claimed. Host numeric ceilings are prospective and unenforced. Independent producer/root, privileged builder/local fallback, hard disk, egress and cancellation remain unresolved. No operator build/bootstrap/import/start command is authorized; #795 stays SOURCE design only.

## B2.2c1-H1c — offline clean DDEV plan SOURCE (#795)

[H1c technical plan](h1c-ddev-install-plan.md) documents the bounded source implementation under [actual Owner seven-path/four-protected consent](https://github.com/sonvhse06072/personal-coding-platform/issues/795#issuecomment-6394295965) and [WorkOrder](https://github.com/sonvhse06072/personal-coding-platform/issues/795#issuecomment-6394309665). This implementation awaits Draft PR exact-head hosted full4 and independent PM COMMENT; physical Host installation remains STOP.

The validator consumes one strict JSON/YAML-subset plan with four supplied hash-pinned parked source payloads. It does not query Git, the filesystem layout, DDEV, Docker, registries, providers or credentials. Matching supplied bytes/config and unsigned SOURCE-only replay metadata may have structural consistency; they cannot attest an actual clean checkout, resource absence, ownership, trusted OCI producer or Host permission. The CLI accepts only `--check` and an optional explicit data path, always exits 2, and prints fixed redacted Host/DB/LIVE STOP results. All real root/ID/trust/permit/enforcement fields remain null.

Future source/instance/evidence directories are modeled without creating them. Existing parked UID/HOME conflict with the accepted image contract is deliberately unresolved. Legacy hooks/public links, inherited env, extra config/Compose files, socket/foreign mounts, active profile/config, unknown/stopped/shared resources, fake verification/permits, partial/replayed journals and unenforced resource/rollback claims reject. #800 independent OCI proof plus future active-profile, DDEV ancillary-image/tool, shared-router/cache and exact operational decisions are still prerequisites for any physical install. No installer or per-ticket worker is provided; #752 PARKED, #595 HOLD, F2/T01/Guardian frozen, Chợ Nhạc STRICT NO-TOUCH.
