# Provider and Model Resource Policy

Status: approved provider/resource policy. OpenRouter free is an effectiveness-first opportunistic tier. Antigravity is an explicit multi-model resource pool with quota-group-aware routing. Model availability, quota terms and ranking are external operational inputs and must be revalidated before rollout.

## 1. Authority boundary

The Personal Coding Platform Router remains authoritative for:

- logical role staffing;
- model selection;
- cross-model failover;
- profile/risk eligibility;
- durable provider/model/quota-group health state;
- execution budgets and recovery.

An upstream model gateway or provider may select an endpoint for the **same already-selected model**, but it must not silently broaden the model choice behind PCP Router.

Provider integrations must not replace Runtime durability, Router policy, WorkOrder constraints, or Human Owner decision boundaries.

## 2. Resource tiers

Provider/model resources may be classified by cost and reliability, including:

- free / opportunistic;
- subscription-backed;
- ultra-low-cost API;
- paid/premium;
- scarce/frontier.

Free resources are useful compute, not guaranteed capacity. Router may prefer an eligible free resource when its capability and reliability are sufficient for the WorkOrder. Selection should optimize successful completion per unit of cost/time rather than leaderboard position alone.

## 3. OpenRouter free-tier policy

OpenRouter is integrated as an **opportunistic model provider**, not as PCP's routing authority and not as a new platform service.

Rules:

- use explicit free model IDs; do **not** use `openrouter/free` for durable coding jobs;
- do **not** supply an OpenRouter cross-model fallback list;
- same-model provider endpoint fallback may be allowed;
- PCP Router selects a different model after provider/model failure;
- use only profiles explicitly allowed by model metadata;
- critical work and Product Manager staffing remain excluded until separately approved;
- evaluate candidates using current coding/programming usage, tool support, context, observed availability and live functional evidence.

The model registry must make profile eligibility explicit rather than relying only on preferred-order scoring.

## 4. Source-code and secret handling policy

Human Owner decision on 2026-09-14: OpenRouter free selection is **effectiveness-first**. ZDR and `data_collection=deny` are not required eligibility or smoke-test gates for this provider tier. Repository source code may be sent to a free endpoint even when its published terms permit provider logging or model/product improvement use. This is an explicit privacy tradeoff accepted by the Human Owner.

Runtime therefore must not inject ZDR or `data_collection=deny` as mandatory OpenRouter routing filters for this tier. It may still require request-parameter support and same-model endpoint fallback while keeping PCP authoritative for any cross-model change.

Secret boundaries remain strict. Developer-agent prompts or context must never intentionally include:

- API keys or access tokens;
- `.env` contents or secret configuration values;
- private keys, passwords, cookies or session credentials;
- Runtime/control-plane credentials;
- unrelated provider credentials.

OpenCode session sharing remains disabled. Provider credentials remain service-scoped, and an OpenRouter subprocess receives only the credential required for that provider.

## 5. Failure and recovery semantics

OpenRouter free capacity is opportunistic. Rate limits, daily allowance exhaustion, provider overload, endpoint unavailability or model withdrawal are provider failures, not reasons to bypass governance.

Expected behavior:

```text
selected explicit OpenRouter free model
  -> success: continue normally
  -> provider/rate-limit/quota/unavailable failure
       -> record sanitized provider evidence
       -> update durable provider/model state
       -> PCP selects the next eligible explicit model within existing budgets
       -> block only when no valid fallback remains
```

Do not aggressively retry a pressured free provider. A provider overload such as HTTP/API 502 should move routing toward another eligible provider/model rather than consume budget on repeated retries.

Provider recovery is autonomous while eligible capacity remains. The per-profile `max_provider_failovers` value is a planning/telemetry prior, not a Human Owner continuation gate: Runtime may exceed it when each observed failure is durably excluded and Router returns a distinct eligible candidate. Quota, rate-limit, authentication, configuration or availability failure of one provider/model must therefore fall through to another valid route for the same job/workspace/counters. Human Owner attention is appropriate only when no eligible route remains, contradictory/oscillating provider evidence is detected, or another protected/anomaly/material-resource boundary independently requires a stop.

Failed provider/model/quota health must remain durable across those automatic reroutes. Runtime must not clear failed-capacity state merely to stay under a failover counter; this preserves a finite recovery sequence and prevents cycling back to capacity already proven unusable.

OpenRouter authentication, configuration and true provider-unavailable failures remain provider-wide. Quota/rate-limit failures use the registered `openrouter_free` quota group. Multiple free OpenRouter models in that same group therefore still do **not** provide an independent quota fallback: exhaustion of the shared free pool excludes them together. Do not register a multi-model OpenRouter pool as independent capacity until its quota/provider semantics are intentionally redesigned and tested.

## 6. Current OpenRouter model strategy

Issue #85 replaces withdrawn Qwen free models before local rollout.

Observed live evidence:

- `qwen/qwen3-coder:free`: withdrawn from free access (404);
- `qwen/qwen3.6-plus:free`: deprecated as a free model (404);
- `nvidia/nemotron-3-ultra-550b-a55b:free`: valid free model, but synthetic tool-call smoke returned upstream NVIDIA overload (502 `provider_unavailable`);
- `cohere/north-mini-code:free`: synthetic tool-call smoke succeeded with the expected tool call when no ZDR/data-collection filter was imposed;
- the same North Mini Code smoke with `zdr=true` + `data_collection=deny` failed with 404 `No endpoints found matching your data policy (Zero data retention)`.

