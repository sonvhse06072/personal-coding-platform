# Provider and Model Resource Policy

Status: approved provider/resource policy. OpenRouter free is an effectiveness-first opportunistic tier. Antigravity is an explicit multi-model resource pool with model/group/provider-aware health. Upstream quota telemetry is authoritative only when obtained from a supported provider signal and fresh enough for routing. Model availability, quota terms and ranking remain external operational inputs and must be revalidated before rollout.

## 1. Authority boundary

The Personal Coding Platform Router remains authoritative for:

- logical role staffing;
- model selection;
- cross-model failover;
- profile/risk eligibility;
- durable provider/model/quota health state;
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

Quota collection must use already-authenticated provider tooling through constrained Runtime/bridge interfaces. It must not parse provider OAuth credentials, expose account secrets, or hand provider credentials to coding agents merely to read usage.

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

Current Runtime provider-failure semantics intentionally remain provider-wide for OpenRouter. Therefore multiple active OpenRouter models do **not** currently provide an effective same-provider PCP fallback: one provider-level failure would exclude all of them. Do not register a multi-model OpenRouter pool until its health semantics are intentionally redesigned and tested.

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

Antigravity resource state has four deliberately separate scopes:

```text
model:<logical model id>          deterministic/no-effect model health
quota:model:<logical model id>    observed quota/rate-limit failure for one model
quota:<quota group>               authoritative evidence for a shared quota family
provider:google_antigravity       bridge/auth/provider-wide health
```

The registry currently associates Gemini models with `antigravity_gemini` and Claude/GPT-family models with `antigravity_claude_gpt`, but a failure from one selected model is **not** sufficient evidence that its whole family is exhausted. Runtime therefore records a concrete `quota_exhausted` or `rate_limited` failure at `quota:model:<id>`. A shared `quota:<group>` marker may be produced only from an authoritative upstream quota signal that actually identifies the shared bucket. Authentication, bridge and provider-wide failures remain provider-scoped.

For compatibility, a preserved same-job reroute may narrow a legacy `provider:google_antigravity` marker to the exact historical model only when durable failure evidence proves the old marker came from quota/rate-limit exhaustion. Other provider-wide failures are not narrowed.

## 8. Authoritative proactive quota telemetry

PCP should know provider capacity **before** a model call whenever a supported upstream signal makes that possible. Runtime maintains provider quota telemetry as platform-wide durable resource state rather than job-owned progress.

Current authoritative collection paths are:

- **Codex:** the installed authenticated `codex app-server` protocol, initialized normally and queried with `account/rateLimits/read`. Primary/secondary windows may provide `usedPercent`, window duration and `resetsAt`. `ordinaryUsageAllowed` is a separate backend permission signal; when it is `null`, PCP must not infer recovery solely from a low percentage or future reset time.
- **Antigravity:** the constrained authenticated host bridge invokes the official read-only print command `agy -p "/usage" --output-format json`. It is serialized with normal Antigravity CLI access and returns only bounded sanitized quota metadata. Structured model/bucket values such as remaining fraction and reset time are normalized without reading provider credentials directly.

Telemetry rules:

1. poll best-effort at approximately five-minute cadence and persist the latest successful provider snapshot;
2. treat snapshots as stale after the configured freshness horizon; stale data is visible for diagnosis but must not change routing availability or quota pressure;
3. before a new route or PM staffing decision, perform one bounded best-effort refresh when the provider snapshot is stale;
4. refresh again after a quota/rate-limit failure so the durable observation can catch up quickly;
5. never replace the last known snapshot with fabricated `0%`, `100%`, or an invented reset timestamp when collection fails;
6. use fresh `used_percent` as Router `quota_pressure` so capacity with more headroom is favored when capability/policy permit it;
7. fresh authoritative exhaustion may make only the mapped model/group unavailable;
8. fresh authoritative capacity may reconcile an old **quota-only** transient failure after reset, but must never clear authentication, bridge/provider health or deterministic model-health failures;
9. collector failures are fail-open for coding execution: normal durable provider-health/failure semantics remain active;
10. quota reads are observability/routing inputs only. They do not reset provider quotas, extend Runtime job budgets, resume blocked jobs, or authorize control actions.

Dashboard and authenticated diagnostics must expose source, freshness, used/remaining percentage and reset time when upstream actually supplied those values. Unknown fields must remain visibly unknown.

## 9. Quota terms and non-authoritative limits

The platform may record observed usage, failures, latency, selected model/provider/quota group and local request counts.

It must not present an authoritative "quota remaining" value unless the upstream exposes a reliable authoritative counter for that exact model/bucket/window. Product documentation about weekly limits, RPM, subscription tiers or refresh cadence is useful policy context but is **not** a substitute for a fresh account-specific snapshot.

The Human Owner has funded at least $10 of OpenRouter credit, which has historically affected documented free-model request allowances. Those external terms may change; they are not architecture invariants and are not currently collected by the Codex/Antigravity telemetry integration.

## 10. Rollout rule

Provider/model/telemetry changes should be introduced incrementally:

1. validate explicit model IDs and telemetry interfaces against current provider documentation or protocol source;
2. implement collection behind existing service/credential boundaries without exposing provider secrets to coding agents;
3. add deterministic parser, stale-data, reconciliation, routing-pressure, dashboard and secret-non-disclosure tests;
4. bump affected service versions;
5. obtain green CI and the review/merge required by current governance;
6. only at a stable blocked/terminal Runtime gate, roll out locally and verify service/config/bridge versions;
7. query the deployed read-only quota endpoint and compare it with provider UI/CLI evidence before allowing telemetry to influence normal routing;
8. preserve fail-open behavior if an upstream quota schema changes or becomes unavailable.

Never force-complete work or restart Runtime/DDEV while a job is in flight.
