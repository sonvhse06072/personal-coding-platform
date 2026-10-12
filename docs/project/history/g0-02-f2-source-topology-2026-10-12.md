# G0-02/F2a — Cấu hình nguồn biệt lập, PARKED và chặn kích hoạt nhầm

**Ngày:** 2026-10-12 (ICT). **Authority:** T3 evidence dưới [PCP #595](https://github.com/sonvhse06072/personal-coding-platform/issues/595); thuộc phê duyệt source/tests DEC-G0-FULLPATH-SOURCE-01 và quyền PM quyết định kỹ thuật thông thường. **Không phải** phê duyệt triển khai, tạo volume, thay quyền protected hay sử dụng quota model.

## Kết quả F2a

- **Compose candidate:** `deploy/fullpath/compose.source-only.yml`, project Compose `pcp-f2-fullpath` *không* phải legacy PCP hoặc `pcp-g0d01`. Bốn service `fullpath-db/router/executor/runtime` đều có profile không mặc định `owner-gated-f2-source` **và** entrypoint `/bin/false`. Thậm chí thao tác bật profile thủ công cũng **không** khởi chạy PostgreSQL, Router, Executor hay model; thao tác Docker có thể vẫn tạo container/volume, nên **cấm** dùng `up/run/create` cho candidate này.
- **Nguồn registry cấu hình mới:** `config/fullpath-candidate/projects.yml` chỉ chứa `pcp-g0-fullpath-fixture`; autonomy toàn `false`, DDEV off và reviewer PM off. `project-baselines.yml` có *chưa có* active revision / source commit approved. `models.yml` và `routing-policy.yml` **không có model hoặc profile được phép route**. Đây là những blockers chủ động; không tự sao chép registry/provider quota của hệ cũ.
- **Cô lập dự kiến:** PostgreSQL user/db `fullpath`, volume `pcp-f2-fullpath-postgres-data`; network `pcp-f2-fullpath-private` internal và network egress `pcp-f2-fullpath-provider` riêng (chưa có domain allowlist). Docker service image phải được cung cấp qua biến tương lai, pull never, app non-root, root FS read-only, cap_drop ALL, no-new-privileges, no published ports, no host Docker socket, no host DDEV hay host Antigravity. Workspace/source/config/auth bind chỉ có các biến `PCP_F2_*` sau bước Owner riêng cấp quyền; tất cả bind `create_host_path=false`. Runtime mới là service duy nhất thấy private CODEX_HOME. Không gắn GitHub token vào Runtime/agent; Executor chưa có token/delivery capability nên delivery **chưa khả thi**.
- **Source-only negative tests:** `scripts/g0_fullpath_topology_source.py inspect` chỉ đọc YAML; trả `status=STOP` cố định, cùng `source_topology_valid` và blockers riêng, **không** Docker/net/DB/process. `tests/test_g0_fullpath_topology_source.py` kiểm tra mount path chính xác, no ports/socket/foreign project, private networks, secret variables và không thể bật job/DDEV/autonomy qua config khác. Kết quả STOP dù source đúng là **điều bắt buộc**, không phải CI thất bại.
- **Ngăn mode-switch:** Source Runtime `parked_fullpath_environment()` nhận diện môi trường đánh dấu F2 từ project path/source/workspace/CODEX_HOME/DB ngay cả nếu biến `PCP_RUNTIME_STARTUP_MODE` bị thay thành `normal`. Middleware chặn toàn bộ HTTP (kể cả health/API PM), lifespan và cả đường trực tiếp `RuntimeEngineCore.start()` chặn trước `Storage.init`, Antigravity cancel-all, job replay hoặc `PlanOrchestrator.tick()`. Source negative tests kiểm tra cả ba đường. Không thay hành vi các dự án legacy với danh tính config thông thường.

## Điều kiện F2 vẫn CHƯA ĐƯỢC CHỨNG MINH

| Gating | Evidence phải có trước một lệnh Docker/Runtime/model |
| --- | --- |
| Fixture source mới | Repository/branch `benchmark/fullpath`, task mới, seed commit approved khác G0D-T01; không reuse hay merge hai PR fixture lịch sử |
| Baseline + registry | Approval chính xác source SHA từ Owner, file config *được mount* có chỉ một project và baseline mới, không chỉ tin file mẫu trong PCP repo |
| Ownership runtime | Các host paths mới tồn tại riêng, UID/GID quyền tối thiểu, không symlink/traversal; Docker images SHA256 pinned và không reuse container/image auth ngoài scope |
| Zero historic state | DB/user/volume/network mới tạo sau preflight; không copy/snapshot dữ liệu legacy/G0D-T01; DB mới phải chứng minh không có jobs/plans/leases trước normal start |
| Startup real | Normal engine vẫn có `cancel_all_antigravity_runs`, replay và lease/preview reconciliation; phải loại/giới hạn **side effect host** bằng source/negative tests trước khi tháo parked entrypoint, tuyệt đối không hạ guard chỉ vì compose config đúng |
| Provider route | Scope model registry chỉ Codex được duyệt + effort; Router riêng và provider authentication riêng; chứng minh egress allowlist thực sự, không tin việc network có tên `fullpath-provider` |
| PR/CI/PM | Executor GitHub credential cấp riêng, không agent-accessible; pipeline thực hiện PR trên đúng repo/HEAD, workflow Composer/PHPCS/Unit/Kernel đã xác thực; biên nhận PM không tự merge |
| Rollback | Không chạm mọi volume/DB/WorkOrder/Journals của legacy, Chợ Nhạc và `pcp-g0d01`; chỉ tài nguyên mới đã chứng minh ownership mới được dừng/xóa bởi quyết định riêng |

## Quyết định PM

**F2a = source topology ready-for-review**, **F2 operational = NOT READY**. Duy trì G0 HOLD/NOT GO, không cấp phép chạy `docker compose up`, không phát sinh Codex inference hoặc tạo DB/provider secret. Đánh giá F2b trước tiên về khả năng cô lập *normal startup host side effects* và liệu safe provider egress + privileged CI delivery có thể đạt được mà không cần Docker socket host hoặc engine song song. Nếu không, báo `FULLPATH_NOT_FEASIBLE` và đề xuất tối giản PCP trong #595 thay vì dựng smoke test thứ hai.

**Nguồn:** [F1 code gates #656–#660](https://github.com/sonvhse06072/personal-coding-platform/pull/660), [F1/T3 contract](g0-02-fullpath-source-admission-2026-10-12.md), [first paired output](g0-02-first-paired-outcome-2026-10-12.md). Hai PR fixture #4/#5 giữ OPEN, hai `benchmark/*` seed không đổi.
