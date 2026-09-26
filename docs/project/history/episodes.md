# PCP Episodic Memory Index

Status: Tier-3 historical index under #313/#314.

This file is intentionally compact. It records reusable lessons and authoritative references for completed incidents/rollouts without turning `current-state.md` into an append-only history.

Detailed chronology remains in Git history, GitHub issues/PRs, Runtime durable state and CI.

## 2026-09 — execution-efficiency and recovery

### Healthy-progress executable alignment — #224 / PR #226

Outcome: merged and live-proven.

Durable lesson:
- healthy work may adopt adaptive headroom without replacing the durable job/workspace or resetting consumed counters;
- static budget thresholds alone are not Human Owner gates.

Evidence:
- issue #224;
- PR #226;
- final source CI #401;
- preserved DEC-025C-r2 live proof.

Status: historical implementation evidence; policy remains current in `efficiency-model.md`.

### Autonomous provider recovery — #228 / PR #229

Outcome: merged and locally activated.

Durable lesson:
- provider/model/quota failures should fall through autonomously while another eligible route remains;
- failed capacity must remain durable so routing cannot loop back to already-proven-bad capacity;
- provider-failover counts are telemetry/reassessment inputs, not standalone owner gates.

Evidence:
- issue #228;
- PR #229;
- merge `bd24f18a0983ed370681f253edeb0606cf9e80cf`;
- exact-head CI #408.

Status: historical rollout; current policy lives in T2.

### Retired Chợ Nhạc DEC-025C orchestration

Outcome: PCP orchestration retired by Human Owner; durable history preserved.

Historical identity:
- plan `pm-gh-5650852312`;
- WorkOrder `DEC-025C-1-recovery-tooling-r2`;
- job `eec59b13651c54559c10ce204380a68e`;
- branch `ai/eec59b13651c`.

Durable lesson:
- do not revive a retired product WorkOrder merely because its historical job remains queryable;
- use supported Runtime cancellation/cleanup and retain durable audit records;
- historical product evidence must not masquerade as active work.

Status: retired/historical. The missing-workspace legacy cleanup compatibility gap discovered later is tracked in open issue #282.

## 2026-09 — Chợ Nhạc UI-CL-1 platform hardening

### WorkOrder protected-change false positive — #262 / PR #263

Outcome: fixed and activated.

Durable lesson:
- explicit WorkOrder risk flags are authoritative for plan-orchestrated protected-change hints;
- preservation/out-of-scope wording must not be misread as intended security/schema/API changes;
- legacy free-text routing may retain keyword inference separately.

Evidence:
- issue #262;
- PR #263;
- merge `427b930c44a91b1e262419d488aa8469298c80c1`.

Status: historical defect/lesson.

### Reviewer repair/rebuttal re-check — #284 / PR #285

Outcome: merged.

Durable lesson:
- reviewer re-check may consume only the bounded current developer repair/rebuttal report;
- WorkOrder and deterministic repository evidence remain authoritative;
- prior raw stdout/stderr must not grow reviewer context without bound.

Evidence:
- issue #284;
- PR #285;
- merge `836af29f3ee308e1ea5aab8a47194b2ada682331`.

Status: historical implementation evidence.

### Current-tail repeated-failure detection — #286 / PR #287

Outcome: merged.

Durable lesson:
- circuit breaking must evaluate the consecutive suffix matching the most recent durable failure fingerprint, not stale repetitions earlier in history;
- complete failure history remains audit evidence.

Evidence:
- issue #286;
- PR #287;
- merge `3075a4f588074a2206909360b56b20029003e335`.

Status: historical implementation evidence.

### GitHub Actions pre-run failure classification — #288 / PR #289

Outcome: merged.

Durable lesson:
- runner/startup failures that occur before repository execution are delivery infrastructure failures, not engineering repair evidence;
- accepted source identity must survive delivery retry;
- legacy recovery must reconstruct accepted delivery state only from authoritative PCP-owned durable evidence.

Evidence:
- issue #288;
- PR #289;
- merge `2174a1efd595aa79f6a750fc3d5cba150e7db737`.

Status: historical implementation evidence.

### Trusted exact-SHA CI revalidation — #291 / PR #292

Outcome: completed after the historical current-state snapshot.

