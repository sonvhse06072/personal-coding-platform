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
- `main` is verified at merge commit `326ea1c5afb40ce144bf95d2421ad5091eb8391d` after PR #84.
- Intended post-rollout version evidence is Router `1.0.15`, Runtime `1.0.29`, model registry `v6`, routing policy `v6`.
- Merged code is not locally activated merely because it is on `main`; Runtime/Router/n8n health evidence must be checked after a safe rollout.

## Active work

### 1. OpenRouter free-model replacement before rollout

Durable policy: `docs/project/provider-policy.md`.

- Issue: `personal-coding-platform` #85.
- Branch: `fix/openrouter-free-model-85`.
- The original configured free model `openrouter/qwen/qwen3-coder:free` is no longer usable: a live synthetic privacy-safe OpenRouter request returned HTTP/API 404 with `This model is unavailable for free` and suggested the paid slug `qwen/qwen3-coder`.
- Therefore the local platform must **not** be restarted/rolled out with the current OpenRouter model configuration.
- The Human Owner has added at least $10 OpenRouter credit, which raises the documented account free-model allowance to 1,000 requests/day while free-model rate limiting remains 20 RPM; this is an external operational limit, not an authoritative remaining-quota counter.
- Preferred first replacement candidate: `qwen/qwen3.6-plus:free`. OpenRouter currently lists it as free, 1M context, agentic/repository coding capable, and tool-calling capable.
- Candidate approval requires a successful synthetic request with `provider.zdr=true`, `data_collection=deny`, `require_parameters=true`, and no cross-model fallback.
- If Qwen3.6 Plus has no eligible privacy-safe free endpoint, next candidate is `openai/gpt-oss-120b:free`, subject to the same live privacy smoke and capability review.
- Do not use NVIDIA Nemotron 3 Ultra free for private code: OpenRouter's current free-endpoint notice says sessions are logged/used to improve NVIDIA products, which conflicts with this project's fail-closed private-code policy.
- Only after a replacement passes live smoke should issue #85 change `config/models.yml`, bump the model registry version, update focused tests and update `provider-policy.md`.

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
- Before any restart or recovery action, query local Runtime again; the status above is last known evidence only.

### 3. Telegram control rollout

- Issue #77 / PR #78 are merged.
- Owner-facing Telegram messages/actions are localized to Vietnamese; stable machine reason codes remain unchanged.
- `reassessment_stopped + hard_budget_guard` can produce a bounded, live-dimension-revalidated owner action; stale/wrong-dimension actions fail closed.
- Local activation is pending.
- `ddev n8n-sync` restarts the DDEV stack; it must run only after C1 is confirmed stable blocked/terminal and after issue #85 produces a valid OpenRouter model configuration.

## Next safe sequence

1. Keep the local DDEV stack unchanged; do not run `ddev n8n-sync` yet.
2. Live-smoke `qwen/qwen3.6-plus:free` using only synthetic text and the exact privacy controls required by `provider-policy.md`.
3. If it passes, complete issue #85 with the smallest model-registry/test/docs patch and obtain green CI + Human Owner merge.
4. If it fails due to no privacy-eligible endpoint/unavailability, smoke the next approved candidate instead; never relax ZDR/no-data-collection requirements.
5. After the replacement PR is merged, pull `main` locally and re-query C1.
6. Only if C1 is stable blocked/terminal, configure `OPENROUTER_API_KEY` in `.ddev/.env.coding-runtime.local` and run the required platform/n8n rollout.
7. Verify Router/Runtime/config versions and OpenCode availability before any C1 recovery.
8. Re-run a minimal OpenRouter smoke through the deployed integration, then trigger orchestrator tick and recover C1 only through the official live-revalidated control action.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
