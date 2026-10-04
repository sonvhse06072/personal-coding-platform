# Current Project State and Handoff

Status: Tier-1 mutable working-state snapshot. Repository policy/code/tests and
live Runtime/GitHub evidence remain authoritative over chat history. Completed
chronology belongs in Tier-3 history, not here.

Last updated: 2026-10-04 sau khi merge PCP #466 / PR #468; source main
Runtime 1.0.106 đã xanh CI, local vẫn cần rollout/acceptance riêng.

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
  WorkOrder/PM proposal validators vẫn strict. Local activation chưa được suy từ
  GitHub merge; snapshot gần nhất của owner vẫn là Runtime `1.0.105`.
- PCP #463 đã hoàn thành qua PR #464, merge commit
  `0706cd119ebf2dcac9481b28799e5d835b2518ff`; Runtime trong source là
  `1.0.105`, ddev-executor vẫn `1.0.31`. Exact PR head
  `ecda44f5138a3c1d3817e5b2d9bc49ded20b4b97` có workflow `tests`
  run `37159249321` PASS ở cả Router, Runtime, ddev-executor và structure tests.
- PM prompt đã có `AUTHORIZED_SOURCE_REFERENCE_PATHS`, sort/deduplicate từ
  đúng `ProjectBaseline.references`. WorkOrder và DecisionBoundary chỉ được
  cite tập này; authority-only paths không được tự nâng thành references.
  Validator fail-closed được giữ nguyên. Không triển khai lại #463.
- Owner snapshot `2026-10-04T10:58:19.945738+00:00` xác nhận Runtime
  `1.0.105` healthy, Router/executor ok, executor `1.0.31`; r3/source và
  exact sorted/deduplicated 27-path prompt allowlist PASS. Local PCP main
  `0706cd119ebf2dcac9481b28799e5d835b2518ff` clean; docs-only PR #465 đã
  merge trên GitHub tại `d73412a44dde17ea4562648182cc6a7aed8e5f1f`.
  Không cần rollout lại #464 chỉ vì local chưa có docs commit #465.
- Active engineering jobs = 0 trước/sau snapshot, không phải atomic idle/lease
  clearance. Quota snapshot giữ nguyên Codex available=true/pressure=0.16,
  Gemini true/0.99912, Claude-GPT false/1.0; freshness/reserve cần đọc mới trước
  model call. Bridge `1.13` và registry `11` là checkpoint cũ, chưa đọc lại ở
  snapshot này. HTTP 500 riêng historical plan được theo dõi ở #466 bên dưới.
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
  Sau local preflight và rà soát contract tổng thể, mới chuẩn bị một successor
  supervised plan đúng bảy phần còn lại theo Chợ Nhạc #63.
- Frontend-heavy successor WorkOrders should use
  `frontend_quality -> visual_quality` with concrete bounded routes only when
  those routes are renderable by the WorkOrder.

Historical DEC-025 and GH-42 execution are retired. Do not recreate, reroute or
resume them.

## Active PCP follow-up work

PCP #466 đã đóng completed qua PR #468; source fix ở Runtime
`1.0.106`. Owner probe trước sửa
`2026-10-04T11:11:26.098002+00:00` là evidence nguyên nhân: 7 historical
template `visual_routes` trong 4 WorkOrders làm GET plan trả 500, còn
orchestration và persisted record vẫn nguyên.

Bản sửa tách read response sang non-executable `ExecutionPlanSnapshot*` models.
Historical template routes được giữ để audit; một bản sao validation trong RAM
thay chỉ template route local an toàn bằng sentinel rồi chạy strict
`WorkOrder` validation, nên malformed data khác và parent invariants vẫn
fail-closed. Object/dict/PM-proposal replay của snapshot vẫn bị strict validator
từ chối. Exact-head CI và PM review đã PASS trước merge.

Local Runtime chưa được xác minh ở `1.0.106`; không coi source merge là rollout.
Không mutate historical record/orchestration hoặc release rejected plans trong
bước activation.

