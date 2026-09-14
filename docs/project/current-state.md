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
- PR #88 (`Reconcile post-OpenRouter rollout state`) is merged; current `main` merge commit is `3129dad6ea876cd659c9518d4080d3fa4cb366c2`.
- Deployed platform before issue #89: Router `1.0.15`, Runtime `1.0.30`, model registry `v7`, routing policy `v7`, OpenCode adapter available, n8n healthy, OpenRouter secret scoped only to Runtime.
- Deployed Runtime/OpenCode smoke passed with `openrouter/cohere/north-mini-code:free` in non-mutating plan mode.

## Active work

### 1. Runtime wall-budget timeout recovery — issue #89

- Issue: `personal-coding-platform` #89 (`Recover wall-budget-bounded agent timeouts instead of failing jobs`).
- Branch: `fix/wall-budget-agent-timeout-89`.
- Trigger: DEC-025C C1 resumed after bounded budget extensions, then a Codex invocation received an approximately `376s` timeout derived from the remaining job wall-time budget. `run_command()` raised a generic RuntimeError and the worker loop incorrectly persisted the job as terminal `failed` instead of stopping at a recoverable wall-time budget gate.
- Required forward behavior:
  - coding-command timeout is represented by a typed exception while preserving whole-process-group termination;
  - planner/executor/evaluator timeouts are reclassified as budget exhaustion only when the job's remaining wall-time is the limiting deadline;
  - ordinary per-call timeouts while wall-time remains are not fabricated into budget exhaustion;
  - elapsed progress/checkpoint are persisted before the recoverable block;
  - same job/workspace/counters remain intact.
- Compatibility behavior for the already-failed C1 is intentionally narrow: Runtime recognizes only the legacy terminal timeout shape whose recorded timeout closely matches the wall time remaining at the last durable progress checkpoint. That state may expose only the normal bounded `max_wall_time_minutes +20` recovery action; unrelated failed jobs must fail closed.
- Runtime behavior changes from `1.0.30` to target `1.0.31`; Router/model policy is unchanged.
- Current implementation branch includes the typed timeout, wall-budget classification, legacy failed-job compatibility, focused regression tests, and version bump. Full CI and Human Owner manual merge are still required before rollout.

### 2. DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- C1 still must satisfy two evaluator findings before its normal PR/CI/manual-merge gate:
  1. derive/verify deployed release identity from the deployed tree instead of trusting local Git SHA/fingerprint supplied by `run.sh`;
  2. provide deterministic passing evidence for the DEC-025C-specific Python/PHP/shell/static checks required by AC6.
- Bounded recoveries already approved on the same job without resetting usage:
  - `max_model_calls`: `14 -> 18`;
  - `max_repair_iterations`: `2 -> 3` via action `vNqbP1aduh_RzGKxnvhz_njI`;
  - `max_iterations`: `8 -> 10` via action `ymYxMQEsO4qCfaJqbc66H2gL`.
- Last pre-timeout live counters included model calls `14/18`, tool calls `36/160`, test runs `6/14`, wall time about `63.515/70`, and repair iterations `2/3`.
- Current C1 state is terminal `failed` under Runtime `1.0.30` because the wall-budget-bounded Codex command timed out after about `376s`. This terminal state is the Runtime bug being fixed by issue #89; do not manually change the DB status, create a replacement C1 job, or call generic `/v1/jobs/{job_id}/run` to bypass orchestration controls.
- C2/C3 remain gated until C1 satisfies both evaluator findings and reaches its normal PR/CI/manual-merge gate.

### 3. OpenRouter / Telegram control status

Durable provider policy: `docs/project/provider-policy.md`.

- OpenRouter rollout is complete and operational; active explicit upstream free model is `cohere/north-mini-code:free`.
- Stable logical PCP model ID remains `openrouter_qwen3_coder_free`; registry `model:` slug is authoritative.
- OpenRouter free remains effectiveness-first; secret boundaries and disabled OpenCode sharing remain mandatory.
- Telegram owner controls are localized to Vietnamese and use Runtime-owned durable action state. Runtime previously surfaced sequential bounded C1 gates `+4 model calls`, `+1 repair iteration`, and `+2 iterations` correctly.
- Treat Runtime action state as authoritative rather than assuming a Telegram button press executed successfully.

## Next safe sequence

1. Finish issue #89 on `fix/wall-budget-agent-timeout-89`: focused tests, Runtime `1.0.31`, continuity docs, green CI, then Human Owner manual merge. Do not auto-merge.
2. C1 is terminal `failed`, so after #89 is merged it is safe to pull merged `main` and restart/sync only as required to activate Runtime `1.0.31`.
3. Verify platform health and Runtime `1.0.31` after rollout.
4. Trigger orchestration reconciliation and inspect the newly materialized live control action for the same C1 job. Expected only if the compatibility matcher validates the exact persisted legacy state: `max_wall_time_minutes +20`.
5. Execute recovery only through the official live-revalidated control action. Do not mutate DB state or create a replacement job.
6. Monitor the same C1 through verification/evaluation/delivery. Any later budget extension must be based on a fresh live blocker/action only.
7. C1 must fix both evaluator findings and reach PR/green-CI/Human-merge before C2/C3 proceed.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight. Terminal `failed`/stable blocked states may be restarted when needed for an approved rollout.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
