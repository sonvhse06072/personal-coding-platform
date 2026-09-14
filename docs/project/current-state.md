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
- Current `main` rollout markers before issue #85: Router `1.0.15`, Runtime `1.0.29`, model registry `v6`, routing policy `v6`.
- Merged code is not locally activated merely because it is on `main`; Runtime/Router/n8n health evidence must be checked after a safe rollout.

## Active work

### 1. OpenRouter free-model replacement before rollout

Durable policy: `docs/project/provider-policy.md`.

- Issue: `personal-coding-platform` #85.
- Branch: `fix/openrouter-free-model-85`.
- Do **not** run `ddev n8n-sync` or restart the local platform until #85 is merged and C1 is re-confirmed stable blocked/terminal.
- Human Owner decision: OpenRouter free is effectiveness-first. ZDR and `data_collection=deny` are not required. Repository source code may traverse free endpoints under their published logging/training terms. Secret boundaries and disabled OpenCode sharing remain mandatory.
- Live evidence:
  - `qwen/qwen3-coder:free` -> 404, unavailable for free;
  - `qwen/qwen3.6-plus:free` -> 404, free model deprecated;
  - `nvidia/nemotron-3-ultra-550b-a55b:free` -> valid model, but synthetic tool-call smoke returned NVIDIA 502 `provider_unavailable` / temporarily overloaded;
  - `cohere/north-mini-code:free` -> synthetic tool-call smoke passed without ZDR/data-collection filters and returned one `pcp_probe` tool call;
  - North Mini Code with `zdr=true` + `data_collection=deny` -> 404 `No endpoints found matching your data policy (Zero data retention)`.
- Implementation decision for #85:
  - use `cohere/north-mini-code:free` as the **single active explicit OpenRouter free model** for initial rollout;
  - preserve logical model ID `openrouter_qwen3_coder_free` as a stable legacy durable identity so existing route history/provider-state evidence remains comparable; the registry `model:` slug is authoritative;
  - do not activate Nemotron in the same pool yet because Runtime provider failures mark `provider:openrouter` unavailable, so one provider-level failure would exclude every OpenRouter model and defeat same-provider model fallback;
  - remove mandatory ZDR/data-collection filters from Runtime OpenCode request policy, but keep exact-model/provider allowlists, `require_parameters`, same-model endpoint fallback, service-scoped `OPENROUTER_API_KEY`, and `share=disabled`.
- Intended #85 version markers: Router remains `1.0.15`; Runtime `1.0.30`; model registry `v7`; routing policy `v7`.
- Critical profile and Product Manager exclusions remain unchanged.
- The Human Owner funded at least $10 OpenRouter credit; current documented free allowance is 1,000 requests/day at 20 RPM. Do not expose a fabricated authoritative remaining-quota counter.
- Current gate: finish focused tests/docs, green full CI, Human Owner manual merge; no local restart before that.

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
- Local activation is pending.
- `ddev n8n-sync` restarts the DDEV stack; it must run only after C1 is confirmed stable blocked/terminal and #85 is merged.

## Next safe sequence

1. Finish issue #85 on `fix/openrouter-free-model-85`: North Mini Code upstream model, effectiveness-first OpenCode request policy, Runtime `1.0.30`, registry/policy `v7`, focused tests/docs.
2. Run full CI and obtain Human Owner manual merge; do not restart local services yet.
3. Pull merged `main` locally and re-query C1.
4. Only if C1 is stable blocked/terminal, configure `OPENROUTER_API_KEY` in `.ddev/.env.coding-runtime.local` and run the required platform/n8n rollout.
5. Verify Router `1.0.15`, Runtime `1.0.30`, registry `v7`, routing policy `v7`, plus OpenCode availability.
6. Run one minimal deployed integration smoke through PCP using North Mini Code; no secrets/private credentials in the prompt.
7. Trigger orchestrator tick and recover C1 only through the official live-revalidated control action; expected first bounded extension for the recorded blocker is `+4 model calls`.
8. C1 must address both evaluator findings and reach its normal PR/CI/manual-merge gate before C2/C3 proceed.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is in flight.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials remain service-scoped and must never be committed to repository docs or intentionally sent to model prompts.

## Updating this file

Keep this file compact. Replace stale state rather than appending raw conversation history. Git history is the audit trail. When an active item is merged/completed, replace it with the rollout/verification state a future session still needs.