Rollout choice:

1. activate `cohere/north-mini-code:free` as the single explicit OpenRouter free model for the initial rollout;
2. retain the existing logical PCP model ID `openrouter_qwen3_coder_free` as a **stable legacy durable identity** so existing route history/provider-state evidence remains comparable; the `model:` field is the authoritative upstream model slug;
3. keep Nemotron documented but **not active** until a separate change introduces safe model-level health/failover semantics for multiple models under one OpenRouter provider;
4. existing non-OpenRouter PCP fallbacks remain authoritative after an OpenRouter provider failure.

This choice is operational, not permanent. Re-evaluate when model availability/rankings materially change.

## 7. Antigravity model, effort and quota policy

Antigravity is a multi-model provider. PCP must pin an explicit headless model slug rather than delegate durable model selection to Antigravity `auto` mode.

The active initial pool is:

- `antigravity_free` -> `gemini-3.8-flash-medium`, retained as the stable legacy PCP identity and preferred for general low-cost execution;
- `antigravity_flash_high` -> `gemini-3.8-flash-high`, a stronger Flash option for reasoning-heavy execution without spending the stronger Pro/Sonnet pools first;
- `antigravity_gemini_pro` -> `gemini-3.1-pro-high`, preferred for planning, debugging and high-reasoning work;
- `antigravity_claude_sonnet` -> `claude-sonnet-4-6`, preferred for independent review/evaluation and strong fallback reasoning.

The Router may attach `low`, `medium` or `high` reasoning effort to an Antigravity choice. Runtime must pass that exact effort to the headless bridge. A bounded reasoning escalation may increase effort on the same selected model before consuming a different model tier when policy allows it.

Antigravity health is tracked at three distinct levels:

```text
model:<logical model id>        model-specific deterministic/no-effect health
quota:<quota group>             shared Antigravity quota/rate-limit health
provider:google_antigravity     bridge/auth/provider-wide health
```

The initial quota groups follow the externally visible Antigravity resource families:

- `antigravity_gemini` for Gemini Flash/Pro models;
- `antigravity_claude_gpt` for Claude/GPT-family models.

A `quota_exhausted` or `rate_limited` result from an Antigravity model marks only its quota group unavailable. It must **not** mark all of `google_antigravity` unavailable. Authentication, bridge or true provider-wide failures remain provider-scoped. This lets PCP move from an exhausted Gemini pool to the Claude/GPT pool before leaving Antigravity entirely, while avoiding repeated calls into models sharing a quota bucket that is already known exhausted.

For compatibility, preserved pre-fix provider-wide quota markers may be narrowed only when durable failure evidence proves the latest failure for that provider was quota/rate-limit exhaustion. Antigravity direct model failures remain model-scoped; Codex ChatGPT subscription failures use the registered shared `codex_chatgpt_plus` quota group. Authentication, configuration, bridge and true provider-wide failures are never narrowed automatically.

Antigravity plan terms currently include weekly limits, while eligible paid plans may also refresh usable quota on a shorter window until the weekly limit is reached. PCP treats these windows as external operational state. It does not invent recovery from a reset timestamp. When a fresh authoritative provider observation made **after** a durable quota/rate-limit failure reports that the exact quota key is available again, Runtime may rehabilitate only that quota key and autonomously retry the same blocked job. Stale observations, elapsed time alone, auth/config failures and provider-wide failures never qualify.

The Antigravity interactive `/usage`/`/quota` UI and statusline may expose richer quota information, but PCP does not scrape or mutate host Antigravity settings merely to infer remaining quota. A future dedicated telemetry integration may ingest an officially supported machine-readable quota signal if one becomes operationally reliable.

## 8. Quota and telemetry

The platform may record observed usage, failures, latency, selected model/provider/quota group and local request counts.

It must not present an authoritative "quota remaining" value unless the upstream exposes a reliable authoritative counter for that exact quota bucket.

The Human Owner has funded at least $10 of OpenRouter credit, which currently raises the documented free-model allowance to 1,000 requests/day with a 20 RPM free-model limit. These are external terms and may change; they are not architecture invariants.

For Antigravity and Codex, provider/model availability and quota reset cadence are external terms. Durable PCP state records observed exhaustion; authoritative post-failure quota observations may record bounded automatic rehabilitation. Speculative remaining percentages or reset-time inference are never sufficient recovery evidence.

## 9. Rollout rule

Provider/model changes should be introduced incrementally:

1. validate explicit model IDs/slugs against current provider documentation or live model discovery;
2. register explicit models and bump registry/routing-policy versions;
3. bump Router/Runtime versions when routing or failure semantics change;
4. run deterministic Router/Runtime/executor/structure tests;
5. obtain green CI and the review/merge required by current governance;
6. only at a stable blocked/terminal Runtime gate, roll out locally and verify service/config versions;
7. run deployed integration checks before relying on a newly activated provider/model tier for normal jobs;
8. review telemetry before broader role/profile eligibility.

Never force-complete work or restart Runtime/DDEV while a job is in flight.
