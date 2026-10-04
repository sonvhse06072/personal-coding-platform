# Chợ Nhạc — Exact reconciliation mapping for GH-63 successor

Status: **APPROVE_EXACT_SUPERSESSION_MAPPING_NOT_LEASE_CHANGE_NOT_RELEASE**.

This document records PM-reviewed execution mapping only. It does not change
ProjectBaseline authority, cancel jobs, release leases, continue plans, or
authorize implementation.

## Evidence snapshot

Read-only inventory observed at `2026-10-04T15:59:00.003639+00:00`:

- candidate: `pm-b0748be27f8446a0813c2d1fe7d697fd`;
- candidate plan digest:
  `f667ffe9d27fc3824f550089cf09269b0cfa7ccc58654d8c9e8a30e91ac7ab7d`;
- candidate orchestration: active / supervised_hold / generation 1 / held;
- candidate has exactly seven pending active agent rows, every `job_id=null`,
  ready set only `AP-MVP-01-artist-profile-data-curation`;
- historical plan:
  `pm-5cd9ec06f74b4feba4db5a1507ab35f0`, blocked/generation 0;
- historical job:
  `c02defa348fc5b19a0bd021e2697571e`, status blocked;
- direct-workspace lease: active generation 9, same historical job owner,
  preview absent;
- rejected plans:
  `pm-095d6aea0fe94901bbf692fa7d113fc2`,
  `pm-a72e960c0f3b458897831cff3fb51a30`,
  `pm-ac6a52e6019947adab8744a7ada72011`;
- each rejected plan is active / supervised_hold / generation 1 / held with
  seven pending rows and zero child jobs;
- helper made zero model calls and zero mutating API requests;
- storage records and Git state were unchanged between reads.

The inventory was produced against Runtime 1.0.106 and ddev-executor 1.0.31 with
zero active engineering/executor jobs.

## Canonical candidate identities

1. `AP-MVP-01-artist-profile-data-curation`
2. `AP-MVP-02-artist-profile-public-experience`
3. `EE-0-01-event-backend-domain-api-access`
4. `EE-0-02-public-event-discovery-detail`
5. `EE-0-03-studio-event-management-participation-program`
6. `AP-MVP-03-generalized-verified-performance`
7. `EE-0-04-event-engagement-analytics`

Candidate content was approved separately in
`pilot-successor-pm-review-b0748be-2026-10-04.md`.

## Historical r1 mapping

The source definitions and GH-63 replan contract establish:

| Historical WorkOrder | Successor |
|---|---|
| GH-63-PILOT-01 | **none — retire only** |
| GH-63-PILOT-02 | AP-MVP-01-artist-profile-data-curation |
| GH-63-PILOT-03 | AP-MVP-02-artist-profile-public-experience |
| GH-63-PILOT-04 | EE-0-01-event-backend-domain-api-access |
| GH-63-PILOT-05 | EE-0-02-public-event-discovery-detail |
| GH-63-PILOT-06 | EE-0-03-studio-event-management-participation-program |
| GH-63-PILOT-07 | AP-MVP-03-generalized-verified-performance |
| GH-63-PILOT-08 | EE-0-04-event-engagement-analytics |

PILOT-01 has no replacement because its product change is already accepted and
merged. Its Runtime job remains blocked historical/incident evidence; do not
rewrite it to completed.

### Required historical supersession order

Retire **PILOT-02 through PILOT-08 first** while PILOT-01 remains blocked.
Retire blocked PILOT-01 last.

This order is required because `supersede_work_order` recalculates source-plan
status after each transaction. Keeping PILOT-01 active/blocked until the end
prevents pending historical work from becoming the apparent controlling state
during partial reconciliation.

## Rejected-plan mapping

For each of the three rejected plans, every source WorkOrder maps by the exact
same ID to the approved candidate.

The rejected plans are evidence of failed/incorrect proposal generations:
- r2 plan contained historical template visual routes;
- one r3 plan had profile-floor contradictions;
- one r3 plan included unacceptable verified-performance/route semantics.

Supersession does not mean their contents were accepted. It only retires their
orchestration eligibility in favor of the separately reviewed candidate.

## Runtime supersession semantics reviewed

The supported endpoint is:

`POST /v1/plans/{plan_id}/work-orders/{work_order_id}/supersede`

with:
- exact reason;
- optional replacement plan id;
- optional replacement WorkOrder id.

The Runtime store:
- permits source states pending / blocked / waiting_human / awaiting_merge;
- refuses in-flight source jobs;
- validates replacement plan/project/WorkOrder identity;
- marks source WorkOrder lifecycle superseded;
- does **not** modify source state, Runtime job, result, progress, workspace or
  counters;
- does **not** release the direct-workspace project lease;
- retires matching attention/control-action rows;
- makes an exact retry idempotent only when replacement/reason are identical.

Each call is its own transaction. This is not an all-plan atomic batch.

## Safety gates for supersession-only execution

Before first mutation:
- Runtime health 1.0.106 and executor 1.0.31 healthy;
- active engineering jobs = 0 and executor active_jobs = 0;
- candidate digest and generation-1 hold identity unchanged;
- historical job remains exact blocked job;
- lease remains exact active generation-9 historical ownership;
- Chợ Nhạc worktree remains clean on `ai/c02defa348fc` at
  `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba`;
- source plan definitions/state/digests remain the reviewed inventory values.

During mutation:
- do not call orchestrator tick;
- do not cancel/cleanup the historical job;
- do not release lease;
- do not continue/release candidate supervision;
- verify candidate remains held/zero-job after every source plan batch;
- verify historical job/lease/worktree evidence remains unchanged.

After mutation:
- historical plan and all three rejected plans must have no active WorkOrders;
- their orchestration lifecycle must be superseded;
- historical Runtime job must still be blocked with unchanged durable
  progress/checkpoint/result evidence;
- lease must still belong to that blocked job;
- candidate must remain active / supervised_hold / generation 1 / held, exactly
  seven pending and zero jobs.

## Separate lease gate

Supersession does not solve direct-workspace ownership.

The supported Runtime cancel path can:
- change the historical job status to cancelled;
- retire preview if present;
- return a clean direct workspace from its AI branch to configured base;
- then release the exact project lease.

That branch/worktree side effect is intentionally **not** authorized by this
mapping document. Review it only after supersession evidence is complete.

AP-MVP-01 must not be released until that separate lease lifecycle gate has been
reviewed and accepted.
