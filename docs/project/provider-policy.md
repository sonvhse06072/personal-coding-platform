# Provider and Model Resource Policy

Status: approved provider/resource policy. The OpenRouter-specific behavior below is an approved implementation target for issue #79 until the corresponding code is merged to `main`.

## 1. Authority boundary

The Personal Coding Platform Router remains authoritative for:

- logical role staffing;
- model selection;
- cross-model failover;
- profile/risk eligibility;
- privacy eligibility;
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

Free resources are useful compute, not guaranteed capacity. Router may prefer an eligible free resource when its capability and reliability are sufficient for the WorkOrder, but provider failure must not weaken privacy, verification, scope, or delivery rules.

## 3. OpenRouter free-tier policy

OpenRouter is integrated as an **opportunistic model provider**, not as PCP's routing authority and not as a new platform service.

Initial policy for issue #79:

- use a specific free model ID, initially `qwen/qwen3-coder:free` through OpenCode;
- do **not** use `openrouter/free` for durable coding jobs;
- do **not** supply an OpenRouter cross-model fallback list;
- same-model provider endpoint fallback may be allowed;
- use only for profiles explicitly allowed by model metadata;
- first rollout allows `fast`, `standard`, and bounded `complex` use, but not `critical`;
- first rollout does not allow OpenRouter free for Product Manager staffing;
- PCP Router remains responsible for selecting a different model after provider/model failure.

The model registry must make profile eligibility explicit rather than relying only on preferred-order scoring.

## 4. Private-code and data policy

Private repository code must fail closed.

For OpenRouter-backed private-code calls, Runtime/OpenCode must enforce the equivalent of:

```json
{
  "provider": {
    "data_collection": "deny",
    "zdr": true,
    "require_parameters": true,
    "allow_fallbacks": true
  }
}
```

`allow_fallbacks` applies only to provider endpoints capable of serving the exact model PCP selected. It must not authorize OpenRouter to choose another model.

If no eligible endpoint satisfies the required privacy policy, the provider call must fail and PCP must use its normal provider/model failover path. The platform must never relax privacy requirements merely to consume free capacity.

OpenCode sharing must be disabled for OpenRouter runs. The inline OpenCode configuration must also allowlist only the `openrouter` provider (or use the current OpenCode equivalent), so mounted user configuration cannot silently activate another provider for that run. Developer-agent subprocesses receive only `OPENROUTER_API_KEY` when that provider is selected; they must not inherit unrelated provider keys or Runtime/control-plane credentials.

## 5. Failure and recovery semantics

OpenRouter free capacity is opportunistic. Rate limits, daily free allowance exhaustion, endpoint unavailability, or lack of a privacy-eligible endpoint are provider failures, not reasons to expand WorkOrder scope or bypass governance.

Expected behavior:

```text
selected OpenRouter free model
  -> success: continue normally
  -> provider/rate-limit/quota/privacy-endpoint failure
       -> record sanitized provider evidence
       -> update durable provider/model state
       -> PCP provider/model failover within existing budgets
       -> block only when no valid fallback remains
```

Do not repeatedly retry a pressured free provider simply to consume remaining execution budget.

## 6. Quota and telemetry

The platform may record observed usage, failures, latency, selected model/provider, and daily local request counts.

It must not present an authoritative "free quota remaining" value unless the upstream provider exposes a reliable authoritative counter for that exact quota.

Current OpenRouter free-tier limits and commercial terms are external facts that may change. They are configuration/operational inputs, not architecture invariants. The platform should therefore keep local safety margins and rely on provider-state/failure evidence rather than hard-code an assumed remaining quota into user-facing state.

## 7. Rollout rule

OpenRouter free should be introduced incrementally:

1. explicit model registration and privacy-safe OpenCode configuration;
2. fast/standard routing eligibility;
3. bounded complex reviewer/evaluator use where independent-provider diversity is useful;
4. telemetry review before broader role/profile eligibility.

Critical work and Product Manager staffing remain excluded until separate evidence and approval justify changing this policy.
