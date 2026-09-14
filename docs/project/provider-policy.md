# Provider and Model Resource Policy

Status: approved provider/resource policy. OpenRouter is an opportunistic free-compute provider under PCP Router authority. The Human Owner has explicitly chosen model effectiveness and usable free capacity over ZDR/no-data-collection guarantees for this provider tier.

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

Free resources are useful compute, not guaranteed capacity. Router may prefer an eligible free resource when its capability, observed effectiveness and availability are sufficient for the WorkOrder. Provider failure must not weaken verification, scope, delivery, secret isolation or state-machine rules.

## 3. OpenRouter free-tier policy

OpenRouter is integrated as an **opportunistic model provider**, not as PCP's routing authority and not as a new platform service.

Policy:

- use explicit free model IDs selected by PCP; do **not** use `openrouter/free` for durable coding jobs;
- do **not** supply an OpenRouter cross-model fallback list;
- same-model provider endpoint fallback may be allowed;
- use only profiles explicitly allowed by model metadata;
- first rollout keeps OpenRouter free excluded from `critical` and Product Manager staffing;
- PCP Router remains responsible for selecting a different model after provider/model failure;
- model selection should consider current OpenRouter programming ranking/usage, coding and agent benchmarks, tool support, context, latency and observed availability;
- free model availability is ephemeral, so live availability smoke is required before registering or rolling out a replacement model.

The model registry must make profile eligibility explicit rather than relying only on preferred-order scoring.

## 4. Data handling and secret boundary

For the OpenRouter free tier, ZDR and `data_collection=deny` are **not required routing gates**. The Human Owner accepts that a free upstream provider may log prompts/outputs or use them under its published free-endpoint terms in exchange for better model effectiveness/free capacity.

This relaxation applies to provider data-retention/training policy only. It does **not** relax credential or control-plane boundaries:

- never send API keys, passwords, tokens, private keys, authentication cookies, `.env` secrets or other credentials to an OpenRouter model;
- Runtime/control-plane credentials remain inaccessible to coding-agent subprocesses;
- an OpenRouter OpenCode subprocess receives only the minimum provider credential required for that run;
- OpenCode session sharing remains disabled;
- mounted host configuration must not silently activate unrelated providers;
- prompts should avoid unnecessary personal data and unrelated confidential material even when repository source is permitted.

Provider logging/training terms should be treated as operational metadata and may be recorded for owner awareness, but they do not make an otherwise eligible OpenRouter free model unroutable.

## 5. Failure and recovery semantics

OpenRouter free capacity is opportunistic. Rate limits, daily free allowance exhaustion, endpoint unavailability, model deprecation, or provider errors must use the normal PCP provider/model failure path.

Expected behavior:

```text
selected explicit OpenRouter free model
  -> success: continue normally
  -> provider/rate-limit/quota/deprecation/unavailability failure
       -> record sanitized provider evidence
       -> update durable provider/model state
       -> PCP model/provider failover within existing budgets
       -> block only when no valid fallback remains
```

Do not repeatedly retry a pressured or deprecated free model simply to consume execution budget.

## 6. Quota and telemetry

The platform may record observed usage, failures, latency, selected model/provider, local daily request counts and upstream ranking/availability evidence used during model selection.

It must not present an authoritative "free quota remaining" value unless the upstream provider exposes a reliable authoritative counter for that exact quota.

The Human Owner has funded at least $10 of OpenRouter credit, enabling the provider's higher documented free-model daily allowance. Current limits and commercial terms are external operational facts and may change.

## 7. Effectiveness-first candidate policy

For issue #85, current candidate priority is:

1. `nvidia/nemotron-3-ultra-550b-a55b:free` as the primary effectiveness candidate because it ranks highly in OpenRouter programming usage, supports 1M context and tool calling, and targets long-running agentic/coding work;
2. `cohere/north-mini-code:free` as the availability/coding-harness fallback because it is purpose-built for agentic coding and OpenCode/SWE-Agent with 256K context and tool calling;
3. other active explicit free models may be evaluated if both candidates become unavailable or materially underperform.

A candidate must pass a synthetic **availability + tool-call smoke** before registration. ZDR/no-data-collection success is no longer required.

## 8. Rollout rule

OpenRouter free should be introduced incrementally:

1. select and live-smoke an active explicit model;
2. register the selected model and keep profile eligibility bounded;
3. verify fast/standard executor behavior and bounded complex reviewer/evaluator use;
4. review telemetry and actual coding success before broader eligibility.

Critical work and Product Manager staffing remain excluded until separate evidence and approval justify changing this policy.
