# Personal Coding Platform v1

A DDEV-managed, personal coding automation platform. Daily startup is intentionally one command:

```bash
ddev start
```

## Project source of truth

Project intent, authority boundaries, current/target architecture, agent-team operating model, and the approved implementation roadmap live in [`docs/project/`](docs/project/README.md). Coding agents should begin with the repository-root [`AGENTS.md`](AGENTS.md), which defines the required reading order and authority hierarchy.

The checked-in source of truth is authoritative over chat history or remembered agent context. Documents under `docs/project/` clearly distinguish current implemented behavior from approved target behavior so planned PM/WorkOrder/Reviewer capabilities are not treated as already available.

## Why DDEV for the whole platform?

DDEV supports custom Docker Compose services through `.ddev/docker-compose.*.yaml`, so the platform can remain one Git repository while keeping Router, Coding Runtime, n8n and the privileged DDEV executor isolated as separate services.

The Coding Runtime **does not** receive `/var/run/docker.sock` or the source-repository root. Only `ddev-executor` has Docker and source-repository access and it accepts a project ID + named phase (`preflight`, `targeted_tests`, `static_analysis`, `full_tests`, `cleanup`). The actual shell commands come only from checked-in `config/projects.yml`.

## Components

- **n8n** — thin control plane for ingress, status access, human decisions and future external event/notification orchestration.
- **router** — deterministic-first complexity/profile/model selection and hard execution budgets.
- **coding-runtime** — job persistence, repository analysis, isolated Git workspaces, agent adapters, deterministic verification, repair/escalation loops and bounded GitHub delivery.
- **Antigravity host bridge** — constrained WSL-host bridge that runs the signed-in `agy` CLI inside isolated job workspaces; it keeps OS-keyring credentials outside Docker.
- **ddev-executor** — tiny privileged service that can operate target DDEV projects without exposing Docker socket to the agents.
- **PostgreSQL** — the standard DDEV `db` service; n8n and runtime persistence share it.

## One-time setup

Prerequisites on WSL: Docker/Docker Desktop integration, DDEV, Git, Python 3 and a signed-in Antigravity CLI (`agy`).

```bash
./scripts/bootstrap.sh
```

The script creates `.ddev/.env`, generates local service secrets, detects the Docker socket group, creates `$HOME/.coding-platform/workspaces`, and starts the platform. n8n secrets are kept in the service-scoped `.ddev/.env.n8n.local`; existing installs preserve their current n8n encryption key during migration.

After that:

```bash
ddev start
```

is enough.

## Register your real project

Edit `config/projects.yml`. A project is never accepted from an arbitrary API path; it must be registered here.

```yaml
projects:
  my-drupal:
    path: "${CODING_PROJECTS_ROOT}/my-drupal"
    base_branch: develop
    privacy:
      private_code: true
      allow_training_provider: false
      require_zero_retention: false
    autonomy:
      allow_commit: true
      allow_push_ai_branch: true
      allow_create_pr: true
      allow_auto_merge_low_risk: true
      allow_production_deploy: false
    runtime:
      branch_prefix: ai
      max_diff_bytes: 750000
    ddev:
      enabled: true
      preflight:
        - "ddev start -y"
        - "ddev drush cr"
      targeted_tests:
        - "ddev exec vendor/bin/phpcs web/modules/custom"
      static_analysis:
        - "ddev exec vendor/bin/phpstan analyse web/modules/custom"
      full_tests:
        - "ddev exec vendor/bin/phpunit"
      cleanup:
        - "ddev stop --unlist --omit-snapshot"
```

By default `CODING_PROJECTS_ROOT=$HOME/projects`. Change it once in `.ddev/.env` if your repositories are elsewhere.

## Authenticate coding agents once

Antigravity Individual authentication is intentionally kept on the WSL host because `agy` stores account sessions in the Linux Secret Service/D-Bus keyring. The coding container does **not** receive your host keyring.

Install/login Antigravity natively on WSL first:

```bash
curl -fsSL https://antigravity.google/cli/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
agy
agy -p "Reply with exactly ANTIGRAVITY_OK" --output-format json
```

`ddev start` automatically starts a local bearer-token-protected host bridge. Runtime calls that bridge only for workspaces under `$CODING_WORKSPACES_ROOT`; the bridge runs `agy` with Antigravity's native sandbox and non-interactive permissions.

Codex/OpenCode remain container adapters. Authenticate them as needed:

```bash
codex login
opencode auth login
```

Codex credentials are mounted into Runtime; OpenCode uses its mounted config/data directories.

## URLs

After `ddev start`, run:

```bash
ddev describe
```

The custom services use DDEV-routed alternate HTTPS ports:

