# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
live Runtime/GitHub evidence remain authoritative over chat history. Completed
chronology belongs in Tier-3 history, not here.

Last updated: 2026-10-04 theo owner rollout v3 PASS; local Runtime 1.0.106
đã xác minh. Bước hiện tại là successor planning review, chưa release execution.

## Resume order

1. Read repository-root `AGENTS.md`.
2. Read `docs/project/README.md`.
3. Read this compact current-state snapshot.
4. Retrieve only the T2 topical documents and T3 episodes relevant to the
   current task.
5. Inspect live GitHub `main`, active issue/PR, local branch/worktree,
   Runtime/executor health, active WorkOrder/job and project lease before
   mutation.
6. Fetch raw CI/log/transcript evidence only when diagnostics or audit require
   them.

Memory-tier rules are in `context-memory-architecture.md`. Historical reusable
lessons are indexed in `history/episodes.md`.

## Current platform snapshot

- PCP #466 / PR #468 đã merge tại
  `6fcf5b79a35921ebd887736138b0279222e93224`; source Runtime là `1.0.106`.
  Exact head `66f9a38d2fe01762054cd6a1f1e6e3b0008cae1a` có workflow tests
  run `37199654326` PASS ở structure, Runtime, Router và ddev-executor.
  Read response dùng non-executable `ExecutionPlanSnapshot*` models; shared
  WorkOrder/PM proposal validators vẫn strict.
- Owner rollout v3 PASS xác nhận local PCP main
  `e7fb6d364f109a2ddee979d3a040367b03d87f73` clean, Runtime `1.0.106`,
  Router/executor healthy, executor `1.0.31`, active engineering jobs và executor
  active_jobs đều 0 tại lần kiểm tra. Output không có observed_at; không gán
  timestamp mới cho lần chạy. Không cần rollout/restart #466 lần nữa.
- Historical GET `pm-095d6aea0fe94901bbf692fa7d113fc2` trả 200, giữ đủ
  7 template routes; strict WorkOrder/PM proposal replay trong process bị từ
  chối. Digest v3 `7d49d87afd3c165eff72bf3f97e3f36f9465465bd992879546db4e3a2b376f32`
  giống nhau trước build, trước restart và sau acceptance. Không so digest này
  với probe khác khi chưa thống nhất serialization; không gọi in-process replay
  probe là HTTP POST replay test.
- Lease lịch sử vẫn active generation 9, owner
  `c02defa348fc5b19a0bd021e2697571e` blocked, preview absent; record lease
  và Chợ Nhạc worktree không đổi qua restart. Bảo toàn ownership không đồng
  nghĩa giải phóng lease cho successor job. Không cancel/cleanup để vượt gate.
- PCP #463 đã hoàn thành qua PR #464, merge commit
  `0706cd119ebf2dcac9481b28799e5d835b2518ff`; Runtime của bản sửa đó là
  `1.0.105`. Exact PR head `ecda44f5138a3c1d3817e5b2d9bc49ded20b4b97`
  có workflow `tests` run `37159249321` PASS ở cả bốn nhóm.
- PM prompt có `AUTHORIZED_SOURCE_REFERENCE_PATHS`, sort/deduplicate từ đúng
  `ProjectBaseline.references`. WorkOrder/DecisionBoundary chỉ được cite tập
  này; authority-only paths không tự thành references. Validator fail-closed
  giữ nguyên. Rollout v3 xác nhận r3/source, 27 reference paths, docs/12 absent
  và docs/26 present; exact prompt allowlist đã được kiểm tra ở snapshot trước.
- Rollout v3 không thu quota mới. Các số Codex/Gemini/Claude trong snapshot cũ
  không là điều kiện cho model call mới; phải đọc telemetry/freshness và giữ
  nguyên available=false/reserve policy. Bridge `1.13` và registry `11` cũng
  chưa được đọc lại phiên bản trong output rollout này.
- PCP #446 / PR #447 is complete at
  `645200e1f0e1ea1902569f471a53d5b90699ece6`: canonical WorkOrder diff
  identity is source-commit-relative across Runtime-created commits,
  `no_effect` is turn-local, and reviewer/PM response-only semantic turns are
  not mislabeled as no-effect.
- #438 targeted-verification shell repair is complete through PR #439 at
  `841890e60e486d6e4e823b9919e9e79de6cbf6a0`.
- #440 Antigravity Developer Activity coalescing is complete through PR #442 at
  `c2ee43c35042a58883d2f739c5efba7b528bd4db`: transport-level response
  deltas are not persisted; Runtime emits one bounded/redacted completed response.
- #441 is complete through PR #443 at
  `38454b56adf02459a197dbc5ccbde024462d964d`; the
  `destructive_migration` path heuristic no longer treats Drupal
  `config/schema/*.schema.yml` metadata as a destructive database/content
  migration while true migration/schema paths remain protected.