Durable lesson:
- CI recovery must bind evidence to the exact requested commit SHA;
- trusted commit status needs exact repository/run/publisher identity and must fail closed on ambiguous/missing metadata.

Evidence:
- issue #291;
- PR #292;
- GitHub/CI history is authoritative for final merge identity.

Status: historical implementation evidence.

### Owner-attention generation and supersession — #293 / PR #294

Outcome: merged.

Durable lesson:
- polling/no-op timestamps must not create fresh Human Owner attention generations;
- obsolete pending owner attention/control actions should become superseded/cancelled while sent/executed audit history remains immutable.

Evidence:
- issue #293;
- PR #294;
- merge `a08e2bd58e2ea2f00b1ee8701031f9fb74d55d6a`.

Status: historical implementation evidence.

### Explicit superseded orchestration lifecycle — #295 / PR #296

Outcome: completed after the historical current-state snapshot.

Durable lesson:
- supersession is an explicit lifecycle operation bound to exact identities; it is never inferred from timestamps, later success or prose;
- superseded orchestration remains queryable as history but is excluded from new execution/owner-attention eligibility.

Evidence:
- issue #295;
- PR #296;
- GitHub/Runtime history is authoritative for final merge/activation identity.

Status: historical implementation evidence.

## 2026-09 — resource hygiene

### Dedicated PCP BuildKit isolation — #281 / PR #283

Outcome: source merged, locally activated and live accepted; #281 and parent #277 later closed as stale-open completed issues.

Durable lesson:
- PCP custom-service and executor-owned workspace builds use a dedicated `pcp-builder` cache namespace without changing the user's globally selected builder;
- destructive cleanup must use authoritative zero-active-work gates and exact PCP ownership;
- shared/default BuildKit cache must never be pruned merely because PCP has its own GC path.

Evidence:
- issue #281;
- PR #283;
- merge `f858d4b1323a5803e818c1e2b1ae61254458e145`;
- local activation/disk evidence in Git history and issue comments.

Status: historical rollout. Legacy terminal cleanup without an existing workspace remains a separate open compatibility issue #282.

## 2026-09 — direct workspace and preview

### Chợ Nhạc direct workspace + job-owned live preview — #297

Outcome: locally accepted and closed.

Durable lesson:
- direct mode requires an exclusive project lease and exact registered workspace;
- Dashboard mutation uses a separate control boundary;
- preview transport resets must reconcile durable state rather than treating a dropped HTTP connection as proof of failure;
- frontend health must avoid nested shell reconstruction through DDEV; raw argv execution with Python-owned retries is the accepted approach;
- terminal job-owned preview retirement must precede lease release.

Primary evidence:
- #298 / PR #300;
- #299 / PR #301;
- corrective PRs #304, #306 and #307;
- implementation merge through `56e5abe52c6129b5c198c661bfef95242c7dd8c4`;
- final rollout documentation PR #308.

Status: historical rollout; capability remains current.

### Project-level Current site preview — #309

Outcome: locally accepted and closed.

Durable lesson:
- idle project preview is not an engineering job and does not hold the engineering lease;
- when a direct job starts, it first acquires the normal lease, retires idle preview, then prepares/switches the direct workspace;
- terminal direct-job cleanup must return the exact clean job-owned branch to the existing local base branch before lease release;
- dirty or externally changed source fails closed and keeps the lease rather than resetting/stashing/cleaning Human Owner work.

Primary evidence:
- PR #310 — project-level Current site;
- PR #311 — safe terminal return-to-base lifecycle;
- PR #312 — rollout documentation;
- implementation merge `add228f7258887390651686aa711529eaf6c0d3b`;
- documentation merge `d2dc61e7d34082bb88925639c3ee8129b8f30056`.

Last accepted local outcome:
- zero active engineering jobs;
- zero Chợ Nhạc engineering lease;
- Chợ Nhạc clean on `main`;
- Current site Frontend Ready at `https://chonhac.ddev.site:3100`.

Status: historical rollout; capability remains current.

## Retrieval guidance

Use this file when the current task asks:

- why a current policy exists;
- whether a similar platform defect happened before;
- what lesson came from a prior rollout/incident;
- which issue/PR contains detailed evidence.

Do not use an episode as proof of current live state. For current state, consult T1 plus live Runtime/GitHub/source evidence.
