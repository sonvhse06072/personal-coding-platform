# G0-02 — Giao thức benchmark PCP so với Codex trực tiếp (2026-10-10)

**Class:** T3 evidence/history — phương pháp và trạng thái thu thập, không phải nguồn cấp quyền mới. **Issue:** [#595](https://github.com/sonvhse06072/personal-coding-platform/issues/595), sau audit [#594](https://github.com/sonvhse06072/personal-coding-platform/issues/594) hoàn tất.

**Trạng thái: BENCHMARK CHƯA ĐỦ DỮ LIỆU.** Công cụ và fixture kiểm thử bên dưới không phải kết quả thực nghiệm, không được coi là G0 Go hay bằng chứng PCP đạt ngưỡng p50/p90. G0 chưa cho phép cấp quyền host cho Codex, thao tác Chợ Nhạc direct workspace hoặc tự triển khai G1.

## 1. Benchmark phải đo gì

Mỗi `trial_id` là một bản thử tương đương theo hai nhánh độc lập:

1. **direct:** Codex trực tiếp trên dev environment được phép, edit/build/test/browser trong job.
2. **pcp:** PCP Runtime/Router/Developer/Verifier/PR đi qua các gate chất lượng cùng mức yêu cầu.

Cả hai phải pin **cùng task/criteria digest/source SHA, model ID/reasoning effort, environment profile, verification/review policy**. Dùng hai bản checkout/DB riêng để tránh giao thoa; kết quả CI và PM review phải cùng chuẩn, không giảm gate PCP hay direct để đẹp số. Ngày bắt đầu được tính lúc approved ticket có thể thực thi; ngày kết thúc khi accepted PR/merge đã đạt review+exact-head CI+kiểm chứng UI nếu task frontend. Không gọi riêng thời gian developer là end-to-end time.

**Cohort mục tiêu:** task Drupal domain PHPUnit/PHPCS, frontend Next/Playwright real browser/visual, và sửa bug/test failure trên fixture cô lập. Một lịch sử Chợ Nhạc GH-89 dù nhiều lần repair **không phải matched direct-vs-PCP pair**. Không tạo ticket giả hoặc chồng writer lên Chợ Nhạc. Trial thất bại, bị chặn, abort hoặc thiếu required QA phải được báo cáo riêng, không âm thầm loại để báo tốc độ đẹp.

## 2. Bản ghi có provenance bắt buộc

File JSON đầu vào chứa chính xác `schema_version=1` và `records` tối đa 500 bản ghi. Mỗi record yêu cầu:

| Nhóm | Các trường |
| --- | --- |
| Identity | `trial_id`, `task_id`, `task_type` = `drupal/frontend/repair`, `arm` = `direct/pcp` |
| Comparability | `source_sha` (Git commit 40hex), `acceptance_sha256` (64hex), `environment_id`, `environment_class` = `isolated_fixture/historical_record`, `model_id`, `reasoning_effort`, `verification_policy`, `review_policy` |
| Actual chronology | `started_at`, `ended_at` ISO-8601 có UTC offset; chỉ đo interval dương tối đa 30 ngày |
| Outcome | `outcome` = `accepted/failed/aborted`, `quality` có bool `deterministic/review/ci` và `visual` bool/null |
| Checkable evidence | `evidence_url` dạng GitHub URL đến issue/PR/run/log được quyền truy cập |

Accepted yêu cầu deterministic, review, CI đều PASS, và frontend còn cần visual PASS. Token/chi phí/tần suất được đo riêng bằng những trường **tùy chọn**: `input_tokens`, `cached_input_tokens`, `output_tokens`, `model_calls`, `tool_calls`, `test_runs`, `repair_iterations`, `owner_interventions`. Không có số liệu thì để null/không truyền, không đổi ký tự thành token hoặc tự suy ra quota. Không lưu prompt thô, credential, đường dẫn bí mật, dữ liệu artist/customer; schema từ chối unknown fields.

## 3. Công cụ phân tích — read-only, fail closed

Chạy **sau khi có bằng chứng thật** (tool không tự khởi chạy model/DDEV):

```bash
python scripts/pcp-parity-benchmark.py --input records-real.json --output parity-report.json
python -m pytest -q -p no:cacheprovider tests/test_pcp_parity_benchmark.py
```

Script ghép hai nhánh bằng `trial_id`, so sánh toàn bộ comparability fields, loại khỏi **latency cohort** khi thiếu nhánh, khác model/criteria/environment/policy hoặc một arm chưa accepted; **vẫn công khai các excluded trials và toàn bộ failed/aborted attempts**. Duplicate identity, invalid timestamps, SHA, final QA, schema fields đều bị từ chối.

- Dưới **3 accepted pairs**: không hiển thị p50 hoặc p90.
- Từ **3 đến 9 accepted pairs**: p50 mô tả; p90 giữ null, verdict `insufficient_evidence`.
- Từ **10 accepted pairs**, có cả 3 loại task: p50 là median mỗi arm; p90 là nearest-rank mỗi arm; tỷ lệ `PCP/direct`, mục tiêu hoạch định p50 **≤1.25×**, p90 **≤1.5×**. Công cụ chỉ in `metrics_available_human_g0_gate_required`, **không tự quyết định Go**.
- Số trial chưa tương đương/không thành công phải đi kèm báo cáo, thay vì gọi accepted quality đạt trên cohort tự lựa chọn.

**Test fixtures dùng số liệu tổng hợp nhân tạo, chỉ để chứng minh phép tính/abstention.** Không lấy CI unit tests hoặc case giả đó làm thực nghiệm đo PCP.

## 4. Việc còn lại / G0 investment gate

1. Chọn tối thiểu ba nhóm task có acceptance độc lập (Drupal, frontend, repair). Pin evidence và source revision của mỗi trial, hai workspace/DB tách biệt, không dùng worktree đang dirty.
2. Kiểm chứng model ID, reasoning effort, Codex/PCP CLI, DDEV, browser/Node/PHP, network và review/CI cùng mức; nếu khác thì đánh dấu `noncomparable`, không đổi nhãn cho khớp.
3. Thu thập thực tế `approved-ticket → accepted-PR`, model usage nếu provider trả về, verifier loops, owner interventions và chất lượng (bao gồm browser screenshots/visual QA).
4. Chạy reporter, báo cohort size, p50/p90 khi đủ mẫu, failure rate, biến thiếu và uncertainty. Nếu mục tiêu G1 1.25×/1.5× không chứng minh được, đề xuất No-Go/thu hẹp scope hoặc thêm mẫu; không tự nâng quyền hệ thống.
5. G0 decision phải chỉ rõ ROI, chi phí maintenance/runtime/model/quota và ChangeProposal nếu muốn thay trust boundary #596. Human Owner duyệt riêng trước G1.

**An toàn live 2026-10-10:** [Guardian 6093920625](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6093920625) có 0 active PCP engineering lúc chụp, nhưng [GH-89 diagnostic 6093934986](https://github.com/sonvhse06072/chonhac/issues/89#issuecomment-6093934986) xác nhận direct Chợ Nhạc checkout **dirty trên nhánh Codex GH-132**, PCP job GH-89 vẫn blocked/checkpoint 187. Không có quyền tự clean/stash/restart/checkout/cancel/retire lease; benchmark chỉ được chạy trên fixture độc lập được phép.

**Source:** [#593 roadmap](https://github.com/sonvhse06072/personal-coding-platform/issues/593), `docs/project/efficiency-model.md` (approved G0 performance targets), `docs/project/history/g0-01-architecture-audit-2026-10-10.md` (source/deployed gaps). Đây là protocol + audit evidence, không sửa target policy T2.