- #400 repository-CI parity is complete. Chợ Nhạc PR #64 merged at
  `af1e24a60fc43cae0c417dc312e7a7839f284b6b`; protected workflow changes are
  authorized by DEC-034 and use bounded changed-module Unit/Kernel/Functional
  verification without requiring Docker/DDEV privilege on the self-hosted
  repository runner.
- #406 incident learning is complete through PCP PR #436 at
  `cf34010e18cc0580a965098456872127fee1953a`. Runtime creates stable,
  deterministic, model-free incident candidates only for repeated/expensive/
  platform anomalies and carries bounded references through telemetry,
  continuity and PM evidence.
- #421 visual-preview evidence is complete through:
  - Chợ Nhạc collector PR #65:
    `f81e0ca86fdc9471854cfb702c43f5902e416a50`;
  - Chợ Nhạc evidence-redaction PR #66:
    `aa51045dacf5afe41c0d7ce3564c7303cd56847d`;
  - PCP PR #437:
    `7b1cd6ee050440ae624a242678246f5252189195`.
- `visual_quality` is a bounded final verification phase after
  `frontend_quality`. It requires a direct workspace, exclusive lease,
  enabled frontend preview and 1..4 local `visual_routes`; Runtime owns preview
  lifecycle and ephemeral evidence requests.
- Chợ Nhạc visual evidence uses viewports 360/390/430/768/1024/1440 and captures
  route/viewport, HTTP/navigation, console/page errors, failed request paths,
  DOM landmarks, horizontal overflow and local screenshot hashes. Textual
  evidence redacts common secrets and strips embedded URL query/fragment data.
- Screenshot capture alone is not represented as multimodal review.
  `image_reviewed=false` forbids pixel-level/aesthetic claims by a text-only
  evaluator.
- PM planning can require configured `frontend_quality` and `visual_quality`
  phases for material user-facing UI WorkOrders.
- Chợ Nhạc targeted Runtime verification follows changed custom Drupal modules
  and runs their Unit/Kernel/Functional suites instead of hard-coding Show.
- `gemini-3.8-flash-medium` is correctly modeled as no-explicit-effort while
  registry-v10 persisted effort metadata remains backward-compatible for
  blocked-job recovery.
- Chợ Nhạc remains the first trusted-local project: exact direct workspace +
  `antigravity_host` + execute/repair may use bounded DDEV; plan/evaluate,
  Codex/OpenCode, direct Docker, sudo, remote/destructive Git, merge and deploy
  remain outside developer authority.
- PM-controlled merge remains enabled for Chợ Nhạc routine/standard WorkOrders
  under exact-head CI/review/protected-boundary gates. Developer agents never
  merge; production is never implied.
- The #146 efficiency implementation program is complete. Future efficiency
  work starts from natural telemetry/incident evidence in focused issues rather
  than keeping a perpetual umbrella or creating synthetic tasks.

For executable details, inspect code/tests on current `main`. Historical
rollout/incident rationale belongs in `history/episodes.md`.

## Chợ Nhạc project state

Approved ProjectBaseline for **new** PCP-managed Chợ Nhạc work:

- active revision: `pilot-v1-2026-10-04-dec033-r3`;
- immutable baseline source:
  `aa8e68dd9aea6740de446151eb97615931de9b40`;
- r3 is the narrow planning-authority correction tracked by PCP #459. It keeps
  the exact r2 source/authority and adds the already-authorized local-only
  `docs/26-local-demo-workflow.md` to `requirements` and `quality_policy`
  references so PM WorkOrders may cite the DEC-030 fixture/purge contract;
- r2 remains immutable at
  `aa8e68dd9aea6740de446151eb97615931de9b40` and explicitly resolvable;
- r2 is the post-PILOT-01 successor baseline authorized by the #63 replan
  boundary and preserves r1 authority/reference categories while pinning the
  governed Chợ Nhạc main that includes PILOT-01 plus CI governance repairs;
- r1 remains immutable at
  `132c2ef767b595833677e9672d655872e07ba9b7` and explicitly resolvable;
- r1 was activated by PCP PR #429 at
  `95f4d8a5522112efa4ad0f7e710be0641a5d9159` after the first #63 planning
  attempt exposed missing legitimate Profile source references;
- r1 added protected `docs/14-cho-nhac-profile-implementation-plan.md` and
  `docs/15-account-email-verification-producer-plan.md` to requirements;
- the original `pilot-v1-2026-10-03-dec033` revision remains immutable and
  explicitly resolvable;
- PCP baseline activation merged through PR #425 at
  `ccdd1712ff8ea75a14a061b30122dc4988558630`;
- pre-existing GH-42 plan/jobs keep their stored
  `mvp-v1-2026-10-01-completion` baseline until explicitly superseded;
