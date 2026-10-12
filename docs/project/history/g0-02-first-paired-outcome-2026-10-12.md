# G0-02 / G0D-T01 — Cặp Drupal đầu tiên và khoảng trống full PCP

**Đối chiếu:** 2026-10-12 (ICT). **Loại:** Tier-3 outcome và incident evidence; không phải thay đổi Constitution/ProjectBaseline, quyền Runtime hay quyết định đầu tư của Owner.
**Nguồn:** [PCP #595](https://github.com/sonvhse06072/personal-coding-platform/issues/595), [fixture #2](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/issues/2), hai PR/CI, Owner WSL logs đã ghi trên issues.

## Phạm vi thực tế

**G0D-T01**: chuẩn hóa chuỗi ASCII U+0020, tab, CR và LF bên trong EventLabelNormalizer, giữ trim và NBSP. Hai arm dùng cùng immutable seed **39ef13c25b24c4a1b43a720ae53419f479996ed2**, Codex CLI **0.160.0**, model **gpt-6-luna**, effort **medium**, giới hạn cùng ba file PHP, cùng workflow GitHub-hosted validation blob **30e1202a37a7e57cd29e10dad8d5a2dd06f35cd8**. Hai workspace và CODEX_HOME khác nhau. Không dùng host Codex global, DDEV local, browser/preview, Chợ Nhạc hay legacy PCP.

**PCP arm là đường G0FixtureExecution rút gọn:** chỉ một G0 Runtime job chạy CodexAdapter và tạo commit scoped. Startup mode g0_fixture_run đi vòng qua normal RuntimeEngine, Router staffing, Planner/PlanOrchestrator, Verifier/repair pipeline, automatic GitHub delivery, notification/dashboard. **Vì thế không phải benchmark end-to-end PCP sản phẩm.**

## Evidence matrix

| Bằng chứng | PCP G0 fixture-only | Codex Direct |
| --- | --- | --- |
| Original coding | Job d361d1d9b4d54858bbbe6939fcf0cba9: execute PASS; một CLI invocation; local commit d7ff88183e2ccea298f5eadded7ae84f7d88c7c5 | Một CLI coding invocation; original wrapper **STOP: g0_direct_coding_wrapper_timeout_no_retry**; journal execute_claimed; **không có local commit** |
| Model-layer completion | Runtime trả PASS | Forensic read-only PASS: một session 82 events, exact prompt/CLI/model/effort, một task_complete, token_count, không abort |
| Worktree provenance | Ba original Git blob hashes khớp byte-for-byte | Ba original tracked PHP blob hashes khớp byte-for-byte, không extra/untracked files; git diff --check PASS |
| PR OPEN, unmerged | [#4](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/4), delivery HEAD b511aea5abc82cf3e8f9a12acc349d10899b919c | [#5](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/5), delivery HEAD 4ae6097ec42d06b40221ded247c2f255cac85b81 |
| Hosted exact-HEAD CI | [38162674835](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/actions/runs/38162674835): SUCCESS; Composer/lock, lint, Drupal PHPCS; Unit 4 tests/4 assertions; Kernel 1 test/4 assertions | [38194627127](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/actions/runs/38194627127): SUCCESS cùng chuẩn; Unit 4 tests/4 assertions; Kernel 3 tests/4 assertions |
| PM exact-HEAD review | 0 blocking source findings | 0 blocking source findings, cả sau CI |
| Hosted delivery | PM qua GitHub connector, không phải PCP automated delivery | PM qua connector **sau** forensic; commit GitHub được tạo từ 3 blobs gốc, không phải local Codex commit |
| Cảnh báo CI | Một deprecation baseline; không có test fail/skip | Một deprecation baseline; không có test fail/skip |

**Direct exact blob SHAs:** normalizer **008a0958aa7805570f4f57ba0bdca33314acfbae**, Unit **8fcfb82504b75a9bee51e91662d2ac359821c0d4**, Kernel **4d459f6146e6f7a2c0d9bc1bc797a6d4c05cb10e**.

Cả hai permanent benchmark base refs vẫn ở seed ban đầu; hai PR vẫn OPEN. Original timeout/journal/Workspace **không bị sửa lại**.

## Kết luận đo lường — không phóng đại kết quả

- **1 code-valid paired output** (cả hai có hosted CI + PM source review).
- **0 clean unattended end-to-end paired successes** (Direct timeout và manual recovery; cả hai cần PM connector delivery). Wrapper FAILED_TIMEOUT vẫn là thất bại vận hành dù original model-layer output đã hoàn thành.
- **1 Codex CLI coding invocation attempted trên mỗi arm**; model API request count, token consumption, provider cost, human-intervention count và total approved→accepted elapsed **chưa đủ provenance để định lượng**: phải là null, không suy ra từ CLI invocation hay thời lượng GitHub CI.
- Wrapper Direct cấu hình timeout **1860 giây**, không đồng nghĩa đo được end-to-end task-cycle hoặc chất lượng model thấp.
- [Protocol G0-02](g0-02-benchmark-protocol-2026-10-10.md): p50 cần ít nhất **3** comparable accepted pairs, p90 ít nhất **10** pairs và nhiều task classes. **p50=null, p90=null**; không được báo đã đạt ngưỡng 1,25x/1,5x.
- **G0 investment gate: HOLD / NOT GO, insufficient representative evidence.** Đây là đánh giá PM, **chưa phải** quyết định Owner cấp quyền G1.

## Khoảng trống sản phẩm và nguyên nhân theo source

1. **Pipeline:** services/runtime/app/main.py trong mode g0_fixture_run không khởi chạy engine.start, plan_orchestrator.start và publisher. G0 chỉ dùng CodexAdapter + fixture-only storage/workspace.
2. **Normal Runtime có side effects:** services/runtime/app/engine_core.py RuntimeEngineCore.start khởi tạo/mutate DB, cancel_all_antigravity_runs, replay queued jobs, interrupt in-flight và reconcile leases. services/runtime/app/orchestrator_notifications.py PlanOrchestrator.start đảm bảo controls và gọi core start/tick. Đã có **lịch sử** legacy PCP DB ghi active lease/orchestrations/pending WorkOrders; **không** mở normal mode trên legacy DB, không suy ra live hiện tại từ snapshot cũ.
3. **Verification:** G0 Executor allowlist hiện chỉ bật Git-only workspace creation; generic DDEV phase/preview bị từ chối. Normal engine verification cần project-owned phase evidence từ Executor. Bật normal startup hoặc sửa dashboard **không tự tạo được full-path test hợp lệ**.
4. **Delivery/owner attention:** G0 GitHub delivery flag OFF; PM connector hỗ trợ code PRs nhưng không kiểm thử Runtime privileged delivery, PM merge/reconciliation, progress/Owner attention.
5. **Wrapper reliability:** một task_complete trong Codex session và một clean host CLI/process exit là hai bằng chứng khác nhau; manual recovery phải tính là intervention, không được sửa nhãn.

## PM — bước tiếp theo trong canonical #595

**G0-02/F1 — source-only full-path feasibility map, không thêm model call:**
- Map hai đường real PCP: direct-ticket fast path và plan→WorkOrder path qua Router, RuntimeEngine, verification, review, GitHub PR/CI, PM transition. Ghi gate, dependency và negative test khả thi trên fixture; phân biệt source hiện có và feature G1 mới.
- Phân loại tối thiểu: startup/replay & host Antigravity side effects, single-writer DB/workspace ownership, Router/provider quota, Git-only vs deterministic verifier, privileged delivery, full telemetry. Không dựng thêm bộ recovery operator G0D-T01.
- Sau F1, **nếu** khả thi, đưa ra protected proposal F2: một **namespace/DB/workspace mới** không chứa lịch sử PCP hay G0D-T01 job, fixture-only registry, không socket Docker host, fail-closed startup, xác minh verifier/CI/PM đường thật, rollback. Không copy/migrate legacy DB. No model/activation/credential changes khi chưa được Owner duyệt.
- F3 chỉ sau Owner riêng phê duyệt: task fixture **mới**, không replay G0D-T01, hai arm độc lập, same model/CLI/effort/QA, đo đầy đủ approved→accepted, recovery, Owner attention, quota/usage. Nếu full pipeline chỉ chạy được khi phá trust boundary hoặc nhân bản một PCP song song, đề xuất **No-Go/giảm scope** thay vì ngụy trang một smoke test thành benchmark.
- Gate G1 #596 và G2/G3 **chưa mở** chỉ nhờ code CI-green. Hai PR #4/#5 giữ OPEN với benchmark bases frozen, không tự merge/reset/retry provider.

**Bài học T3:** model completion, code validity, wrapper/process exit, unattended delivery và throughput/ROI là **năm trục tách biệt**. Lặp thêm phép thử code-only không giải quyết câu hỏi giá trị cốt lõi của PCP.

## References

- [PCP G0-02 #595 — final paired evidence](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6116517408).
- [Fixture #2](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/issues/2), [PCP PR #4](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/4), [Direct PR #5](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/5).
- [Direct forensic PR #654](https://github.com/sonvhse06072/personal-coding-platform/pull/654) and [Owner reconciliation evidence](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6116364328).
- [Program #593](https://github.com/sonvhse06072/personal-coding-platform/issues/593), [approved G0 protocol](g0-02-benchmark-protocol-2026-10-10.md).
