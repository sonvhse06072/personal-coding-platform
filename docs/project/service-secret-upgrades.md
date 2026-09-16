# Service-Secret Upgrade Procedure

This document covers existing local installations when a source update introduces or changes service-scoped credential names.

## Invariant

Platform credentials remain service-scoped. Never copy bearer tokens or provider credentials back into the shared `.ddev/.env`, prompts, logs, issue comments, or repository files.

The canonical migration helper is:

```bash
./scripts/scope-service-secrets.sh
```

It preserves existing real values, refuses conflicting values, generates only missing shared secrets, writes the intended service-local files, removes migrated credentials from the global DDEV environment, and never needs the credential values to be printed.

## Existing-install upgrade order

When merged source adds or changes a service credential, an existing installation must not assume that `git pull` or a DDEV rebuild will create the new local secret automatically.

Use this order:

1. Require all Runtime jobs to be stable blocked/terminal and require zero active executor/Antigravity work before any restart or rebuild.
2. Run `./scripts/scope-service-secrets.sh` on the host. If it reports conflicting existing values, stop and repair that configuration deliberately; do not overwrite one side blindly.
3. Rebuild/restart DDEV only after the safety gate passed. The rebuild/restart is what loads the updated service-local environment into the containers.
4. Run `ddev platform-status` and inspect the non-secret `credential-boundary` result.
5. For rollout or merge-path acceptance, additionally run `./scripts/service-secret-status.sh --strict`; require exit code 0 before creating validation work.

Do not put the migration command inside a read-only preflight block. It mutates only local secret files, so execute it only after the read-only active-work gate has passed.

## Credential-boundary status

`./scripts/service-secret-status.sh` reports booleans only. It does not print credential values.

The strict gate requires:

- coding-runtime: `PLATFORM_INTERNAL_TOKEN` present; `GITHUB_DELIVERY_TOKEN` and `TELEGRAM_BOT_TOKEN` absent;
- ddev-executor: `PLATFORM_INTERNAL_TOKEN` and `GITHUB_DELIVERY_TOKEN` present; `RUNTIME_API_TOKEN` absent;
- n8n: `RUNTIME_API_TOKEN` present; `GITHUB_DELIVERY_TOKEN` and `PLATFORM_INTERNAL_TOKEN` absent.

A public service `/health` response is not sufficient evidence for this boundary. Runtime health can be green even when a privileged Runtime -> ddev-executor credential is missing because the executor health endpoint itself is intentionally unauthenticated.

## Human-operator shell safety

Any pasted gate that may return non-zero must follow the repository `AGENTS.md` operator-command rule: run controlled failure inside a subshell or standalone script so the Human Owner's parent Ubuntu/WSL shell remains available.