- protected completion authority includes the current MVP contract,
  permissions/access matrix, business rules and architecture documents pinned
  by `config/project-baselines.yml`;
- direct project root: `/home/sonvh/chonhac`;
- runtime mode: `workspace_mode: direct`;
- exclusive engineering lease: enabled;
- AI branch prefix: `ai`.

The immutable ProjectBaseline source is an authority boundary, not a claim that
the live product repository must remain at that commit.

Current implementation evidence:

- DEC-033 remains the canonical controlled-pilot execution decision.
- Historical generated plan:
  `pm-5cd9ec06f74b4feba4db5a1507ab35f0`.
- PILOT-01 / GH #61 is accepted and merged.
- Chợ Nhạc PR #67 merged as
  `aa8e68dd9aea6740de446151eb97615931de9b40`.
- Exact product head validated before merge:
  `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba`.
- Current-base CI run 69 passed documentation authority, Composer,
  isolated PostgreSQL 17 Unit/Kernel/Functional verification, PHPCS and the
  controlled self-repair probe.
- Final PILOT-01 product diff remained 16 files / +223 / -56, within #61's
  <=25-file budget and without Event/payment/deployment scope expansion.
- Preserved historical direct job:
  `c02defa348fc5b19a0bd021e2697571e`.
- Preserve that job/workspace/counters as incident/work evidence; do not spend
  further model quota attempting to complete an already-merged product diff.
- Chợ Nhạc #68/#69 fixed PR documentation-authority range semantics by using
  merge-base-to-head while preserving the fail-closed checker.
- Chợ Nhạc #70/#71 restored PostgreSQL-backed repository CI after one-time
  PostgreSQL 17 provisioning on the self-hosted Chonhac-CI host. Repository CI
  still does not gain Docker/DDEV authority and uses isolated per-job clusters.
- Generated PILOT-02..PILOT-08 remain untouched/pending and must **not** be
  released from the old plan.
- Baseline successor r3 đã tồn tại và giữ nguyên source
  `aa8e68dd9aea6740de446151eb97615931de9b40`. Không tạo r4 hoặc thêm
  `docs/12-launch-metrics.md` vào references để hợp thức hóa output của model.
- Frontend-heavy successor WorkOrders use
  `frontend_quality -> visual_quality` with concrete bounded routes only when
  those routes are renderable by the WorkOrder.

Historical DEC-025 and GH-42 execution are retired. Do not recreate, reroute or
resume them.

## Active PCP follow-up work

PCP #466 source repair và local activation đã được PM chấp nhận theo owner
rollout v3 PASS. Evidence acceptance nằm ở comment #466
`5981132981`; không mở lại diagnostic/restart để xác nhận điều đã đủ chứng cứ.

Bước hiện tại: rà/chốt một canonical supervised successor intake cho đúng
#48/#49/#56/#57/#58/#50/#59. Đã đọc live bodies của bảy issue, #63 replan và
comments liên quan, cùng DEC-033 mapping trong baseline docs/27. #56 có nhãn
cũ giao provider cho EE-0-04; đã sửa tham chiếu thành AP-MVP-03 #50, analytics
vẫn riêng #59. Không sửa product authority/baseline vì lỗi nhãn này.

Chi tiết review, dependencies, budgets, routes và fixture ownership:
`pilot-successor-review-2026-10-04.md`. Đây là execution preparation/evidence,
không phải nguồn mới được tự thêm vào ProjectBaseline.references.

Successor attempt `pm-d2947a399ecb44de9e96d174bd4c2d48` được giữ làm evidence:
planner đã cite `docs/12-launch-metrics.md`, một authority-only path không
thuộc r3 references. Authority classification không đồng nghĩa quyền cite.
`usage=null` không chứng minh model chưa được gọi.

PCP #461/#462 is complete at Runtime `1.0.104`: new PM plans reject
`max_profile` below their risk/protected-flag floor. PCP #457/#458,
#455/#456, #453/#454 and #451/#452 are also complete.

Local state tại owner rollout v3, không phải bảo đảm về sau:

- `pm-095d6aea0fe94901bbf692fa7d113fc2`,
  `pm-a72e960c0f3b458897831cff3fb51a30` và
  `pm-ac6a52e6019947adab8744a7ada72011` vẫn active, supervised_hold,
  generation 1, held; mỗi plan đúng 7 pending WorkOrders, mọi job_id null,
  ready set chỉ AP-MVP-01. Không release các rejected plans.
- Historical job `c02defa348fc5b19a0bd021e2697571e` vẫn blocked, lease
  active generation 9; Chợ Nhạc clean trên `ai/c02defa348fc` tại
  `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba`. Rollout không thu lại toàn bộ
  orchestration của historical plan `pm-5cd9ec06f74b4feba4db5a1507ab35f0`;
  trạng thái blocked/generation 0 của plan là snapshot trước, cần GET mới
  trước reconciliation.
