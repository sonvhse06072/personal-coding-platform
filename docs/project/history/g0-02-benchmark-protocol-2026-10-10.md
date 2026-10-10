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

## 7. Fixture selection outcome & proposed bounded pilot (2026-10-10)

**Source:** Owner chạy một lần preflight Git/DDEV/Codex chỉ đọc, báo trong hội thoại 2026-10-10; chưa có thao tác sửa source hay khởi động fixture nào từ kết quả đó.

### 7.1 Grounded candidate matrix

| Candidate | Git / version / dấu hiệu thực tế | Phân loại quyết định |
| --- | --- | --- |
| PCP platform | local `main@d53fbb0` clean; GitHub `main@a5b0c617db9fb0cff261855d1aaaa4cb37a6f7c1` mới hơn | Repo source phải được đồng bộ ff-only có gate riêng khi chạy benchmark tool; **không có local rollout** |
| Codex CLI | WSL host **0.162.0**; chạy **trong coding-runtime 0.160.0** | **Mismatch đã xác minh thực tế.** Không đổi host global, Runtime pin, credentials hoặc lách báo cáo; normalized A/B phải cùng binary, as-operated chỉ mô tả thực trạng riêng |
| `riebedebie` | Git `fun-pass@f8c48656144d`, dirty=0; composer `drupal/core:^10`, `installed_core=false`, DDEV `drupal10` stopped | Có thể *tham khảo source contract*, **không** lấy làm fixture có thể thực thi ngay; cần Composer install, chưa rõ dữ liệu/giấy phép/quyền clone |
| `environmentaljobs` | `prod@b9c49c1911ee`, dirty=5, Drupal Core installed, Drupal 10.6.14 | Không dùng checkout đang dirty hoặc DB hiện có |
| `ipropaganda` | `main@b005c2bd86ce`, dirty=254, Drupal Core installed, Drupal 10.6.14 | Không dùng |
| `KCCI` | `main@ef9c0fe3c422`, dirty=82, composer Drupal 11.3.2, installed Core not observed | Không dùng |
| `academic_management`, `cck`, `lovenote` | not_git_root; DDEV registry riêng | Không coi là source-root hợp lệ để clone |
| `pcp-validation-fixture` | local clean `main@6395655ec311`, PHP 8.3 / `type: php`, không có Composer Drupal Core; GitHub task #7 đã complete | Chỉ historical/smoke, không tính Drupal A/B, không replay task hoặc tự đổi approved baseline |
| Chợ Nhạc / PCP `cp-*` | Chợ Nhạc DDEV active; nhiều workspace PCP stopped/paused, GH-89 direct writer/lease cũ chưa được retire | **No touch** cả source, DB, workspace và lease |

**Kết luận:** Không có candidate nào đồng thời có (a) framework thực được chứng minh, (b) clean + độc lập, (c) quyền sử dụng data/repo/DB, (d) môi trường thực thi phù hợp. Một Git worktree `dirty=0` không chứng minh không chứa dữ liệu nhạy cảm hoặc đã được cấp quyền thành fixture.

### 7.2 Quyết định thiết kế đề xuất (PENDING OWNER, chưa triển khai)

**Chọn tạo hai fixture nhỏ từ starter chính thống, không sao chép code/data từ các dự án trên máy.** Phần tạo fixture là *bước chuẩn bị vận hành G0*, không bật quyền `trusted_project` và không làm thay #596 security ChangeProposal.

**F-DRUPAL:** từ `drupal/recommended-project` chính thống trên release Drupal 11 stable được pin rõ ở Composer lock; DDEV unique project name, PHP 8.4, database mới rỗng. Đặt một custom module riêng nhỏ với Unit/Kernel PHPUnit, PHPCS và check PHP syntax bắt buộc, có workflow CI tương đương hai arm. Tạo nhiệm vụ đổi validation đơn giản nhưng có acceptance kiểm chứng được; không require Event/Artist/Chợ Nhạc domain. Đây là Drupal thật, khác `pcp-validation-fixture` PHP smoke. Official: https://www.drupal.org/docs/develop/using-composer/starting-a-site-using-drupal-composer-project-templates .

**F-NEXT:** từ `create-next-app` chính thức (TypeScript + App Router) với CLI/package lock và Node 24 pinned, không gọi API bên ngoài; 1 trang sample tự tạo, Unicode/Vietnamese typography, tương tác trạng thái, responsive 390/768/1440, keyboard accessibility, Playwright Chromium, screenshot/console evidence và build/lint/TypeScript tests. Không dùng screenshots/artist media/copy từ Chợ Nhạc. Official: https://nextjs.org/docs/app/getting-started/installation .

