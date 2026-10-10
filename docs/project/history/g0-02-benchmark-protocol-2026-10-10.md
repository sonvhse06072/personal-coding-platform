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
| Identity | `trial_id`, `task_id`, `task_type` = `drupal/frontend/repair` hoặc `php` (PHP smoke, **không** tính vào cohort Drupal), `arm` = `direct/pcp` |
| Comparability | `source_sha` (Git commit 40hex), `acceptance_sha256` (64hex), `environment_id`, `environment_class` = `isolated_fixture/historical_record`, `model_id`, `reasoning_effort`, `verification_policy`, `review_policy` |
| Controlled proof (tùy chọn khi nhập bản ghi lịch sử, **bắt buộc để tính A/B**) | `codex_cli_version` (phiên bản quan sát thực, dạng `0.162.0`), `toolchain_id` (mã profile gồm DDEV/PHP/Node/browser/OS), `workspace_id` (mã định danh opaque, **khác nhau** ở hai arm, không chứa đường dẫn máy) |
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

Script ghép hai nhánh bằng `trial_id`, so sánh toàn bộ comparability fields, loại khỏi **latency cohort** khi thiếu nhánh, khác model/criteria/environment/policy hoặc một arm chưa accepted; **vẫn công khai các excluded trials và toàn bộ failed/aborted attempts**. Bản ghi `historical_record` là bằng chứng tham khảo, **không** phải phép thử A/B có đối chứng; case `php` chỉ dùng smoke test, **không** thay Drupal thật. Hai arm chỉ được tính A/B khi đã **quan sát đúng phiên bản Codex CLI** từ `codex --version` trên host/Runtime, trùng `toolchain_id` và có **hai `workspace_id` khác nhau**. Thiếu một trong ba hoặc mismatch sẽ trả `excluded_trials`/insufficient evidence, không tự suy ra phiên bản đã cài từ pin. Opaque `workspace_id`/`toolchain_id` do operator khai báo chỉ là dấu vết đối chiếu; cần nguồn read-only xác thực workspace/DB isolation riêng trước Human G0 Go. Duplicate identity, invalid timestamps, SHA, final QA, schema fields đều bị từ chối.

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

## 5. Readiness audit hiện tại (2026-10-10)

- [PCP Guardian read-only](https://github.com/sonvhse06072/personal-coding-platform/issues/524#issuecomment-6094166352) xác nhận Runtime 1.0.141, Executor 1.0.35, Router 1.0.31, n8n/Antigravity healthy và 0 active job tại thời điểm chụp; local PCP clean `d53fbb0` nhưng GitHub main `f5913448`. **Không có rollout/fast-forward đã thực thi trong G0.**
- [Validation fixture](https://github.com/sonvhse06072/pcp-validation-fixture) là PHP 8.3 generic với bề mặt **Drupal-style**, không có Drupal Kernel/Core integration. Task đã được phê duyệt riêng [#7](https://github.com/sonvhse06072/pcp-validation-fixture/issues/7) **đã đóng**, [PR #9](https://github.com/sonvhse06072/pcp-validation-fixture/pull/9) đã merge `3ecd9ce66260245089efe2533080d1b5191b810c`; không replay hoặc mở rộng ProjectBaseline chỉ để tạo benchmark số đẹp.
- [PCP R3 fixture audit](https://github.com/sonvhse06072/personal-coding-platform/issues/162#issuecomment-5702384513) chứa một **PCP-only** kết quả thật: first pass, targeted/style/static/full/CI success, 0 repair/retry/owner intervention. Không có cặp direct Codex độc lập cùng điều kiện; do đó **không** đi vào percentile A/B.
- [Chợ Nhạc GH-89](https://github.com/sonvhse06072/chonhac/issues/89) là PCP blocked rồi handoff sang Codex-direct trên **cùng dirty workspace**, không phải hai nhánh thí nghiệm độc lập. Bằng chứng hữu ích để phân tích blocker/cost nhưng không ghép thành một A/B trial. Workspace Codex hiện hữu và PCP lease cũ không bị đụng tới.
- Config PCP có `example-drupal` và `pcp-validation-fixture`; chưa có bằng chứng local `example-drupal` có đủ repo/dataset/lease sạch; chưa có benchmark Next.js fixture đăng ký. Không được tự lấy `chonhac` active writer làm Next fixture.

**G0 disposition:** hiện có 0 cặp Drupal/frontend/repair được kiểm chứng tương đương; báo cáo phải là `insufficient_evidence`, chưa G0 Go. Trước khi đo thực nghiệm cần hai checkout/database disposable độc lập, chính sách model/effort/CLI/verification/review giống nhau, mục tiêu acceptance từ ticket đã duyệt, framework Drupal thật được xác minh và browser evidence cho frontend. Không thêm production/privileged workflow hoặc bypass ProjectBaseline. Việc tạo/cấp quyền fixture mới là một quyết định vận hành được kiểm tra riêng; không được ngụy trang thành cập nhật số đo.

## 6. Environment discrepancy / operator check (2026-10-10)

Owner WSL read-only preflight: local PCP clean `main@d53fbb07524bb3ca13324e2ed7edac1513367072`; GitHub `main@8aa1d47ef55132aac20948294d2fef75e1945d18` đi trước **21 commit, không behind** (diff docs/Context Composer/benchmark scripts+tests, **không có Router/Runtime/Executor/Guardian source diff**). Installed host `codex --version` trả `codex-cli 0.162.0`, trong khi `config/tool-versions.env` pin `CODEX_VERSION=0.160.0`. **Đây là candidate CLI mismatch, chưa xác minh version binary thực sự trong Runtime**. Không tự downgrade host, không tự nâng runtime pin hoặc gọi GitHub merge là local rollout.

`example-drupal` không có Git checkout. `pcp-validation-fixture` tại local `6395655ec...`, đúng nguồn approved baseline lịch sử trước khi task #7 đã merge vào fixture GitHub; không reuse fixture làm task mới hay Drupal thật. DDEV liệt kê các dự án Drupal 10/11 đang stopped (KCCI, academic-management, cck, environmentaljobs, ipropaganda, lovenote, riebedebie) nhưng **đó là workspace/dữ liệu ứng dụng của Owner, chỉ được quan sát read-only**; Chợ Nhạc đang active, PCP historical cp-* workspace stopped/paused. Không restart/clone private data/DB khi chưa được phép.

**Next bounded read-only proof:** chạy `ddev exec -s coding-runtime codex --version` trong PCP directory để xác minh binary đang được dùng; chỉ đọc branch/HEAD/dirty-count và `composer.json` Drupal core requirements của candidate repositories, không dump secrets. Nếu Runtime version khác host, giữ kết quả ở lớp `noncomparable` hoặc dùng hai binary version giống nhau trong các môi trường cô lập sau khi xác minh; tuyệt đối không thay provider/credentials hoặc áp dụng full-access để làm đẹp số.

**Protected registration:** `config/projects.yml` và `config/project-baselines.yml` là đường dẫn được bảo vệ bởi `scripts/check_project_doc_authority.py`; tạo Drupal/Next fixture mới cần approval + PR/CI theo thẩm quyền. Chưa có kênh PM Bridge được phép dispatch remote các fixture ngoài Chợ Nhạc. Không gọi `/v1/intake` khi không có fixture/baseline đã duyệt.
