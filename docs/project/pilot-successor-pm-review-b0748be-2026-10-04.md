# Chợ Nhạc — PM review successor pm-b0748be

Status: **APPROVE_PLAN_FOR_RECONCILIATION_NOT_RELEASE**.
Phạm vi: phê duyệt nội dung kế hoạch, không phê duyệt trước implementation diff,
không release WorkOrder, không đổi ProjectBaseline hoặc cấp quyền cancel/clear lease.

## Evidence và định danh

- Owner `--collect` snapshot: `2026-10-04T15:37:35.921136+00:00`
  (22:37:35 ngày 04/10/2026, UTC+07).
- Plan: `pm-b0748be27f8446a0813c2d1fe7d697fd`.
- Baseline: `pilot-v1-2026-10-04-dec033-r3`.
- Source: `aa8e68dd9aea6740de446151eb97615931de9b40`.
- Parent ticket: `GH-63`; initiative: `GH-63-PILOT-V1`.
- PM acceptance được ghi ở Chợ Nhạc #63 comment `5981710459`.
- SHA256 của trường `plan_review.plan` trong collect JSON:
  `f667ffe9d27fc3824f550089cf09269b0cfa7ccc58654d8c9e8a30e91ac7ab7d`.
  Cách mã hóa: JSON UTF-8, ensure_ascii=false, sort_keys=true,
  separators=(',',':'). Đây là snapshot-plan digest, không phải raw DB digest.

Đã đối chiếu toàn bộ 7 WorkOrder / 42 acceptance criteria với draft đã review
trong operator intake pack và `pilot-successor-review-2026-10-04.md`, cùng
#48/#49/#56/#57/#58/#50/#59 và DEC-033. Các WorkOrder fields khớp sau khi
normalize duy nhất `source_references.section` từ absent thành null.
Plan summary là lời diễn đạt của planner, không thay authority hoặc tăng scope.

## Kết quả review nội dung

| Issue | WorkOrder | AC | File working target | Risk / max_profile | Kết quả |
|---|---|---:|---:|---|---|
| #48 | AP-MVP-01-artist-profile-data-curation | 5 | 45 | high / complex | Đạt |
| #49 | AP-MVP-02-artist-profile-public-experience | 6 | 55 | high / complex | Đạt |
| #56 | EE-0-01-event-backend-domain-api-access | 8 | 90 | critical / critical | Đạt |
| #57 | EE-0-02-public-event-discovery-detail | 6 | 55 | high / complex | Đạt |
| #58 | EE-0-03-studio-event-management-participation-program | 6 | 65 | high / complex | Đạt |
| #50 | AP-MVP-03-generalized-verified-performance | 5 | 45 | high / complex | Đạt |
| #59 | EE-0-04-event-engagement-analytics | 6 | 35 | critical / critical | Đạt |

Tất cả role developer, budget adaptive; IDs/risk flags đúng contract; mỗi WO
sau phụ thuộc đúng WO liền trước. Không tạo operator/cleanup/WO thứ tám hoặc
làm lại PILOT-01. Các giá trị 8 model calls / 2 repairs / 25 minutes vẫn được
diễn giải theo adaptive policy hiện hành, không reset counters hoặc ép provider.

Review không chỉ kiểm tra schema:
- #48 giữ slug/migration/freeze, 5 themes, type-specific portfolio invariants,
  usable Drupal Media upload và existing lifecycle/current-email/privacy.
- #49 giữ portfolio-first/SEO/OG, hide-empty, conditional CTA, 6 viewports,
  lazy media và accessibility; không cần public recruitment để có giá trị.
- #56 giữ Event độc lập, PostgreSQL persisted/API/security tests, UUID,
  publication readiness, confirmation/reconfirmation và terminal archives.
- #57/#58 giữ backend authority, PUBLIC/UNLISTED/PRIVATE, canonical participation
  routes, Program keyboard reorder, external ticket metadata và no force-confirm.