Successor attempt `pm-d2947a399ecb44de9e96d174bd4c2d48` được giữ làm evidence:
planner đã cite `docs/12-launch-metrics.md`, một authority-only path không
thuộc r3 references. Bài học: phân loại `authority` không đồng nghĩa quyền cite
trong `source_references`; sửa prompt và giữ validator fail-closed, không mở
rộng baseline theo từng output sai. `usage=null` không chứng minh model chưa
được gọi.

PCP #461/#462 is complete at Runtime `1.0.104`: new PM plans reject
`max_profile` below their risk/protected-flag floor. PCP #457/#458,
#455/#456, #453/#454 and #451/#452 are also complete.

Local plan state tại owner snapshot 10:58:19 UTC, không phải bảo đảm về sau:

- `pm-095d6aea0fe94901bbf692fa7d113fc2`,
  `pm-a72e960c0f3b458897831cff3fb51a30` và
  `pm-ac6a52e6019947adab8744a7ada72011` đều có orchestration active,
  supervised_hold, generation 1, held; mỗi plan đúng 7 pending WorkOrders,
  mọi job_id null, ready set chỉ AP-MVP-01. Không release các rejected plans.
- Historical plan `pm-5cd9ec06f74b4feba4db5a1507ab35f0` vẫn blocked,
  generation 0; PILOT-01 gắn job `c02defa348fc5b19a0bd021e2697571e`,
  PILOT-02..08 pending và chưa có job. Chợ Nhạc worktree clean trên
  `ai/c02defa348fc` tại `88dd4f60dbe95c41c6e7ce8fc5bb3c7ba8a098ba`.
- Các failed planning attempts giữ nguyên làm evidence. Không xóa plan,
  reset counters/history, sửa SQL, resume historical job hoặc tạo replacement
  chỉ để né blocker.

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
  collector/redaction PRs #65/#66.

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

## Immediate next safe actions

1. Chạy fresh local idle/lease/worktree/health gates rồi rollout PCP source main
   chứa Runtime 1.0.106; không checkout/reset/clean Chợ Nhạc và không restart
   khi còn engineering work hoặc lease không rõ.
2. Sau rollout, xác minh GET historical plan = 200, 7 template routes giữ nguyên,
   persisted record digest/history không đổi, current/new WorkOrder validation
   vẫn reject template routes, và ba rejected orchestrations vẫn held/zero jobs.
3. Giữ nguyên mọi historical/rejected/failed plan. Không gọi continue/operator/
   supersede trước khi có replacement được PM duyệt và mapping rõ ràng.
4. Trước một fresh intake, đọc live #48/#49/#56/#57/#58/#50/#59 cùng source r3
   liên quan; rà đồng thời source allowlist, acceptance, exact IDs/dependencies,
   risk/profile floors, budgets, concrete routes và fixture ownership. #50 chỉ
   triển khai EventParticipation live provider, không Booking/Marketplace
   provider hoặc Booking queries; Selected Performances phải có visual_quality.
5. Replacement phải có đúng bảy developer WorkOrders tuần tự, adaptive budget,
   execution_mode supervised. Review cả nội dung product contract, không chỉ
   JSON/status=ready. Xác minh generation-1 supervised_hold, active/held,
   đúng bảy pending WorkOrders, mọi job_id null và chỉ AP-MVP-01 ready.
6. Chỉ sau PM approval mới reconcile bằng supported supersession API với exact
   mapping; PILOT-01 retire không replacement vì product đã merge. Không đổi
   job history/counters/workspace; failed attempts không có orchestration chỉ
   giữ evidence. Kiểm tra project lease qua supported control path.
7. Sau reconciliation hợp lệ, chỉ release exact generation 1 cho AP-MVP-01;
   các WO sau tiếp tục supervised hold. Không mở scope marketplace recruitment,
   Professional Reviews, Availability salvage, payment, staging/production seed
   hoặc deployment.
