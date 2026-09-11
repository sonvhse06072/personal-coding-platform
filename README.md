# Personal Coding Platform v1

A DDEV-managed, personal coding automation platform. Daily startup is intentionally one command:

```bash
ddev start
```

## Why DDEV for the whole platform?

DDEV supports custom Docker Compose services through `.ddev/docker-compose.*.yaml`, so the platform can remain one Git repository while keeping Router, Coding Runtime, n8n and the privileged DDEV executor isolated as separate services.

The Coding Runtime **does not** receive `/var/run/docker.sock` or the source-repository root. Only `ddev-executor` has Docker and source-repository access and it accepts a project ID + named phase (`preflight`, `targeted_tests`, `static_analysis`, `full_tests`, `cleanup`). The actual shell commands come only from checked-in `config/projects.yml`.

## Components

- **n8n** — control plane and external event orchestration.
- **router** — deterministic-first complexity/profile/model selection and hard execution budgets.
- **coding-runtime** — job persistence, repository analysis, isolated Git workspaces, agent adapters, deterministic verification, repair/escalation loops.
- **Antigravity host bridge** — constrained WSL-host bridge that runs the signed-in `agy` CLI inside isolated job workspaces; it keeps OS-keyring credentials outside Docker.
- **ddev-executor** — tiny privileged service that can operate target DDEV projects without exposing Docker socket to the agents.
- **PostgreSQL** — the standard DDEV `db` service; n8n and runtime persistence share it.

## One-time setup

Prerequisites on WSL: Docker/Docker Desktop integration, DDEV, Git, Python 3 and a signed-in Antigravity CLI (`agy`).

```bash
./scripts/bootstrap.sh
```

The script creates `.ddev/.env`, generates local service secrets, detects the Docker socket group, creates `$HOME/.coding-platform/workspaces`, and starts the platform.

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

## Create a job

Using the helper:

```bash
./scripts/create-job.sh my-drupal \
  "Fix order synchronization retry" \
  "Orders occasionally fail to retry when the CRM API times out."
```

Or call `POST /v1/jobs` on Coding Runtime.

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
DDEV verification through constrained executor
      ↓
Router /reassess
      ├─ continue repair
      ├─ monotonic escalation
      ├─ human decision
      ├─ stop / blocked
      └─ complete
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
ddev logs -s router
ddev logs -s coding-runtime
ddev logs -s ddev-executor
ddev logs -s n8n
```

## Security note

`ddev-executor` mounts Docker's socket, which is effectively host-root-equivalent capability. It is deliberately not externally exposed and does not accept arbitrary command text. Keep the platform local-only and do not expose this internal Docker network to untrusted users.

## Current v1 boundaries

- Runtime can commit successful work if Router grants permission.
- Push, PR creation and merge are intentionally left for the next integration layer; the Router already returns permission flags for them.
- Per-job token/cost enforcement is active. Cross-job/monthly provider quota telemetry is the next layer; it is not yet inferred automatically from subscription dashboards.
- n8n workflow is intentionally thin and comes after Router + Runtime integration.

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
