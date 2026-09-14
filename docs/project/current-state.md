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

- `personal-coding-platform` PR #78 (`Handle reassessment budget guards and Vietnamese Telegram UX`) is merged.
- PR #81 (`Complete OpenRouter free-tier routing policy`) is merged. Its exact head `6a59b6a1ac9e15778794c043cf78bb7bf519c1f2` passed GitHub Actions tests run #155.
- PR #82 (`Make project docs the cross-chat continuity source`) is merged and this continuity process is now active.
- After PR #81, `main` was verified at merge commit `596fcc5b6a62ce948d782a1cac3fa99d00386a96`.
- Merged code is not automatically considered locally activated. Runtime/Router/n8n health and version evidence must be checked after a safe rollout.

## Active work

### 1. Post-merge version / rollout reconciliation

- Issue: `personal-coding-platform` #83.
- PR: #84, `Reconcile post-merge versions and rollout state`.
- Branch: `fix/post-merge-version-state-83`.
- Purpose: make post-#78/#81 behavior distinguishable in durable route/health evidence before rollout.
- Version evidence implemented on the branch:
  - Router app `1.0.15`;
  - Runtime app `1.0.29`;
  - model registry `v6`;
  - routing policy `v6`.
- This task does not change routing/provider behavior; it only reconciles version markers, version tests, and docs.
- GitHub Actions run #161 passed all suites after updating the stale staffing version assertions.
- Current gate: Human Owner manual merge of PR #84 -> only then local rollout.

### 2. DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- Last known Runtime status: `blocked` in `reassessment` with top-level reason `reassessment_stopped`.
- Nested reassessment evidence: `model-call budget exhausted` with `hard_budget_guard`.
- Evaluator did **not** accept C1. Two material findings remain:
  1. deployed release identity must be derived/verified from the deployed tree instead of trusting local Git SHA/fingerprint supplied by `run.sh`;
  2. AC6 needs deterministic passing evidence for the DEC-025C-specific Python/PHP/shell/static checks.
- PR #78 now supports bounded recovery for this exact reassessment class. For the recorded C1 state, the first authorized recovery dimension is `+4 model calls`; later repair/iteration extensions are allowed only if they become the current live blocker.
- Do not force-complete C1. Do not create a replacement job merely to bypass recovery state. C2/C3 remain gated.
- Before any restart or recovery action, query the local Runtime again; the status above is only the last known durable evidence in docs.

### 3. Telegram control rollout

- Issue #77 / PR #78 are merged.
- Owner-facing Telegram notifications/actions are localized to Vietnamese while stable machine reason codes remain English.
- `reassessment_stopped + hard_budget_guard` can produce a bounded, live-dimension-revalidated owner action; stale/wrong-dimension actions fail closed.
- Local activation is still pending verification.
- Because #78 changed n8n workflows, activation requires `ddev n8n-sync`, which restarts the DDEV stack during synchronization. Run it only when C1 is confirmed stable blocked/terminal, never while a job is in flight.

### 4. OpenRouter opportunistic free provider rollout

Durable policy: `docs/project/provider-policy.md`.

- Issue #79 / PR #81 are merged.
- Exact model: `openrouter/qwen/qwen3-coder:free`; `openrouter/free` is forbidden for durable coding jobs.
- PCP Router remains authoritative for model selection, cross-model failover, budgets and provider/model state.
- OpenRouter is eligible only for fast/standard executor work and bounded complex evaluator/reviewer use; critical and Product Manager use are excluded.
- OpenCode is constrained to the selected OpenRouter provider/model, sharing disabled, and request policy requires `data_collection=deny`, `zdr=true`, `require_parameters=true`; same-model endpoint fallback may remain enabled.
- Static verification is green via PR #81 / CI run #155. No live OpenRouter inference/privacy smoke has yet been recorded.
- `OPENROUTER_API_KEY` must be configured only in `.ddev/.env.coding-runtime.local`; never print or commit it.
- Before relying on the free provider, perform one bounded live smoke that proves the selected model currently has an eligible privacy-compliant endpoint. If it does not, fail closed and keep PCP fallback behavior; do not relax privacy.
- Do not present an authoritative free-quota-remaining number.

## Next safe rollout sequence

1. Have the Human Owner merge PR #84 after its final docs-only CI run is green.
2. On the local WSL checkout, pull current `main`.
3. Query C1 job `eec59b13651c54559c10ce204380a68e`. If it is queued/routing/planning/executing/verifying/evaluating/delivering or otherwise in flight, do **not** restart anything.
4. If C1 is confirmed stable blocked/terminal, configure `OPENROUTER_API_KEY` in `.ddev/.env.coding-runtime.local` without exposing it in chat/logs.
5. Run the required n8n/platform rollout (`ddev n8n-sync`) because #78 changed workflows and #81/#83 require Runtime/Router reload. Remember that this command restarts the stack.
6. Verify post-rollout health before any C1 recovery:
   - Router version `1.0.15`;
   - Router registry version `6`;
   - Router policy version `6`;
   - Runtime version `1.0.29`;
   - Runtime reports OpenCode adapter available.
7. Perform a minimal privacy-safe OpenRouter smoke using the exact configured model; do not use `openrouter/free` and do not weaken ZDR/no-data-collection policy if no endpoint is available.
8. Re-query C1 and trigger an orchestrator tick. Recover C1 only through the official Runtime/Telegram control action that matches the current live exhausted dimension. For the last recorded state this should be `+4 model calls`, but live revalidation is authoritative.
9. Monitor the same C1 job until it repairs the evaluator findings and reaches the normal PR/CI/manual-merge gate. Keep C2/C3 pending until C1 clears that gate.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