**F-REPAIR:** lỗi deterministic có seed công khai trong một trong hai fixture mới, reproduction test fail trước khi sửa và PASS sau sửa. Không làm hỏng dự án thật hoặc khôi phục job/branch cũ.

**Isolated pairing contract:** mỗi task có **một baseline Git SHA + acceptance hash**; tạo **hai bản clone, DDEV names, working directories và databases độc lập** trước khi giao tác vụ. Hai arm chạy cùng mức chất lượng/CI/review và task scope, không trộn thay đổi giữa hai arm. Nếu PCP tự merge làm thay đổi base trước arm còn lại, dùng hai nguồn delivery tách biệt có cùng Git ancestry hoặc dừng ghi nhận accepted-pair (không giả vờ comparable). Log đầy đủ failed/aborted attempts và Owner interventions.

### 7.3 Hai lớp đo, không trộn số liệu

- **Normalized / controlled:** cùng exact Codex CLI version, model ID, reasoning effort, verified toolchain version, task/source/acceptance và review/CI policy; chỉ lớp này đủ điều kiện cho phép tính percentile theo script `pcp-parity-benchmark.py`. Giữ host global `0.162.0` và runtime `0.160.0` nguyên trạng; thử nghiệm chỉ chạy khi có cách gọi phiên bản `0.160.0` **riêng biệt, đã kiểm chứng** cho direct arm mà không thay host toàn cục. Không dùng pin trong file thay cho binary proof.
- **As-operated / operational:** host `0.162.0` so với PCP `0.160.0` phản ánh **chi phí thực của lifecycle/version lag**. Thu riêng status, lỗi, thời gian/owner-wait/cost, kèm nhãn `noncomparable_cli_version`; tuyệt đối không gộp vào controlled p50/p90 hoặc tự đổi version để kết quả đẹp. Đây cũng là tín hiệu đầu vào cho #606/#607 về sau.

**Pilot gate nhỏ trước khi scale:** tối đa một cặp cho Drupal, một cặp frontend và một cặp repair sau khi fixture/data/authority/CLI proof hợp lệ. Nếu một arm không đạt required QA, báo *failure/insufficient evidence*, phân tích một lần có giới hạn; không chạy mù 10 lần để tạo percentile. Chỉ mở cohort lớn hơn nếu vận hành và accepted-quality đã chứng minh khả thi. G0 không đòi 10 accepted pairs bằng mọi giá trước khi nhận ra một lỗi nền tảng đã có bằng chứng.

### 7.4 Protected decision / external capability boundary

`config/projects.yml`, `config/project-baselines.yml`, `config/pm-bridge.yml` là protected governance paths. Việc đăng ký project mới hoặc cấp remote dispatch/lease cho fixture phải có **Owner approval có scope cụ thể, PR, exact-head CI/review**, giữ immutable baseline. Không dùng issue comment làm authorization. Cấm tự thêm Guardian action, root/Docker socket vào developer, thay Production/Chợ Nhạc hay cấp quyền host Codex trước #596 riêng.

**Owner decision cần riêng:** cho phép tạo hai repository/directory benchmark **non-production, empty data** từ hai starter chính thống; xác nhận phương thức PCP registration tối thiểu và giới hạn model/CI/quota cho tối đa ba cặp pilot. Đây **không** phải phê duyệt thay Constitution, trusted dev permissions, rollout production hoặc bỏ required PR gates. Nếu chưa được duyệt, chỉ được chuẩn bị spec/logic và tiếp tục dùng bằng chứng read-only.

**Next executable checkpoint after approval:** dựng fixture, commit exact sources/locks, test deterministic baseline, xác minh DB/workspace isolation rồi đối chiếu trên PCP local đang clean/healthy. Không tự gọi `/v1/intake`, restart/rollout PCP hay chạm dự án Owner trong giai đoạn proposal.

### 7.5 Evidence rules / stop criteria

- G0 measured `accepted outcome` phải có PR identity, exact head/base, CI, quality/review/visual proof, source/model/effort/CLI, timestamps và evidence link cho cả hai arm; template scaffold success không phải accepted engineering WorkOrder.
- No-Go hoặc `insufficient_evidence` nếu owner approval thiếu, fixture registration không hợp lệ, nguồn/DB chưa cô lập, version mismatch chưa giải quyết, review/CI không tương đương, không có accepted pairs hoặc xuất hiện duplicate/retry bất thường.
- Chỉ chuyển #595 sang DONE khi có report bao gồm các khoảng bất định, so sánh effort/maintenance và G0 Owner investment decision; G1 vẫn đòi một ChangeProposal trust riêng.
