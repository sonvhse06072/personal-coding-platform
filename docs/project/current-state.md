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

- PR #90 (`Recover wall-budget-bounded agent timeouts safely`) is merged at main commit `f698ccc5a687ecc012305c17391c5b40194cb29d`; issue #89 is closed.
- PR #92 (`Make Codex unattended execution fail closed`) is merged at main commit `7d05c68dc36a481fbece98540bc4d0e6888643a2`; issue #91 is closed.
- `main` Runtime source behavior is now `1.0.32`, combining the `1.0.31` wall-budget timeout recovery with explicit unattended Codex policy: read-only planner/evaluator, workspace-write execute/repair, `approval_policy="never"`, and workspace-write network disabled.
- GitHub Actions run #187 passed on the exact PR #92 merge commit.
- The last fully recorded deployed platform evidence still predates this rollout: Router `1.0.15`, Runtime `1.0.30`, model registry `v7`, routing policy `v7`, OpenCode adapter available, n8n healthy, and OpenRouter secret scoped only to Runtime. Runtime `1.0.32` rollout verification is in progress and must be recorded from live evidence rather than assumed from source state.
- OpenRouter rollout is operational with explicit upstream free model `cohere/north-mini-code:free`; stable logical PCP model ID remains `openrouter_qwen3_coder_free`.

## Active work

### 1. Runtime `1.0.32` rollout and DEC-025C recovery

- Human Owner merged PR #92.
- A bounded Codex smoke using the new explicit policy was attempted with `--cd /app` and failed before prompt execution with `Not inside a trusted directory and --skip-git-repo-check was not specified.`
- That failure does not show rejection of `approval_policy="never"` or `sandbox_workspace_write.network_access=false`; it shows `/app` is not an acceptable trusted Git working tree for `codex exec`.
- Do not weaken the smoke by adding `--skip-git-repo-check`, because Runtime does not use that bypass. Re-run the smoke in a disposable Git repository or an existing trusted job workspace; prefer a disposable repo so the C1 workspace remains untouched.
- Successful smoke evidence should include the exact `CODEX_POLICY_OK` agent message and a terminal `turn.completed` event before relying on this CLI policy for C1.

### 2. Operator command quoting guidance — issue #93 / PR #95

- Issue #93 records durable copy/paste command-authoring guidance requested by the Human Owner.
- Branch: `ai/docs-shell-command-safety-93`.
- PR: #95 (`Document safer operator shell command patterns`).
- `AGENTS.md` now requires future sessions to:
  - avoid fragile `python3 -c '...'` forms when embedded Python also contains single quotes;
  - prefer `.format()` or heredocs when they reduce nested quoting risk;
  - verify shell and Python quoting in `curl | python3` pipelines;
  - prefer readable multi-line commands over fragile one-liners for moderately complex commands.
- Documentation-only change; no Runtime, Router, provider, orchestration, security, budget, or deployment behavior change.
- Human Owner must manually merge after green CI; do not auto-merge.

### 3. DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- C1 still must satisfy two evaluator findings before its normal PR/CI/manual-merge gate:
  1. derive/verify deployed release identity from the deployed tree instead of trusting local Git SHA/fingerprint supplied by `run.sh`;
  2. provide deterministic passing evidence for the DEC-025C-specific Python/PHP/shell/static checks required by AC6.
- Bounded recoveries already approved on the same job without resetting usage:
  - `max_model_calls`: `14 -> 18`;
  - `max_repair_iterations`: `2 -> 3`;
  - `max_iterations`: `8 -> 10`.
- Last pre-timeout live counters included model calls `14/18`, tool calls `36/160`, test runs `6/14`, wall time about `63.515/70`, and repair iterations `2/3`.
- C1 remains terminal `failed` from the Runtime `1.0.30` wall-budget timeout bug until merged recovery behavior is live and the official compatibility control action reopens the exact same job.
- Do not manually change DB state, create a replacement C1 job, or call generic `/v1/jobs/{job_id}/run` to bypass orchestration controls.
- C2/C3 remain gated until C1 satisfies both evaluator findings and reaches its normal PR/CI/manual-merge gate.

## Next safe sequence

1. Wait for PR #95 CI on its exact final head; Human Owner manually merges it when green so future sessions receive the durable command-authoring guidance.
2. Verify live platform health and Runtime `1.0.32`; do not infer deployed version from repository source alone.
3. Re-run the bounded non-mutating Codex policy smoke inside a disposable Git repository, without `--skip-git-repo-check` and without touching C1.
4. After `CODEX_POLICY_OK` plus terminal `turn.completed`, trigger orchestration reconciliation and inspect the newly materialized live control action for the same C1 job. Expected only if the compatibility matcher validates the persisted legacy state: `max_wall_time_minutes +20`.
5. Execute recovery only through the official live-revalidated control action. Preserve the same job/workspace/source commit/diff/progress/counters.
6. Monitor C1 through verification/evaluation/delivery. Any later budget extension must be based on a fresh live blocker/action only.
7. C1 must fix both evaluator findings and reach PR/green-CI/Human-merge before C2/C3 proceed.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight. Terminal `failed`/stable blocked states may be restarted when needed for an approved rollout.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.
- Developer agents remain inside the approved isolated workspace/sandbox boundary; avoiding human approval prompts is not permission to grant host-level full access.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
