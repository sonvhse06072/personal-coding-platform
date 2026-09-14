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
- Local rollout has now been performed after confirming C1 was stable blocked.
- Live post-rollout evidence: Router `1.0.15`, Runtime `1.0.30`, model registry `v7`, routing policy `v7`, Runtime OpenCode adapter available, DDEV executor healthy with `active_jobs: 0`, n8n healthy, Antigravity bridge healthy with `active_runs: 0`.
- OpenRouter credential boundary was verified live: Runtime sees `OPENROUTER_API_KEY`, while global `.ddev/.env` does not contain it.

## Active work

### 1. Deployed OpenRouter integration validation

Durable provider policy: `docs/project/provider-policy.md`.

- Operational issue: `personal-coding-platform` #87.
- PR #86 is merged and locally activated.
- Active explicit upstream free model: `cohere/north-mini-code:free`.
- Stable logical PCP model ID remains `openrouter_qwen3_coder_free` for durable route-history/provider-state compatibility; the registry `model:` slug is authoritative.
- Human Owner policy: OpenRouter free is effectiveness-first. ZDR and `data_collection=deny` are not required. Repository source code may traverse free endpoints under their published logging/training terms.
- Secret boundaries remain strict: never intentionally send API keys, access tokens, `.env` contents, private keys, passwords, cookies, Runtime/control-plane credentials, or unrelated provider credentials to a model.
- OpenCode session sharing remains disabled; Runtime scopes only `OPENROUTER_API_KEY` to the OpenRouter subprocess.
- North Mini Code pre-rollout evidence: direct OpenRouter synthetic tool-call smoke passed without ZDR/data-collection filters; the same model failed with a ZDR-required policy because no matching endpoint existed.
- Nemotron remains inactive. Runtime provider failures currently mark `provider:openrouter` unavailable, so activating multiple OpenRouter models would not provide reliable same-provider model fallback after a provider-level failure.
- Human Owner funded at least $10 of OpenRouter credit; current documented free allowance is 1,000 requests/day at 20 RPM. Do not expose a fabricated authoritative remaining-quota counter.
- Current gate: run one synthetic deployed smoke through the Runtime OpenCode adapter using North Mini Code in non-mutating plan mode. Do not resume C1 until this passes.

### 2. DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- Live status re-verified on 2026-09-14 before rollout: `blocked`, profile `complex`, executor `codex_terra`, top-level reason `reassessment_stopped`, Runtime error `None`.
- The blocked row was last updated at `2026-09-13T21:03:40.184327+00:00`, confirming it was stable rather than in-flight before restart.
- Evaluator still did **not** accept C1. The same two material findings remain in the live `last_failure` evidence:
  1. deployed release identity must be derived/verified from the deployed tree instead of trusting local Git SHA/fingerprint supplied by `run.sh`;
  2. AC6 needs deterministic passing evidence for the DEC-025C-specific Python/PHP/shell/static checks.
- PR #78 supports bounded recovery for this reassessment class. For the recorded state, the first expected recovery dimension is `+4 model calls`; later extensions are allowed only if they become the current live blocker.
- Do not force-complete C1. Do not create a replacement job. C2/C3 remain gated.
- After the deployed OpenRouter smoke passes, re-query this same job before any recovery action; post-restart live state is authoritative.

### 3. Telegram control rollout

- Issue #77 / PR #78 are merged and their n8n workflows have now been locally synced.
- Owner-facing Telegram messages/actions are localized to Vietnamese; stable machine reason codes remain unchanged.
- `reassessment_stopped + hard_budget_guard` can produce a bounded, live-dimension-revalidated owner action; stale/wrong-dimension actions fail closed.
- n8n is healthy after rollout. No control action has yet been executed for C1 after restart.

## Next safe sequence

1. Run a synthetic non-mutating deployed OpenRouter smoke through the Runtime OpenCode adapter using `openrouter/cohere/north-mini-code:free`.
2. If the smoke passes, re-query C1 job `eec59b13651c54559c10ce204380a68e` and confirm it remains stable blocked/terminal.
3. Trigger one orchestrator tick.
4. Recover C1 only through the official live-revalidated control action. For the last recorded blocker the expected first bounded extension is `+4 model calls`, but live state is authoritative.
5. Monitor the same C1 job until it addresses both evaluator findings and reaches its normal PR/CI/manual-merge gate. Keep C2/C3 pending until C1 clears that gate.
6. Update this document with deployed smoke evidence, post-restart C1 state, any control action executed, and the resulting job state before handoff.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
