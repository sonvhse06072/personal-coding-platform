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
- `main` is verified at merge commit `cd525d8dfd346bfc6293c8c2641f3c95a4a37799` after PR #86.
- Local rollout has been performed after confirming C1 was stable blocked.
- Live post-rollout evidence: Router `1.0.15`, Runtime `1.0.30`, model registry `v7`, routing policy `v7`, Runtime OpenCode adapter available, DDEV executor healthy with `active_jobs: 0` before C1 recovery, n8n healthy, Antigravity bridge healthy with `active_runs: 0`.
- OpenRouter credential boundary was verified live: Runtime sees `OPENROUTER_API_KEY`, while global `.ddev/.env` does not contain it.
- Deployed OpenRouter smoke through the actual Runtime `OpenCodeAdapter` passed using `openrouter/cohere/north-mini-code:free` in non-mutating plan mode. The synthetic success token was observed and the temporary workspace remained unchanged.

## Active work

### 1. OpenRouter rollout status

Durable provider policy: `docs/project/provider-policy.md`.

- Operational issue: `personal-coding-platform` #87.
- PR #86 is merged and locally activated.
- Active explicit upstream free model: `cohere/north-mini-code:free`.
- Stable logical PCP model ID remains `openrouter_qwen3_coder_free` for durable route-history/provider-state compatibility; the registry `model:` slug is authoritative.
- Human Owner policy: OpenRouter free is effectiveness-first. ZDR and `data_collection=deny` are not required. Repository source code may traverse free endpoints under their published logging/training terms.
- Secret boundaries remain strict: never intentionally send API keys, access tokens, `.env` contents, private keys, passwords, cookies, Runtime/control-plane credentials, or unrelated provider credentials to a model.
- OpenCode session sharing remains disabled; Runtime scopes only `OPENROUTER_API_KEY` to the OpenRouter subprocess.
- Direct pre-rollout smoke and deployed Runtime/OpenCode smoke both passed for North Mini Code without ZDR/data-collection filters. North Mini Code has no endpoint matching the old ZDR-required policy.
- Nemotron remains inactive. Runtime provider failures currently mark `provider:openrouter` unavailable, so activating multiple OpenRouter models would not provide reliable same-provider model fallback after a provider-level failure.
- Human Owner funded at least $10 of OpenRouter credit; current documented free allowance is 1,000 requests/day at 20 RPM. Do not expose a fabricated authoritative remaining-quota counter.
- OpenRouter rollout gate is complete. Current work is C1 recovery/verification.

### 2. DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- Before recovery, C1 was stable `blocked`, profile `complex`, executor `codex_terra`, reason `reassessment_stopped`, Runtime error `None`.
- Evaluator findings that C1 still needs to satisfy:
  1. deployed release identity must be derived/verified from the deployed tree instead of trusting local Git SHA/fingerprint supplied by `run.sh`;
  2. AC6 needs deterministic passing evidence for the DEC-025C-specific Python/PHP/shell/static checks.
- Post-rollout orchestrator tick materialized the expected bounded recovery action `l-PuQpbvYEHnlMNp8Fk5IJ5P`: `budget_extend`, `max_model_calls +4`, from live counters model calls `14/14`, tool calls `30/160`, test runs `6/14`, wall time `61.97/70`, repair iterations `2/2`.
- After the owner-authorized recovery, live job state is now **in flight**: `status=verifying`, `updated_at=2026-09-14T13:36:04.813659+00:00`, profile `complex`, executor `codex_terra`, Runtime error `None`.
- While the job is `verifying`, the returned `result.reason=reassessment_stopped` is stale prior-result context and is not a current blocked-state authorization. Do not act on it while status is in flight.
- No additional control action is authorized while C1 is in flight. Do not tick for recovery, restart services, run the generic job-run endpoint, or execute any other pending/stale action.
- Repair iterations were already `2/2` before resume, so `+1 repair iteration` may become the next bounded gate, but only if Runtime blocks again and materializes a fresh live action for that exact dimension. Never pre-authorize it.
- Do not force-complete C1. Do not create a replacement job. Do not mutate the DB. C2/C3 remain gated.

### 3. Telegram control rollout

- Issue #77 / PR #78 are merged and their n8n workflows have been locally synced.
- Owner-facing Telegram messages/actions are localized to Vietnamese; stable machine reason codes remain unchanged.
- `reassessment_stopped + hard_budget_guard` produced the expected bounded, live-dimension-revalidated C1 recovery action after rollout.
- n8n is healthy after rollout. Recovery has resumed the same C1 job; no further owner action is valid while it remains in flight.

## Next safe sequence

1. Monitor only the same C1 job `eec59b13651c54559c10ce204380a68e` while status is in-flight (`verifying`, `evaluating`, `delivering`, or equivalent). Do not restart or execute control actions.
2. If C1 reaches `delivering`/PR creation, follow the normal CI/manual-merge gate.
3. If C1 becomes `blocked` again, inspect the new live `reason`, counters, reassessment evidence and freshly materialized pending control action. Extend only the dimension Runtime authorizes for that new state.
4. If the next blocker is repair iterations, approve only a fresh `max_repair_iterations +1` action; do not reuse old actions.
5. C1 must fix both evaluator findings and reach the normal PR/CI/manual-merge gate before C2/C3 proceed.
6. Update this document with the next stable state, PR/CI gate, or newly authorized blocker before handoff.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
