# Provider and Model Resource Policy

Status: approved provider/resource policy. OpenRouter free is an effectiveness-first opportunistic tier. Model availability and ranking are external operational inputs and must be revalidated before rollout.

## 1. Authority boundary

The Personal Coding Platform Router remains authoritative for:

- logical role staffing;
- model selection;
- cross-model failover;
- profile/risk eligibility;
- durable provider/model health state;
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

Current Runtime provider-failure semantics mark `provider:openrouter` unavailable for provider failures. Therefore multiple active OpenRouter models do **not** currently provide an effective same-provider PCP fallback: one provider-level failure would exclude all of them. Do not register a multi-model OpenRouter pool until provider/model health semantics are intentionally redesigned and tested.

## 6. Current active model strategy

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

## 7. Quota and telemetry

The platform may record observed usage, failures, latency, selected model/provider and local request counts.

It must not present an authoritative "free quota remaining" value unless the upstream exposes a reliable authoritative counter for that exact quota.

The Human Owner has funded at least $10 of OpenRouter credit, which currently raises the documented free-model allowance to 1,000 requests/day with a 20 RPM free-model limit. These are external terms and may change; they are not architecture invariants.

## 8. Rollout rule

OpenRouter free should be introduced incrementally:

1. validate one explicit free coding model with a synthetic tool-call smoke under the intended request policy;
2. register the explicit model and bump registry/routing-policy versions;
3. bump Runtime when request-policy behavior changes;
4. run deterministic Router/Runtime/executor/structure tests;
5. obtain green CI and Human Owner manual merge;
6. only at a stable blocked/terminal Runtime gate, roll out locally and verify service/config versions;
7. run one deployed-integration smoke before relying on the tier for normal jobs;
8. review telemetry before broader role/profile eligibility.

Never auto-merge, force-complete work, or restart Runtime/DDEV while a job is in flight.