- n8n: `https://personal-coding-platform.ddev.site:5679`
- Router Swagger: `https://personal-coding-platform.ddev.site:8091/docs`
- Runtime Swagger: `https://personal-coding-platform.ddev.site:8788/docs`

## n8n thin control plane

The control-plane workflows are versioned in `n8n/workflows/`. n8n deliberately does **not** route models, run agents, access Docker, publish Git branches, call GitHub delivery APIs, or own job state. It accepts external/operator events and proxies only the allowed operation to Coding Runtime, which remains the source of truth.

After the first pull containing the workflows, or whenever a checked-in workflow changes, sync and publish them with:

```bash
ddev n8n-sync
```

The sync command prepares service-scoped n8n secrets, imports the exact checked-in workflows, publishes only their fixed IDs, restarts n8n so webhook registrations refresh, verifies the n8n container cannot see Router/provider/privileged platform secrets, and runs authenticated/unauthenticated webhook smoke checks.

Initial production webhook paths:

```text
POST /webhook/coding-platform/jobs
GET  /webhook/f94fd841-0da8-42af-a06a-17b78d5a1ea7/coding-platform/jobs/<job_id>
POST /webhook/a0db357c-167e-43c4-a692-e049aa21ef63/coding-platform/jobs/<job_id>/decision
```

The status and human-decision workflows contain dynamic `:job_id` parameters. On the pinned n8n 2.38.x line their stable `webhookId` values form the leading production-URL segment, so callers must preserve the UUIDs shown above. `ddev n8n-sync` prints the same canonical paths after publishing.

All three require the local ingress header `X-Control-Token`. The token is generated in `.ddev/.env.n8n.local` and must not be committed or shared. These DDEV webhooks are local-development endpoints unless you explicitly add a trusted tunnel/reverse proxy later.

Example job creation through n8n:

```bash
source .ddev/.env.n8n.local

curl -fsS \
  -H "X-Control-Token: $N8N_CONTROL_PLANE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "chonhac",
    "task": {
      "title": "Example task",
      "description": "Make one bounded implementation change.",
      "task_type": "implementation"
    },
    "auto_run": true
  }' \
  "https://personal-coding-platform.ddev.site:5679/webhook/coding-platform/jobs"
```

Fetch status through the control plane:

```bash
curl -fsS \
  -H "X-Control-Token: $N8N_CONTROL_PLANE_TOKEN" \
  "https://personal-coding-platform.ddev.site:5679/webhook/f94fd841-0da8-42af-a06a-17b78d5a1ea7/coding-platform/jobs/<job_id>"
```

Resolve a Runtime human-decision gate through n8n:

```bash
curl -fsS -X POST \
  -H "X-Control-Token: $N8N_CONTROL_PLANE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"approve","note":"Reviewed locally"}' \
  "https://personal-coding-platform.ddev.site:5679/webhook/a0db357c-167e-43c4-a692-e049aa21ef63/coding-platform/jobs/<job_id>/decision"
```

## Create a job

Using the direct Runtime helper remains supported:

```bash
./scripts/create-job.sh my-drupal \
  "Fix order synchronization retry" \
  "Orders occasionally fail to retry when the CRM API times out."
```

Or call `POST /v1/jobs` on Coding Runtime directly.

## Runtime lifecycle

```text
registered project
      ↓
pin source commit
      ↓
deterministic repo analysis
      ↓
Router /route
      ↓
isolated Git workspace + AI branch
      ↓
optional planner
      ↓
executor agent
      ↓
DDEV deterministic verification
      ↓
bounded commit + AI branch publish + PR
      ↓
GitHub Actions / commit-status monitoring
      ├─ success → complete
      ├─ failure → bounded repair → verify → same PR
      └─ infrastructure failure → durable delivery checkpoint / resume
```

Every workspace receives a temporary `.ddev/config.coding-platform.yaml` with a unique DDEV project name, so parallel jobs do not collide with the source project's normal DDEV environment.

Every workspace is a **self-contained `git clone --no-local` pinned to the source commit**, not a traditional Git worktree. That is deliberate: a worktree's `.git` file points back to the original repository, which would force the agent container to mount the source-repository root. The isolated clone costs a little more disk but keeps the original repo outside the agent trust boundary.

## Anti-loop behavior

Budget belongs to the job, never the model. Escalation does not reset iteration/model-call/token/time/cost counters. Router v1 enforces failure-fingerprint, no-progress, diff-oscillation, scope and hard-budget gates. Runtime records agent-reported token usage; paid OpenCode agents also accumulate per-job USD cost from the model registry (DeepSeek uses conservative peak pricing when the provider does not report cost directly).

The runtime additionally refuses to auto-replay an in-flight agent turn after a process crash; such a job becomes `interrupted` and needs an explicit `/run` request.

## Commands

