# Current Project State and Handoff

Status: mutable continuity document. Update this file whenever a material decision, implementation state, blocker, rollout decision, or handoff changes. Durable architecture/product/policy decisions belong in the relevant topical source-of-truth document.

Last updated: 2026-09-14

## How to resume in a new chat or agent session

Read, in order:

1. repository-root `AGENTS.md`;
2. `docs/project/README.md`;
3. this file;
4. every topical project document referenced below;
5. the active GitHub issue/PR and current branch diff before editing.

Do not rely on chat history as project state. Repository docs and current executable evidence win according to the authority order in `AGENTS.md`.

## Mandatory continuity rule

Before a material task is complete or handed off, update the relevant topical document for durable decisions and update this file for mutable execution state. Handoff prompts to Codex/platform agents must require those documentation updates as part of Definition of Done.

## Current repository state

- PR #78 (`Handle reassessment budget guards and Vietnamese Telegram UX`) is merged.
- PR #81 (`Complete OpenRouter free-tier routing policy`) is merged; CI run #155 passed on its exact head.
- PR #82 (`Make project docs the cross-chat continuity source`) is merged.
- PR #84 (`Reconcile post-merge versions and rollout state`) is merged; final CI run #162 passed.
- PR #86 (`Replace withdrawn OpenRouter free model with North Mini Code`) is merged; exact head `f7eafe041a3aeed709b7af55e15bcfb2b6737ae6` passed CI run #167.
- `main` was verified at merge commit `cd525d8dfd346bfc6293c8c2641f3c95a4a37799` after PR #86.
- Local rollout is complete: Router `1.0.15`, Runtime `1.0.30`, model registry `v7`, routing policy `v7`, OpenCode adapter available, n8n healthy, OpenRouter secret scoped only to Runtime.
- Deployed Runtime/OpenCode smoke passed with `openrouter/cohere/north-mini-code:free` in non-mutating plan mode.

## Active work

### 1. OpenRouter rollout status

Durable provider policy: `docs/project/provider-policy.md`.

- Operational issue: `personal-coding-platform` #87.
- PR #86 is merged and locally activated.
- Active explicit upstream free model: `cohere/north-mini-code:free`.
- Stable logical PCP model ID remains `openrouter_qwen3_coder_free` for durable route-history/provider-state compatibility; registry `model:` slug is authoritative.
- OpenRouter free is effectiveness-first. ZDR and `data_collection=deny` are not required, but secret boundaries remain strict and OpenCode sharing remains disabled.
- Nemotron remains inactive because current provider-health semantics can disable the entire OpenRouter provider after a provider-level failure.
- OpenRouter rollout gate is complete. Current work is C1 recovery/verification.

### 2. DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- Evaluator findings that C1 still needs to satisfy:
  1. derive/verify deployed release identity from the deployed tree instead of trusting local Git SHA/fingerprint supplied by `run.sh`;
  2. provide deterministic passing evidence for the DEC-025C-specific Python/PHP/shell/static checks required by AC6.
- First bounded recovery extended `max_model_calls` from `14` to `18` and resumed the same job without resetting usage.
- Second bounded recovery action `vNqbP1aduh_RzGKxnvhz_njI` was executed through the official Runtime endpoint after the Telegram callback remained pending. It extended `max_repair_iterations` from `2` to `3`, used `2`, and resumed the same job.
- After that repair-budget recovery C1 returned to `verifying`, then blocked again with `reason=execution_budget_exhausted`.
- Current live Telegram advisory identifies **iterations** as the newly exhausted dimension: iterations `8/8`, model calls `14/18`, tool calls `36/160`, test runs `6/14`, wall time `63.515/70`, repair iterations `2/3`.
- Therefore the only currently authorized bounded recovery is **`max_iterations +2`**. Model calls and repair iterations are not currently exhausted and must not be extended again unless a future live blocker specifically exhausts them.
- Because the previous Telegram control transport did not execute the repair action, prefer fail-closed verification for this new state: identify the fresh pending `budget_extend` action and confirm payload exactly `{"dimension":"max_iterations","increment":2}` before executing it once through the official Runtime endpoint if still pending.
- Do not force-complete C1, do not call generic `/v1/jobs/{job_id}/run`, do not mutate DB state manually, and do not create a replacement job. C2/C3 remain gated.

### 3. Telegram control rollout

- Issue #77 / PR #78 are merged and n8n workflows are locally synced.
- Owner-facing Telegram messages/actions are localized to Vietnamese; stable machine reason codes remain unchanged.
- Runtime correctly surfaced sequential bounded recovery gates: `+4 model calls`, then `+1 repair iteration`, and now `+2 iterations`.
- The prior `+1 repair` Telegram callback did not execute; CLI execution of the exact pending action through the same official Runtime endpoint succeeded. Treat Runtime action state as authoritative rather than assuming a button press completed.

## Next safe sequence

1. Read-only inspect current C1 `budget_extend` actions and identify the fresh pending row with payload exactly `dimension=max_iterations`, `increment=2`.
2. If that row is pending and current, execute that exact action once through `POST /v1/control-actions/{action_id}/execute` using configured owner/chat identity.
3. Confirm authorization changes `max_iterations` from `8` to `10`, used `8`, and resumes the same C1 job.
4. While C1 is in flight, monitor only; do not restart services, tick orchestration for recovery, or execute another control action.
5. If C1 reaches delivery/PR creation, follow the normal CI/manual-merge gate. If it blocks again, inspect the new live reason/counters/fresh action and extend only that current exhausted dimension.
6. C1 must fix both evaluator findings and reach the normal PR/CI/manual-merge gate before C2/C3 proceed.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
