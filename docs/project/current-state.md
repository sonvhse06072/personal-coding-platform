# Current Project State and Handoff

Status: mutable continuity document. Update this file whenever a material decision, implementation state, blocker, rollout decision, or handoff changes. Durable architecture/product/policy decisions belong in the relevant topical source-of-truth document.

Last updated: 2026-09-15

## How to resume in a new chat or agent session

Read, in order:

1. repository-root `AGENTS.md`;
2. `docs/project/README.md`;
3. this file;
4. every topical project document referenced below;
5. the active GitHub issue/PR and current branch diff before editing.

Do not rely on chat history as project state. Repository docs and current executable evidence win according to the authority order in `AGENTS.md`.

## Current repository state

- PR #97 delegates routine in-frame PR review/merge to PM after required evidence, review and CI gates pass; protected Human Owner decision boundaries remain unchanged.
- PR #102 fixes control-action notification rematerialization when the valid action set changes.
- PR #106 makes Telegram callback acknowledgement best-effort so Telegram HTTP acknowledgement failures cannot suppress a valid Runtime control action.
- PR #118 expands sanitized read-only Developer Activity across supported providers and Runtime verification/block events. Raw reasoning, prompts, credentials and unrestricted environment data remain excluded.
- PR #120 is merged at `67db7b561a62c910cfc7840e510c7a836f91055a`, aligning source Runtime release identity to `1.0.34` for the Developer Activity generation.
- PR #126 (`Make Antigravity model, quota and effort aware`) is merged to main at `f297404f96814cd7863a64ea6b0a2c926e7813fd`; its exact-head CI passed all four jobs. Source state after #126 is Router `1.0.16`, Runtime `1.0.35`, model registry `v8`, routing policy `v8`.
- PR #126 registers explicit Antigravity Flash/Pro/Sonnet models, routes `low|medium|high` effort through the host adapter, separates exact-model quota failures from shared quota groups and provider-wide failures, and preserves same-job legacy recovery semantics.
- Issue #127 (`Add proactive provider quota telemetry and reset awareness`) is active on branch `ai/provider-quota-telemetry-127`. It adds authoritative-first Codex and Antigravity usage/reset collection, durable quota snapshots, Router quota pressure, PM/coding pre-route refresh, reset reconciliation, read-only API/dashboard visibility and deterministic tests. Source Runtime is being advanced to `1.0.36`; Antigravity host bridge source is being advanced to `1.7` for the constrained read-only quota endpoint.
- No #126/#127 local rollout has been performed during this work.
- Last verified local deployment before these source changes remains Router `1.0.15`, Runtime `1.0.33`, ddev-executor `1.0.14`, Antigravity bridge `1.6`, model registry `v7`, routing policy `v7`, with n8n healthy.
- Codex CLI `0.154.0` is the last locally verified installed CLI version in platform status evidence.

## Provider quota telemetry direction

The Human Owner identified that reactive quota failures are insufficient: PCP must proactively know authoritative usage percentage and reset time when providers expose them.

Approved implementation rules for issue #127:

- Codex usage comes from the installed/authenticated `codex app-server` protocol via `account/rateLimits/read`; PCP does not parse OAuth credentials or call private backend endpoints with hand-managed tokens.
- Antigravity usage comes through the constrained authenticated host bridge invoking read-only `agy -p "/usage" --output-format json`; quota reads do not start a coding turn or grant extra workspace/host permissions.
- Poll approximately every five minutes, retain the latest successful durable snapshot, mark old data stale, and refresh best-effort before routing when stale.
- Fresh `used_percent` becomes Router `quota_pressure`; authoritative exhaustion can disable only the mapped quota resource.
- A fresh authoritative reset/capacity observation may clear an old **quota-only** marker but cannot clear auth, provider/bridge health or deterministic model failures.
- Unknown/stale/failed telemetry never fabricates a percentage or reset timestamp and never disables a provider merely because collection failed.
- Dashboard/API surfaces are read-only; this work does not add a quota-reset mutation or budget-extension path.

Durable policy details live in `docs/project/provider-policy.md`.

## Effective PM merge governance

Human Owner decision adopted on 2026-09-14 through issue #96 / PR #97:

- PM may review and merge routine PRs autonomously when the change stays inside the already-approved project frame.
- PR, deterministic verification, required independent review, and green CI remain mandatory gates.
- PM must inspect scope, WorkOrder/Task Contract, verification evidence, review findings, CI, risks and Human Owner decision triggers before merge.
- Developer agents still cannot merge and must not receive GitHub merge credentials.
- Force push remains forbidden.
- Production deployment is separate from PR merge and remains under existing Human Owner decision policy.
- Human Owner approval is still required for protected scope, architecture, major dependency/service, security/trust-boundary, destructive-data, production-policy, high-authority governance and material budget decisions.

Issue #98 separately tracks constrained PM-controlled PR merge in Runtime.

## DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- Workspace and durable job identity must remain unchanged across any approved recovery.
- C1 still must satisfy the existing evaluator findings around deployed release identity and deterministic DEC-025C-specific verification evidence.
- Previous bounded same-job recoveries preserved all consumed usage and workspace/diff state.
- Latest authoritative block is `execution_budget_exhausted`, not a provider reset assertion. Persisted metrics at that block were: iteration `10/10`, model calls `17/18`, tool calls `47/160`, test runs `8/14`, wall time `76.652/90` minutes, repair iterations `2/3`.
- The currently exhausted dimension is `max_iterations`; the valid bounded action is `+2 iterations`. Do not pre-extend unrelated dimensions. If another budget becomes exhausted later, handle it sequentially through a fresh control action.
- C1 is intentionally kept stably blocked while #127 is implemented/CI-reviewed. Do not manually mutate its database/job state, create a replacement job, reset counters or call generic `/v1/jobs/{job_id}/run`.
- C2/C3 remain gated until C1 satisfies its current gates and normal delivery/merge policy.

## Next safe sequence

1. Complete issue #127 implementation and deterministic tests on `ai/provider-quota-telemetry-127`.
2. Open/review the PR, require exact-head green CI, and merge only if no new protected Human Owner decision is introduced.
3. Before any local rollout, re-read C1 and require the same job id to remain non-active/stably blocked.
4. Roll out only the components whose source changed: Router/config from #126 as required, Runtime `1.0.36`, and Antigravity bridge `1.7`; do not restart unrelated n8n/ddev-executor services without evidence they require it.
5. Verify deployed `/health`, registry/policy versions and bridge safety before touching C1.
6. Query the new read-only provider quota endpoint and compare Codex/Antigravity percentages/reset windows with provider CLI/UI evidence. If a provider response cannot be mapped confidently, leave that value unknown rather than inventing state.
7. Re-read C1 after rollout and require job/workspace/counters to remain unchanged apart from safe startup/observability metadata.
8. Only then rematerialize normal owner controls and decide whether to apply the still-valid bounded `+2 iterations` recovery.
9. Once C1 becomes active, do not rebuild/restart Runtime/DDEV/n8n until another safe terminal or stable blocked state.

## Global operational gates

- Do not commit implementation work directly to `main`; use issue -> `ai/*` branch -> tests/CI -> PR.
- Never force push.
- Developer agents never merge.
- PM may merge only after required gates pass and only when no unresolved Human Owner decision trigger exists.
- Human Owner remains final authority over important protected decisions listed in the Constitution.
- Do not restart Runtime/DDEV while a job is in flight. Terminal/stable blocked states may be restarted only for an approved rollout.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.
- Developer agents remain inside the approved isolated workspace/sandbox boundary; avoiding human approval prompts is not permission to grant host-level full access.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
