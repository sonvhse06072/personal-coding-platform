# Chợ Nhạc — Historical direct-workspace lease retirement gate

Status: **APPROVE_SUPPORTED_HISTORICAL_JOB_CANCEL_FOR_LEASE_RETIREMENT_ONLY**.

This approval is limited to the historical Runtime job
`c02defa348fc5b19a0bd021e2697571e` after GH-63 supersession reconciliation.
It does not authorize candidate supervision release or implementation execution.

## Preconditions established by reconciliation

Snapshot `2026-10-04T16:20:55.930831+00:00` established:

- Runtime 1.0.106 / executor 1.0.31 healthy;
- zero active engineering/executor jobs;
- all historical and rejected orchestration WorkOrders were superseded exactly;
- candidate `pm-b0748be27f8446a0813c2d1fe7d697fd` remained generation-1
  `supervised_hold` / held / seven pending / zero child jobs;
- historical Runtime job remained `blocked`;
- its progress/checkpoint/result evidence was unchanged by supersession;
- lease remained active generation 9 and owned by the same historical job;
- preview was absent;
- direct Chợ Nhạc worktree was clean on `ai/c02defa348fc` at
  `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba`.

Acceptance was recorded in Chợ Nhạc #63.

## Supported Runtime cancellation semantics

Runtime `POST /v1/jobs/{job_id}/cancel` delegates to the existing
`engine.cancel` lifecycle. For a non-terminal direct-workspace job it:

1. marks the exact job `cancelled` and clears its current `error`;
2. cancels any executor/active task for that job;
3. retires an active preview if one exists;
4. does not run manual-job quiesce behavior for an orchestrated WorkOrder;
5. calls the ddev-executor direct-workspace return-to-base path;
6. records `checkpoint.direct_base_restore` evidence;
7. releases the exact project lease only when preview retirement and workspace
   restoration both succeed.

The executor return-to-base path is fail-closed:

- direct workspace only;
- exact configured owning AI branch or already-configured base branch;
- clean worktree required;
- configured local base branch must already exist;
- no reset, clean, stash, branch deletion, implicit base creation or remote
  update;
- checkout is only to configured `main`;
- the final worktree must remain clean.

Runtime tests cover ordering preview -> restore -> lease release and keep the
lease when preview retirement fails. Project-lease tests require exact owner
release and preserve active ownership when cleanup is incomplete.

## Evidence expected to change

Cancellation is a deliberate terminal lifecycle transition, so these historical
fields are allowed to change:

- job `status`: blocked -> cancelled;
- job `updated_at`;
- job `error`: cleared to null;
- checkpoint digest, only because `direct_base_restore` evidence is appended;
- lease `state`: active -> released and lease `updated_at`;
- actual direct Git checkout: owning AI branch -> local configured `main`.

These changes do not rewrite model/tool/test/repair counters or the saved result.

## Evidence that must remain preserved

The cancel-only helper must verify:

- exact historical job id/project/source/workspace/record before mutation;
- pre-cancel progress and result hashes match reconciliation evidence;
- checkpoint before mutation matches reconciliation evidence;
- no active Runtime/executor jobs;
- no preview;
- lease exact owner/generation/state;
- Chợ Nhạc direct worktree clean at the reviewed AI branch/head;
- local and authoritative remote `main` equal the approved r3 source
  `aa8e68dd9aea6740de446151eb97615931de9b40`;
- AI branch ref remains preserved at
  `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba`.

After mutation it must verify:

- historical job is `cancelled`;
- progress and result hashes are unchanged;
- checkpoint has an exact successful `direct_base_restore` record pointing to
  branch `main` at the approved source;
- actual Chợ Nhạc worktree is clean on `main` at approved source;
- AI branch ref is not deleted or moved;
- lease state is `released`, same owner and generation 9;
- candidate remains generation-1 held/seven pending/zero jobs;
- historical/rejected orchestrations remain superseded.

## Explicit exclusions

The lease helper must not:

- call cleanup;
- remove DDEV data/workspace;
- delete or reset Git branches;
- fetch/merge/pull Chợ Nhạc;
- restart PCP;
- run orchestrator tick;
- submit intake or call a model;
- call plan continue/release;
- create a candidate child job.

If cancel returns but restore/lease release does not complete, stop. Do not
manually clear the lease or checkout/reset/clean the repository to force the
gate.

## Next gate after PASS

After successful historical-job cancellation and lease retirement, read fresh
candidate hold identity, Git state, active jobs and quota/provider state. Only
then may PM consider releasing exact generation 1 for
`AP-MVP-01-artist-profile-data-curation`.