- Failed planning attempts giữ nguyên làm evidence. Không xóa plan, reset
  counters/history, sửa SQL, resume historical job hoặc tạo replacement chỉ
  để né blocker. Fresh successor planning có semantic scope bảy phần đã duyệt,
  không phải replay PILOT-01 hay giả lập hoàn tất historical job.

## Recently completed reusable work

Completed implementation chronology does not remain in T1. Important recent
examples now belong in `history/episodes.md` and GitHub/Runtime history:

- exact-diff protected-signal authorization (#387 / PR #388);
- collaboration budget/continuation/recheck/handoff hardening
  (#389, #391, #393, #395, #397 and their PRs);
- PM approval-output contract correction (#401 / PR #402);
- deterministic verification/Kernel DB/retry-loop hardening
  (#404 / PR #405);
- Chợ Nhạc GH-42 WO-01 / PR #44;
- PHP-runtime capability advertisement (#399);
- trusted-local Chợ Nhạc developer execution (#426 / PR #427);
- frontend_quality exposure to PM planning (#430 / PR #431);
- changed-module Drupal targeted verification (#432 / PR #433);
- Flash Medium capability / reviewer-context recovery (#434 / PR #435);
- Chợ Nhạc repository-CI parity (#400; Chợ Nhạc PR #64 / DEC-034);
- deterministic incident-learning candidate / PM triage (#406 / PR #436);
- automatic visual-preview evidence loop (#421 / PR #437) plus Chợ Nhạc
  collector/redaction PRs #65/#66;
- historical ExecutionPlan read compatibility (#466 / PR #468).

## Global operational gates

- Normal engineering flow: issue -> bounded WorkOrder -> deterministic
  verification/review -> PR/exact-head CI -> PM review -> eligible PM merge.
- Never force push.
- Developer agents never merge.
- Human Owner retains protected scope/architecture/security/destructive-data/
  production/governance/material-budget authority.
- A Human Owner request is a high-authority input to PM reasoning, not an
  automatic guarantee that the proposed tactic is optimal. PM should verify,
  assess and recommend before material execution when alternatives matter.
- Routine reversible in-scope actions should not create needless owner approval
  loops.
- Production deployment is never implied by PR merge.
- Runtime durable execution state is authoritative; never hand-edit it to bypass
  the state machine.
- Do not restart/rebuild platform services while engineering work is active.
- Direct-workspace operations must preserve Human Owner changes; never
  reset/stash/clean/discard them to make automation succeed.
- Broad Docker/system/image/volume prune remains prohibited.
- Time-sensitive claims such as active jobs, leases, branch/HEAD, PR/CI and
  service health must be checked live before acting.
- The approved ProjectBaseline stays pinned until an explicitly approved
  successor revision is activated.
- PM merge evaluation must stop when the final exact diff introduces a genuine
  Human Owner decision boundary, even if earlier versions of the diff were
  approved.
- Operator helper tests must exercise collector -> gate with real-shaped
  snapshots, absent fields, false booleans and refusal-before-mutation. Syntax
  checks alone did not catch the v2 missing-field bug.

## Immediate next safe actions

1. Không rollout lại #466. Đọc fresh health/active work/quota và exact stored
   lease/orchestration trước một planning request; giữ nguyên historical owner.
2. Prevalidate request và draft bảy WorkOrders bằng schemas/validator đang chạy,
   source allowlist, risk/profile, dependencies, budgets và visual contracts.
   Canonical POST /v1/intake phải supervised/bounded_direct=false; không có
   direct job hoặc client-controlled execution bypass. Nếu request/response
   bất định thì giữ attempt evidence, không gửi lặp để đoán.
3. Fresh plan chỉ để PM review tại generation-1 supervised_hold, active/held,
   đúng 7 pending WorkOrders, mọi job_id null và chỉ AP-MVP-01 ready. Structural
   PASS không thay review objective/scope/AC/constraints/provider/fixtures.
4. Chỉ sau PM approval mới reconcile historical/rejected plans bằng supported
   supersession API với exact mapping; PILOT-01 retire không replacement vì
   product đã merge. Failed attempts không có orchestration chỉ giữ evidence.
5. Trước xử lý lease phải review supported lifecycle và side effects: cancel
   có thể restore direct worktree về base. Không coi việc bảo toàn qua restart
   là quyền cancel/clear lease hay checkout Chợ Nhạc. Không sửa SQL/history.
6. Chỉ sau reconciliation và lease gate hợp lệ mới release exact generation 1
   cho AP-MVP-01; các WO sau giữ supervised checkpoints. Không mở recruitment,
   Reviews, Availability salvage, payment, staging/production seed/deployment.