```bash
ddev start
ddev stop
ddev platform-status
ddev platform-test
ddev n8n-sync
ddev logs -s router
ddev logs -s coding-runtime
ddev logs -s ddev-executor
ddev logs -s n8n
```

## PCP BuildKit isolation and resource GC

The DDEV `pre-start` hook runs `scripts/pcp-build-images.sh` before the existing
Antigravity bridge hook. The helper idempotently creates and bootstraps the
`pcp-builder` Buildx builder with the `docker-container` driver, then explicitly
builds and `--load`s fixed local image tags for `router`, `coding-runtime`, and
`ddev-executor`. Their Compose entries consume those tags and contain no
implicit `build:` section. The helper never runs `docker buildx use`, so the
user's globally selected builder is unchanged.

Host and executor access to the builder use only PCP-owned Buildx instance
metadata under `$HOST_HOME/.coding-platform/buildx`. `ddev-executor` mounts that
directory at `/home/coder/.pcp-buildx` and injects
`BUILDX_BUILDER=pcp-builder` plus that `BUILDX_CONFIG` only into its bounded
DDEV subprocesses. The host's complete `~/.docker` directory and registry
credentials are not mounted.

Read-only attribution is safe while jobs exist. Run it through the host-secret
wrapper when Runtime job-state correlation is wanted:

```bash
bash ./scripts/with-host-secrets.sh ./scripts/pcp-resource-inventory.sh
```

The report separates the dedicated PCP builder and shared/default builder,
platform images, exact `cp-*` DDEV built images, containers, volumes, and their
container references.

Resource GC is report-only by default and fails closed unless Runtime is
queryable, every Runtime job is in a stable `blocked`, `failed`, `completed`, or
`cancelled` state, and `ddev-executor` reports `active_jobs=0`:

```bash
# Report cache/image candidates; mutate nothing.
bash ./scripts/with-host-secrets.sh ./scripts/pcp-resource-gc.sh --dry-run

# Prune only pcp-builder cache older than seven days.
bash ./scripts/with-host-secrets.sh ./scripts/pcp-resource-gc.sh \
  --execute --until 168h

# Also remove exact unreferenced PCP DDEV built-image tags for only
# completed/cancelled Runtime jobs whose DDEV ownership labels match.
bash ./scripts/with-host-secrets.sh ./scripts/pcp-resource-gc.sh \
  --execute --until 168h --terminal-images
```

The GC script never removes containers, named volumes, databases, or Git
workspaces. It preserves blocked/failed job images, refuses image removal when
any container still references the image, and invokes cache cleanup only as
`docker buildx prune --builder pcp-builder ...`. It does not prune the retained
shared/default cache.

DDEV's own base web/database image acquisition can still have behavior outside
the executor-owned workspace build path. The integration proves PCP custom
service builds and executor-owned workspace DDEV subprocesses select
`pcp-builder`; it does not claim that every DDEV build on the machine does so.

## Operator shell safety

Treat the interactive Ubuntu/WSL terminal as persistent operator state. A pasted validation block must not be able to close the parent shell just because a gate intentionally returns a non-zero exit code.

Do **not** paste a block that enables `set -e` or `set -euo pipefail` in the current interactive shell and then intentionally calls `exit N` for a failed check. Depending on how the shell/session was started, that can terminate the current Ubuntu/WSL session.

For any preflight, rollout, restart, deploy, health, or other operator check that may intentionally fail, isolate the block in a subshell or standalone script. Preferred pasted pattern:

```bash
(
  set -uo pipefail

  echo "== check =="
  if ! some_read_only_check; then
    echo "GATE=BLOCKED"
    exit 20
  fi

  echo "GATE=PASS"
)
RC=$?

echo "CHECK_EXIT_CODE=$RC"
if [[ $RC -ne 0 ]]; then
  echo "Check did not pass. Parent shell is still available."
fi
```

The parentheses create a child shell. `exit 20` terminates only that child process; after `)` the parent shell remains usable and can inspect `$?`.

Operational command-authoring rules:

- keep mutating restart/rebuild/deploy commands out of a preflight block until all read-only gates have passed;
- when a gate needs controlled failure, return non-zero from a subshell or standalone script, not from the Human Owner's parent interactive shell;
- do not rely on `set -e` in the parent shell as control flow for operator guidance;
- print explicit `PASS`/`BLOCKED` and exit-code evidence so a later chat/agent can reason from the captured output safely.

These rules also apply to commands generated by ChatGPT, Codex, or platform agents; see `AGENTS.md` under **Operator command authoring**.

## Security note

`ddev-executor` mounts Docker's socket, which is effectively host-root-equivalent capability. It is deliberately not externally exposed and does not accept arbitrary command text. Keep the platform local-only and do not expose this internal Docker network to untrusted users.