- #50 chỉ EventParticipation live provider; không Booking provider/query/live
  contribution. Profile boot được khi concrete providers vắng; max 6, cache,
  provenance, hide-empty và frontend_quality trước visual_quality.
- #59 chỉ 3 fixed counters, aggregate-only, no Audience identity, rate-limit
  trước increment, 204/429/422 và non-blocking real Studio metrics.
- Cả 5 WO giao diện đều có frontend_quality -> visual_quality; concrete routes
  không template. Fixture ownership/real domain services/local-only/purge được
  giữ; fixture existence/renderability vẫn phải chứng minh khi implementation.

Independent review, permissions/security tests và PM exact-diff/CI gates của
baseline vẫn áp dụng. Kế hoạch được chấp nhận không đồng nghĩa đã có code, đã
render fixture, đã review ảnh hoặc được phép vượt protected decision boundary.

## Supervision tại snapshot

- status supervised_hold; lifecycle active; execution_mode supervised.
- generation 1; supervision_state held; checkpoint id 45.
- checkpoint key: `plan:supervision-initial:pm-b0748be27f8446a0813c2d1fe7d697fd`.
- ready set: chỉ `AP-MVP-01-artist-profile-data-curation`.
- đúng 7 rows pending/active/agent, sequence 0..6, mọi job_id null.
- Continuation identity đã được kiểm tra hash tự nhất quán theo source helper;
  chưa sử dụng để gọi `/continue`. Phải đọc lại live trước thao tác về sau.
- collect `post_attempted=false`, result COLLECTED_NO_WRITE; Git trước/sau giữ
  PCP e7fb6d3 và Chợ Nhạc historical branch/head sạch.

Usage của planning trước được lưu: 1 model call, input_tokens 32740,
output_tokens 7766, gross_input_tokens 113892, cached_input_tokens 81152.
Các candidate bị quota/reserve loại vẫn bị loại; đây không phải fresh quota
snapshot cho một model call khác. Không cần gọi planner lần nữa.

## Reconciliation còn thiếu evidence

Bản collect chỉ trả đầy đủ candidate, không trả fresh definitions/state của:
- historical `pm-5cd9ec06f74b4feba4db5a1507ab35f0`;
- rejected `pm-095d6aea0fe94901bbf692fa7d113fc2`;
- rejected `pm-a72e960c0f3b458897831cff3fb51a30`;
- rejected `pm-ac6a52e6019947adab8744a7ada72011`.

Bước tiếp theo là inventory chỉ đọc đúng 5 plans và historical job/lease.
Phải đối chiếu source definitions, không map chỉ bằng sequence/name. Mapping
trong #63 là ý định semantic; exact stored WorkOrder identity phải được review.
PILOT-01 đã merge thì retire không replacement, không đổi job thành completed.

Source `PlanOrchestratorStore.supersede_work_order` tại PCP main
`05341ecfffe5105e9221f7e2f5dd46c382339005`:
- đổi lifecycle/attention eligibility; không đổi state/job/result/progress/
  workspace/counters và không release project lease;
- sau mỗi nguồn được retire, status plan còn lại được tính lại; vì vậy cần
  duy trì blocker/hold trong mọi bước trung gian, không chỉ kiểm tra trạng thái
  cuối. Không retire blocker đầu tiên rồi để pending historical jobs launch;
- từng supersession có transaction riêng, không phải all-plan atomic batch;
  retry chỉ idempotent khi exact replacement/reason khớp.

Sau fresh inventory và exact mapping review mới chuẩn bị supported supersession.
Lease vẫn là bước riêng: cancel có thể restore direct worktree về base; chưa
được phép cancel/cleanup/checkout để giải phóng ownership. Không sửa SQL/history,
không resume/restart/replan. Chỉ release AP-MVP-01 sau reconciliation và lease
lifecycle đã được chấp nhận riêng.
