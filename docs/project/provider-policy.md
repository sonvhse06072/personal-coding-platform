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

Do not aggressively retry a pressured free provider. A provider overload such as HTTP/API 502 should move routing toward another eligible free/paid model rather than consume budget on repeated retries.

## 6. Current candidate strategy

Issue #85 is replacing withdrawn Qwen free models before local rollout.

Observed evidence:

- `qwen/qwen3-coder:free`: withdrawn from free access (404);
- `qwen/qwen3.6-plus:free`: deprecated as a free model (404);
- `nvidia/nemotron-3-ultra-550b-a55b:free`: strong Programming usage and 1M context, but current OpenRouter availability is materially lower than the preferred reliable candidate and a live smoke returned upstream NVIDIA overload (502);
- `cohere/north-mini-code:free`: coding/terminal/OpenCode-oriented, 256K context, tool calling support and currently high observed OpenRouter availability.

Current preferred ordering for rollout validation:

1. `cohere/north-mini-code:free` as the reliable primary free coding candidate;
2. `nvidia/nemotron-3-ultra-550b-a55b:free` as a secondary opportunistic model for stronger/long-context work when healthy;
3. existing non-OpenRouter PCP fallbacks remain authoritative after free-tier failures.

This ordering is operational, not permanent. Re-evaluate when model availability/rankings materially change.

## 7. Quota and telemetry

The platform may record observed usage, failures, latency, selected model/provider and local request counts.

It must not present an authoritative "free quota remaining" value unless the upstream exposes a reliable authoritative counter for that exact quota.

The Human Owner has funded at least $10 of OpenRouter credit, which currently raises the documented free-model allowance to 1,000 requests/day with a 20 RPM free-model limit. These are external terms and may change; they are not architecture invariants.

## 8. Rollout rule

OpenRouter free should be introduced incrementally:

1. validate at least one explicit free coding model with a synthetic tool-call smoke;
2. register the explicit model set and bump registry version;
3. run deterministic Router/Runtime/executor/structure tests;
4. obtain green CI and Human Owner manual merge;
5. only at a stable blocked/terminal Runtime gate, roll out locally and verify service/config versions;
6. run one deployed-integration smoke before relying on the tier for normal jobs;
7. review telemetry before broader role/profile eligibility.

Never auto-merge, force-complete work, or restart Runtime/DDEV while a job is in flight.