The n8n service is intentionally lower privilege: it receives the Runtime API token and its own ingress/encryption secrets, but its Compose definition scrubs Router, provider, Antigravity and privileged internal tokens inherited from DDEV's global environment. `ddev n8n-sync` verifies this boundary inside the running container before publishing control-plane traffic.

## Current v1 boundaries

- Runtime supports bounded successful commits, non-force `ai/*` branch publishing, PR create/update and GitHub CI monitoring when project policy grants those capabilities.
- GitHub CI failures can feed bounded diagnostics back into the Runtime repair loop and update the same branch/PR. Auto-merge remains off for the current real-project policy and production deployment remains forbidden.
- n8n is intentionally thin: current responsibilities are job ingress, job status and human-decision forwarding. External notifications, scheduled intake and third-party event connectors are future control-plane extensions, not Runtime logic.
- Per-job token/cost enforcement is active. Cross-job/monthly provider quota telemetry is the next layer; it is not yet inferred automatically from subscription dashboards.

## Why LiteLLM is not a running service in v1

The registry already reserves `adapter: litellm` for Groq, Cloudflare and Luna utility calls, but Router v1 is deterministic-first and Coding Runtime v1 does not need raw utility-model calls yet. Starting an idle gateway would add another moving part without improving the execution path. When semantic classification/context compaction is enabled, LiteLLM can be added as another DDEV custom service without changing the Router/Coding Runtime contracts.

## Model IDs

`config/models.yml` currently uses `gpt-5.6-sol` for the normal Codex Plus pool and `gpt-6-astra` for frontier escalation. Plus includes Sol and Astra access subject to your account's current Codex allowance/availability. OpenCode model IDs are catalog/provider IDs; if a provider changes an alias, verify it once with `opencode models` and update only `config/models.yml`.

## v1.0.3 integration fixes

- Router API tests now authenticate with the actual `ROUTER_API_TOKEN` supplied by DDEV instead of the placeholder `change-me`.
- The constrained DDEV executor image now includes Docker Buildx and reports Buildx health explicitly. DDEV requires Buildx for project image builds.

## v1.0.5 writable service HOME fix

The coding-runtime and ddev-executor images now prepare `/home/coder` using the host DDEV UID/GID. This fixes CLI failures such as OpenCode being unable to create `/home/coder/.cache`, while keeping the services non-root at runtime.

## v1.0.6 quota-aware failover and strict completion

- Coding-agent provider failures such as usage/quota exhaustion, rate limits, authentication failures, and provider outages are detected even when a CLI exits with code 0.
- A provider-level failure disables that provider for the current job and reroutes planner/executor/evaluator work to another eligible provider without consuming repair iterations.
- Provider failovers have their own hard budget and never reset the job budget.
- Implementation tasks inferred to require repository changes now include `material_change` in the Definition of Done. An empty diff can no longer be accepted as a successful implementation.
- Runtime now completes only when Router returns `complete`; `continue` no longer aliases success.
- Agent success itself is part of completion state, preventing green deterministic checks from hiding an agent invocation failure.
- Known provider exhaustion can be declared before a job with `CODING_DISABLED_PROVIDERS=openai ./scripts/create-job.sh ...`, avoiding a wasted probe call.

## v1.0.9 Antigravity migration

- Removed Gemini CLI from the runtime image, registry, routing policy, mounts, tests and documentation. Google Individual coding now uses Antigravity CLI.
- Added `antigravity_free` (`provider: google_antigravity`, `adapter: antigravity_host`, `quota_group: antigravity_individual`).
- Added a constrained WSL-host bridge because Antigravity Individual account sessions live in the OS keyring and should not be mounted into Docker.
- The bridge accepts only authenticated `/health` and `/run` requests, rejects workspaces outside `$CODING_WORKSPACES_ROOT`, and never accepts arbitrary command text.
- Antigravity runs headlessly with JSON output, native sandboxing and bounded execution timeout. Token usage from `agy` is fed into the existing per-job budget counters.
- `ddev start` starts the bridge through a host hook; `ddev stop` stops it. `ddev platform-status` now reports bridge health.
- Routing prefers Antigravity for Fast/Standard work and includes it as a Complex planner/executor option. Critical routing remains biased toward stronger independent pools.

To temporarily disable the Antigravity pool for one job:

```bash
CODING_DISABLED_PROVIDERS=google_antigravity ./scripts/create-job.sh ...
```

## v1.0.10 Test harness fix

- Antigravity async unit tests use `asyncio.run(...)`, so `pytest-asyncio` is not required.
- Runtime pytest cache is disabled in `ddev platform-test` because `/app` is intentionally read-only to the runtime user.
- No routing or runtime execution behavior changed.
