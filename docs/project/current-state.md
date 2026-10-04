# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
live Runtime/GitHub evidence remain authoritative over chat history. Completed
chronology belongs in Tier-3 history, not here.

Last updated: 2026-10-04 sau PM review owner collect 15:37:35 UTC; successor
pm-b0748be được chấp nhận về nội dung, chưa reconciliation/lease clearance/release.

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
- Rollout v3 không thu quota mới. Collect successor ghi lại staffing/usage của
  lần planning đã có (policy 19, registry 11), không phải fresh quota cho một
  model call khác. Giữ available=false/reserve policy; không ép provider.
  Bridge version chưa được đọc lại trong các output này.
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

Successor `pm-b0748be27f8446a0813c2d1fe7d697fd` đã được review toàn bộ và
**APPROVE_PLAN_FOR_RECONCILIATION_NOT_RELEASE**, ghi tại Chợ Nhạc #63 comment
`5981710459`. Không gửi intake/replan lại, giữ attempt marker và result hiện có.
Owner collect `2026-10-04T15:37:35.921136+00:00` xác nhận ready/r3, 7 developer
WorkOrders/42 AC, adaptive targets 45/55/90/55/65/45/35, exact risk flags/profile
floors, dependencies tuyến tính và concrete visual routes. Toàn bộ WorkOrder
fields khớp draft sau duy nhất normalization source_references.section=null.
#50 chỉ EventParticipation live provider và có frontend_quality/visual_quality.

Orchestration tại collect: active, supervised_hold, generation 1, held;
checkpoint 45 / `plan:supervision-initial:pm-b0748be27f8446a0813c2d1fe7d697fd`;
7 pending/active/agent rows, mọi job_id null, ready chỉ AP-MVP-01. Continuation
identity tự nhất quán; chưa sử dụng làm release. Snapshot-plan digest:
`f667ffe9d27fc3824f550089cf09269b0cfa7ccc58654d8c9e8a30e91ac7ab7d`
(JSON UTF-8 ensure_ascii=false, sort_keys=true, separators=(',',':')).

Chi tiết PM review và giới hạn:
`pilot-successor-pm-review-b0748be-2026-10-04.md`.
Contract preparation/fixture ownership:
`pilot-successor-review-2026-10-04.md`.
Hai file là execution evidence, không tự thêm vào ProjectBaseline.references.

Bước tiếp theo: read-only inventory đúng candidate + historical + 3 rejected
plans, full source definitions/state và exact job/lease. Collect hiện tại chỉ
có candidate, chưa đủ fresh mapping để chạy supersession. Source supersession
chỉ đổi orchestration lifecycle/attention, không release lease. Phải giữ blocker/
hold trong các trạng thái trung gian; không retire blocker rồi để old jobs chạy.
Không cancel/cleanup vì có thể restore direct worktree về base.

Successor attempt `pm-d2947a399ecb44de9e96d174bd4c2d48` được giữ làm evidence:
planner đã cite `docs/12-launch-metrics.md`, một authority-only path không
thuộc r3 references. Authority classification không đồng nghĩa quyền cite.
`usage=null` không chứng minh model chưa được gọi.

PCP #461/#462 is complete at Runtime `1.0.104`: new PM plans reject
`max_profile` below their risk/protected-flag floor. PCP #457/#458,
#455/#456, #453/#454 and #451/#452 are also complete.

Preserved state cần đọc mới trước reconciliation:

- `pm-095d6aea0fe94901bbf692fa7d113fc2`,
  `pm-a72e960c0f3b458897831cff3fb51a30` và
  `pm-ac6a52e6019947adab8744a7ada72011` vẫn active, supervised_hold,
  generation 1, held tại rollout v3; mỗi plan đúng 7 pending WorkOrders,
  mọi job_id null. Collect candidate không refresh ba plans này.
- Historical job `c02defa348fc5b19a0bd021e2697571e` blocked, lease active
  generation 9 là rollout snapshot, không phải fresh collect proof. Historical
  plan `pm-5cd9ec06f74b4feba4db5a1507ab35f0` blocked/generation 0 từ snapshot
  trước; cần đọc lại full definitions/orchestration trước mapping.
- Collect xác nhận PCP main `e7fb6d364f109a2ddee979d3a040367b03d87f73`
  và Chợ Nhạc `ai/c02defa348fc` tại
  `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba` sạch/không đổi trước-sau.
- Failed planning attempts giữ evidence; không xóa plan/reset counters/sửa SQL.
  Không cần model call mới để lặp lại plan đã đạt. Fresh quota chỉ cần trước
  execution/model call thật; read-only inventory không chọn provider.

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

1. Không restart/replan/POST lại. Giữ marker
   `~/.coding-platform/operator-actions/gh63-r3-after466-v1/attempt.json` và
   result của attempt `090ccdff34d544189eda9c639d484391`.
2. Thu bounded read-only inventory 5 plans, source definitions, exact candidate
   digest/hold và job/lease. Không model call, SQL write, supersession hay release.
3. Review exact mapping theo definitions. PILOT-01 retire không replacement vì
   product đã merge; PILOT-02..08 và rejected rows map về candidate đã duyệt.
   Bảo toàn state/job/counters/workspace; failed non-orchestrated attempts giữ
   evidence. Giữ blocker/hold suốt trình tự, không chỉ kiểm tra kết quả cuối.
4. Chỉ sau fresh mapping/gates mới dùng supported supersession API. Không tự
   suy supersession đã giải phóng lease; cancel có thể restore base nên phải
   review/authorize side effects riêng. Không reset/clean/checkout/sửa SQL.
5. Sau reconciliation và lease lifecycle hợp lệ mới release exact generation 1
   của AP-MVP-01; chưa có release trong phiên PM này. Mọi independent review,
   protected diff và exact-head CI gate còn nguyên cho implementation về sau.
