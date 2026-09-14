# Current Project State and Handoff

Status: mutable continuity document. Update this file whenever a material decision, implementation state, blocker, rollout decision, or handoff changes. This file is intentionally operational and may change frequently; durable architecture/product/policy decisions belong in the relevant topical source-of-truth document.

Last updated: 2026-09-14

## How to resume in a new chat or agent session

Read, in order:

1. repository-root `AGENTS.md`;
2. `docs/project/README.md`;
3. this file;
4. every topical project document referenced by the active work below;
5. the active GitHub issue/PR and the current branch diff before editing.

Do not rely on chat history as project state. If chat memory and repository docs disagree, repository docs and current executable evidence win according to the authority order in `AGENTS.md`.

## Mandatory continuity rule

Before a material task is considered complete or handed off, the responsible ChatGPT/Codex/platform agent must update repository documentation so another session can continue safely without the previous conversation.

Record durable decisions in their topical document, for example:

- architecture/trust-boundary decisions -> `architecture.md`;
- team/process responsibilities -> `operating-model.md`;
- provider/model resource policy -> `provider-policy.md` when present;
- roadmap/order changes -> `roadmap.md`;
- project authority/invariants -> `constitution.md` when appropriate.

Record mutable execution state in this file, including when relevant:

- active issue, branch, PR, WorkOrder, Runtime job and plan IDs;
- current status and last meaningful evidence;
- work already completed;
- unresolved blockers and why they are blockers;
- verification/CI evidence already obtained;
- exact next safe action;
- merge/restart/deploy gates;
- any owner action still required.

Handoff prompts to Codex/platform agents must explicitly require these documentation updates as part of completion.

## Active work

### DEC-025C / `chonhac` recovery tooling

- GitHub ticket: `chonhac` issue GH-5.
- Orchestration plan: `pm-gh-5650852312`.
- WorkOrder: `DEC-025C-1-recovery-tooling-r2`.
- Runtime job: `eec59b13651c54559c10ce204380a68e`.
- Last known Runtime status: `blocked` in `reassessment` with top-level reason `reassessment_stopped`.
- Reassessment evidence: nested reason `model-call budget exhausted`, signal `hard_budget_guard`.
- Evaluator did **not** accept C1. Two material findings remain:
  1. deployed release identity must be derived/verified from the deployed tree instead of trusting local Git SHA/fingerprint supplied by `run.sh`;
  2. AC6 needs deterministic passing evidence for the DEC-025C-specific Python/PHP/shell/static checks rather than relying on unrelated repository test commands.
- Downstream C2/C3 remain gated until C1 satisfies its PR/CI/manual-merge gate.
- Do not force-complete C1 and do not create a replacement job merely to bypass recovery state.

### Telegram recovery/control UX

- Issue: `personal-coding-platform` #77.
- PR: #78, `Handle reassessment budget guards and Vietnamese Telegram UX`.
- Last known state: Ready for review, CI green, manual merge still required unless GitHub evidence later shows otherwise.
- Purpose: classify `reassessment_stopped + hard_budget_guard` as bounded budget recovery, retain live-dimension revalidation/fail-closed behavior, and Vietnamese-localize Telegram user-facing notifications/actions.
- After merge/rollout, C1 should be recovered only through the official bounded control-action path; no force-complete action is authorized.

### OpenRouter opportunistic free provider

- Issue: `personal-coding-platform` #79.
- Branch: `feat/openrouter-free-79`.
- Goal: use OpenRouter free capacity as an opportunistic provider without replacing PCP Router authority.
- Initial exact model target: `qwen/qwen3-coder:free` via OpenCode/OpenRouter; `openrouter/free` is forbidden for durable coding jobs.
- PCP owns logical model selection, cross-model failover, budgets and durable provider state. OpenRouter may only perform endpoint fallback for the same already-selected model.
- Private-code calls must fail closed with no-data-collection + ZDR requirements; privacy must never be weakened to consume free quota.
- Initial eligibility target: fast/standard executor and bounded complex evaluator/reviewer use; exclude critical profile and Product Manager staffing.
- Partial implementation exists on the branch. A remaining known Router gap is to enforce explicit profile eligibility rather than relying on `preferred_ids` scoring bonuses.
- Codex implementation handoff was blocked locally because the WSL checkout could not authenticate/fetch the private branch. The remote branch and `docs/project/provider-policy.md` were verified to exist. Resolve host Git authentication/fetch first, then continue on the existing branch rather than recreating it.

### Cross-chat documentation continuity

- Issue: `personal-coding-platform` #80.
- Branch: `docs/cross-chat-continuity-80`.
- Goal: make repository documentation the mandatory continuity source across ChatGPT, Codex and platform-run work.
- This file is part of that change and must remain mutable after merge.

## Global operational gates

- Never commit directly to `main`; use issue -> branch -> tests/CI -> PR -> human merge.
- Never force push, auto-merge, or production deploy.
- Do not restart Runtime/DDEV while a job is queued/routing/planning/executing/verifying/evaluating/delivering or otherwise in-flight. Restart only at a stable blocked/terminal gate.
- Runtime durable state is authoritative; do not mutate job/database state manually to bypass state-machine logic.
- Provider/control-plane credentials must remain service-scoped and must never be committed to repository docs.

## Updating this file

Keep this file compact. Replace stale state instead of appending an unbounded chronological log. Git history is the audit trail.

When an active item is merged/completed, update or remove it and record any new rollout/verification state that a future session still needs. If a decision becomes a durable policy, move the authoritative statement into the appropriate topical document and leave only a short pointer here.