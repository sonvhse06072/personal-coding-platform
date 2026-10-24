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

**New source artifacts:** `profiles/pcp-local/image-provenance.example.yml` is a deliberately incomplete immutable-input contract with all approval, base digest, Dockerfile/dependency digests, output image identity, metadata digest and independent attestation fields set to `null`. `scripts/pcp-local-image-provenance-plan.py` is read-only; it accepts only `--check`, rejects dirty or foreign PCP Git sources, validates the fixed manifest schema and prevents mutable/foreign image references. It **always emits `PCP_H1A_RESULT=STOP` / `PCP_B22C1_LIVE=STOP` and exits 2**, even when a future manifest claims all fields. No image or credential is ever created, and local metadata cannot promote itself to independent attestation.

**A3 parked Compose contract:** still uses the legacy `personal-coding-platform-coding-runtime:local` only as an **untrusted, blocked-for-new-PCP placeholder** to preserve the already accepted structural-test contract. H1a adds `pull_policy: never` and keeps the `pcp-inspect` profile OFF by default. This prevents unintended remote pulls, **but does not prevent an operator from deliberately starting an already installed local image**. Therefore **DO NOT enable the profile**, and a later exact protected PR must replace its legacy tag with a digest-locked new PCP-only image reference while synchronously revising the old A3 structural test. Neither Compose comment nor `pull_policy` is an image provenance enforcement boundary.

**Layers of evidence needed before future H1b:** (1) new exact Owner-approved Git source revision and file hashes, (2) digest-pinned base image and explicitly versioned build inputs (including OpenCode and OS dependency resolution, potentially an inspection-only reduced image), (3) unique PCP-local image/manifest digest and reliable Buildx `--metadata-file` output, (4) independently verified attestation/source-chain or an explicit separate Owner decision accepting lower assurance, (5) no-overwrite Docker builder/tag and resource-bound rollback. Docker warns that attestations can be lost with `--load` into the classic image store; external Buildx metadata and an image label are **not** cryptographic proof. [Docker Build attestations](https://docs.docker.com/build/metadata/attestations/) · [Buildx metadata-file](https://docs.docker.com/reference/cli/docker/buildx/build/).

**Next independent authorizations:** H1b source/build recipe expansion is required if existing Dockerfile, A3 structural tests or another protected path must change. A separate bounded Host operation decision is mandatory before any actual Buildx build, image import, registry push, DDEV install or new blank DB. Future B1/B2 gates still govern active PCP-only ProjectBaseline, container-scoped authentication, provider egress, explicit cost/time/call caps and trusted Runtime→PR delivery. The H1a plan is source-only: no per-task WSL operator automation is installed. #752 G1-T02 PARKED, #595 G0 HOLD, F2/T01/Guardian frozen, Chợ Nhạc STRICT NO-TOUCH.
