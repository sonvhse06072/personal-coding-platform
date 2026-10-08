# PCP #562 — Khôi phục merge gate bằng review bổ sung

> Phạm vi: WorkOrder đã `completed`, PR còn mở, CI của exact head đã PASS nhưng PM merge bị chặn vì `required_review_independence_not_satisfied`. Tài liệu này **không** cấp quyền miễn trừ review/Owner approval.

## Quyết định Owner (2026-10-08)

1. **Ưu tiên `cross_provider`** — reviewer thực sự đến từ provider không tham gia bất kỳ lượt viết code nào trong job.
2. **Fallback `same_provider_higher_tier` chỉ khi Router xác nhận không còn reviewer khác provider đủ điều kiện.** Reviewer fallback phải:
   - thuộc một provider đã tham gia viết code, nhưng **khác model ID** với **tất cả** model viết code;
   - có **tier cao hơn tuyệt đối** và **năng lực `capabilities.review` cao hơn tuyệt đối** mức cao nhất của **tất cả** model tham gia viết code, không chỉ model cuối;
   - được chọn bởi Router theo role reviewer, qua kiểm tra registry, quota, sức khỏe provider, quyền riêng tư và profile;
   - không được dùng khi cross-provider review trả về PASS/FAIL, reviewer chạy lỗi, output không hợp lệ, HTTP timeout, API không truy cập được hoặc Router trả danh tính không tin cậy.

Thứ tự tier trong model registry: `utility < balanced < strong < premium < frontier`. Hai model cùng tier không đủ để fallback, dù khác tên hoặc reasoning effort. Việc dùng cùng provider là **ngoại lệ được Owner phê duyệt có điều kiện**, không được ghi thành “cross-provider independence satisfied”.

Policy toggle: `config/routing-policy.yml → review_policy.late_review_recovery.same_provider_higher_tier_fallback_enabled`.

## Quy trình của Engineering PM

1. Gọi PM Bridge `request_diagnostics` cho `job`, `plan_progress`, `github_delivery`. Đọc **đúng** plan, WorkOrder, job, PR, commit, source, branch và checkpoint hiện tại. Không dùng snapshot handoff cũ để đoán checkpoint.
2. Đối chiếu: child job `completed`, `result.status=accepted`, `delivery_finalized=true`, CI exact-head PASS, PR mở, reviewer gốc có protocol PASS, không còn blocker khác, không thiếu Human Owner approval, không có merge audit trước đó.
3. Gửi một GitHub PM control đến **đúng issue đang mở** của dự án: `request_late_independent_review` với `schema_version:1`, `project_id`, `plan_id`, `work_order_id`, `job_id`, `source_commit`, `expected_head`, `branch`, `pr_number`, `checkpoint_id`, `checkpoint_key`. Control marker: `<!-- coding-platform:pm-control:v1 -->`.
4. Control trả `claimed` là **đã đặt claim**, **chưa phải review PASS**. Quan sát `request_diagnostics` với collector `late_review` cho kết quả `passed/failed/uncertain`, `attestation_id`, `review_mode`. Không tạo job khác, không gọi lại model, không chỉnh DB.
5. Chỉ khi `passed` và chứng thực đúng identity/độ mạnh, gửi **một** control `release_late_independent_review` có **cùng các trường danh tính** và `attestation_id`. Runtime tự kiểm lại attestation, exact head/source/diff, CI mới nhất và mọi điều kiện PM merge/Owner; sau đó mới tạo checkpoint chuyển `blocked → awaiting_merge`.
6. Merge tiếp tục qua **cơ chế PM merge sẵn có** (exact-head check, audit, xác nhận GitHub sau mutation), không merge bằng GitHub trực tiếp. Quan sát checkpoint `merged` và phụ thuộc WorkOrder mới đủ điều kiện chạy.

## Giới hạn và hành vi khi lỗi

- Nếu chưa có reviewer eligible: `no_capacity`. **Chưa tiêu hao slot model**; có thể gửi control mới để kiểm tra sức khỏe provider về sau. Không retry liên tục.
- Nếu không xác minh được model writer/tier/năng lực review: `policy_blocked`. Không nới guard hoặc tự chọn reviewer yếu hơn.
- Nếu dữ liệu staffing không tin cậy hoặc Router gặp lỗi: `staffing_error`. Không fallback dựa trên lỗi mạng hay HTTP 5xx.
- Một khi attempt đã `claimed`: **tối đa một** lượt reviewer trên exact head và checkpoint. PASS/FAIL được attest bất biến; `uncertain` không tự chạy lại. Trường hợp cần review code sau FAIL phải xử lý theo governance repair riêng, không tái sử dụng slot này.
- Attestation ghi chính xác `review_mode`. Fallback bao gồm danh sách contributor model IDs, mức tier/capability tham chiếu, tier/capability reviewer, dấu xác nhận cross-provider capacity không sẵn có và hash output. Runtime tính lại toàn bộ từ registry khi release.
- Reviewer chạy **read-only** trên bản clone cô lập trong mount workspace; không thay đổi workspace, branch, diff, job counters hay điều kiện review gốc.
- Guardian phải tính cả late-review attempt đang `claimed` vào active engineering khi đánh giá quyền rollout. Bất kỳ attempt đang chạy đều chặn rollout.
- Không tự thay đổi `review_policy.independence_satisfied` của route cũ; không dùng `review_repair`, `resume_same_job`, SQL hoặc reset counter để vượt merge gate.

**Acceptance trước rollout:** CI của đúng PR head PASS; regression suite bao gồm cross-provider ưu tiên, fallback khi cross không eligible, reviewer tier/capability cao hơn, router lỗi không fallback, chống double-claim/replay, forged provider, stale commit/checkpoint/CI, protected owner decision, và rollback/cancellation fail-closed.
