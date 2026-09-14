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
- Intended rollout markers on current `main`: Router `1.0.15`, Runtime `1.0.30`, model registry `v7`, routing policy `v7`.
- Merged code is not locally activated merely because it is on `main`; Runtime/Router/n8n health evidence must be checked after a safe rollout.

## Active work

### 1. Local rollout of merged OpenRouter support

Durable provider policy: `docs/project/provider-policy.md`.

- Operational issue: `personal-coding-platform` #87.
- PR #86 is merged. No further OpenRouter code change is required before local rollout.
- Active explicit upstream free model: `cohere/north-mini-code:free`.
- Stable logical PCP model ID remains `openrouter_qwen3_coder_free` for durable route-history/provider-state compatibility; the registry `model:` slug is authoritative.
- Human Owner policy: OpenRouter free is effectiveness-first. ZDR and `data_collection=deny` are not required. Repository source code may traverse free endpoints under their published logging/training terms.
- Secret boundaries remain strict: never intentionally send API keys, access tokens, `.env` contents, private keys, passwords, cookies, Runtime/control-plane credentials, or unrelated provider credentials to a model.
- OpenCode session sharing remains disabled; Runtime scopes only `OPENROUTER_API_KEY` to the OpenRouter subprocess.
- North Mini Code live evidence before merge: tool-call smoke passed without ZDR/data-collection filters; the same model failed with a ZDR-required policy because no matching endpoint existed.
- Nemotron remains inactive. Runtime provider failures currently mark `provider:openrouter` unavailable, so activating multiple OpenRouter models would not provide reliable same-provider model fallback after a provider-level failure.
- Human Owner funded at least $10 of OpenRouter credit; current documented free allowance is 1,000 requests/day at 20 RPM. Do not expose a fabricated authoritative remaining-quota counter.
- Current gate: pull merged `main`, re-query C1, and restart/sync only if C1 is stable blocked/terminal.

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
- PR #78 supports bounded recovery for this reassessment class. For the recorded state, the first expected recovery dimension is `+4 model calls`; later extensions are allowed only if they become the current live blocker.
- Do not force-complete C1. Do not create a replacement job. C2/C3 remain gated.
- Before any restart or recovery action, query local Runtime again; this status is last known evidence only.

### 3. Telegram control rollout

- Issue #77 / PR #78 are merged.
- Owner-facing Telegram messages/actions are localized to Vietnamese; stable machine reason codes remain unchanged.
- `reassessment_stopped + hard_budget_guard` can produce a bounded, live-dimension-revalidated owner action; stale/wrong-dimension actions fail closed.
- Local activation is still pending.
- `ddev n8n-sync` restarts the DDEV stack and must run only after C1 is confirmed stable blocked/terminal.

## Next safe sequence

1. Pull current `main` locally and verify HEAD `cd525d8dfd346bfc6293c8c2641f3c95a4a37799`.
2. Re-query C1 job `eec59b13651c54559c10ce204380a68e` before any restart.
3. If C1 is in flight (`queued`, `routing`, `planning`, `executing`, `verifying`, `evaluating`, `delivering`, or equivalent), do **not** restart or sync anything.
4. If C1 is stable blocked/terminal, configure `OPENROUTER_API_KEY` only in `.ddev/.env.coding-runtime.local` without printing or committing it.
5. Run the required platform/n8n rollout (`ddev n8n-sync`).
6. Verify Router `1.0.15`, Runtime `1.0.30`, model registry `v7`, routing policy `v7`, and Runtime OpenCode availability.
7. Run one minimal deployed integration smoke through PCP using North Mini Code; use synthetic content only and do not include secrets.
8. Re-query C1 and trigger an orchestrator tick.
9. Recover C1 only through the official live-revalidated control action. For the last recorded blocker the expected first bounded extension is `+4 model calls`, but live state is authoritative.
10. Monitor the same C1 job until it addresses both evaluator findings and reaches its normal PR/CI/manual-merge gate. Keep C2/C3 pending until C1 clears that gate.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
