# Provider quota telemetry

PCP treats provider quota as external resource telemetry, not as WorkOrder execution usage.

## Contract

Fresh quota snapshots are normalized to provider-state keys immediately before Router `route` and `staff` decisions. Telemetry can add quota pressure or unavailability but cannot clear durable Runtime failure state. Stale or unavailable telemetry is omitted and collection failures are fail-open.

Snapshots record only provider/model/quota identity, used/remaining percentage when supplied by the provider, reset time/window metadata, source, freshness and availability. PCP does not persist provider access tokens, Antigravity CSRF tokens, account email, prompts, transcripts or raw provider responses.

## Codex

Codex quota is read through the supported app-server JSON-RPC method `account/rateLimits/read`. PCP preserves separate primary/secondary windows and `rateLimitsByLimitId` buckets. `ordinaryUsageAllowed=false` is an authoritative denial; reset timestamps alone never infer recovery.

## Antigravity

Antigravity has two quota inputs:

1. A best-effort host-local `GetUserStatus` probe against the running Antigravity language server. This exposes the same local quota state used by `/usage`, but the local protocol is not a supported public API and therefore may change. The CSRF token is discovered and used only in memory on localhost and is never logged, persisted or returned by the bridge.
2. The documented custom status-line JSON `quota` payload as a fallback. PCP installs its silent quota sink only when no user custom status-line command exists; an existing user command is never overwritten.

Both inputs are reduced at the host boundary to quota remaining/reset/model/plan metadata before Runtime can read them. If neither source is fresh, Antigravity quota is unknown and existing Runtime provider-failure semantics remain in force.

## Routing

Quota pressure is advisory below exhaustion and becomes unavailable when an authoritative fresh snapshot reports no remaining quota. Router continues to combine model health, model quota, shared quota-group health and provider health. Telemetry does not consume model/tool/test budgets and does not reset or replace a job.
