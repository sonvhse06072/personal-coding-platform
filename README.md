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
