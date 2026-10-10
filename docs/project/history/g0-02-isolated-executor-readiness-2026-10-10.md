# G0-02 — Đối chiếu runner cô lập và gate kích hoạt PCP Executor (2026-10-10)

**Authority:** T3 evidence/decision-prep only, không thay đổi ProjectBaseline, Constitution, Router, Runtime hay Executor. Tracking: [PCP #595](https://github.com/sonvhse06072/personal-coding-platform/issues/595), parent #593, [fixture task G0D-T01 #2](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/issues/2).

**Trạng thái:** **ISOLATED TOOLCHAIN/DB PREFLIGHT PASS**; **PCP EXECUTOR CHƯA ĐƯỢC TRIỂN KHAI RIÊNG / G0 NOT GO**. Owner chỉ phê duyệt [DEC-G0-FIXTURE-01](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6094931078) cho fixture thử nghiệm, không phê duyệt mở quyền runtime/developer, credentials, sản xuất hoặc thao tác trên Chợ Nhạc. Owner yêu cầu tất cả PCP work trong ChatGPT PM, tuyệt đối không sử dụng Codex đang chạy trên Chợ Nhạc.

## 1. Đã quan sát bằng chứng thật

- [Fixture PR #1](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/1): nguồn Drupal 11 `main`, seed `39ef13c25b24c4a1b43a720ae53419f479996ed2`, real PHPUnit Unit/Kernel/PHPCS/Composer CI PASS. [PCP PR #624](https://github.com/sonvhse06072/personal-coding-platform/pull/624) đăng ký nguồn và baseline `g0d01-seed-2026-10-10` ở trạng thái **PARKED**, `ddev.enabled=false` và mọi autonomous GitHub delivery OFF. No PCP local deployment.
- [Fixture PR #3](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/pull/3), reviewed exact head `af119ef6859a50c3094f2f6aefff02ac1518f3ef`, merged fixture main `b19e25fb35dbc94c8d725849943453aabb667e86`. [Fixture validation run 38046184895](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/actions/runs/38046184895) **SUCCESS**; separate [GitHub-hosted isolation run 38046184891](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/actions/runs/38046184891) **SUCCESS**.
- [Sanitized artifact #11667810169](https://github.com/sonvhse06072/pcp-g0-drupal-fixture/actions/runs/38046184891/artifacts/11667810169), retention 7 ngày, đã tải và tự kiểm tra bằng Python. Artifact SHA-256 `1b32b734a73e13a5889be5b83895e05887aaae7b87799f61565561252e56497d`. Source SHA **cả hai** `39ef13c25b24c4a1b43a720ae53419f479996ed2`; Composer lock SHA-256 `3a3d086be59571b43f05301ab099dc4d710a2ca1da0b25af60341d527f531f2b`.
- Hai Git clone độc lập, hai DDEV project `pcp-g0d02-direct` / `pcp-g0d02-pcp`, PHP **8.4.24**, Node **v24.20.0**, MariaDB **11.8.9**, Composer **2.10.3**, DDEV **1.25.4**, binary thực `codex-cli 0.160.0`. Hai phép kiểm tra chéo SQL xác nhận bảng tạo ở DB arm A không xuất hiện ở DB arm B và ngược lại. `toolchain_id=g0d02-83ea72ca870c84d9592f698b`.
- Fixture `main` tiến lên `b19e25fb...` chỉ thêm workflow/script/test preflight; **`benchmark/direct` và `benchmark/pcp` vẫn ở seed `39ef13c2...`**, code task G0D-T01 chưa sửa. Cloud runner GitHub-hosted Ubuntu 24.04 bị tiêu hủy sau job: không chứa Chợ Nhạc, không dùng owner WSL/PCP Router/Guardian/PM Bridge, không chạy `codex exec`, không có token provider/authenticated session.

**Giới hạn bằng chứng:** artifact tuyên bố rõ `eligible_for_controlled_benchmark=false`, `pcp_runtime_connected=false`, `project_baseline_activated=false`, `provider_authenticated=false`, `model_id=null`, `reasoning_effort=null`, `real_pcpxdirect_trials=0`. Việc runner cloud cài Codex **0.160.0** chỉ trùng **phiên bản đã quan sát trước đây** trong PCP Runtime, không chứng minh phiên bản mới nhất trong deployment hiện tại. Codex host Owner từng quan sát **0.162.0**, nên dùng host đó như direct arm và Runtime 0.160.0 làm PCP arm sẽ không tạo cohort chuẩn hóa.

## 2. Architecture/authority: những gì **chưa** được chứng minh

Một runner GitHub-hosted tạm thời **không phải** PCP `coding-runtime` hoặc `ddev-executor` đang hoạt động: nó không có durable job/state, kết nối điều khiển, ProjectBaseline đã triển khai, signed/intake mechanism, model/provider auth, lease, credential delivery, hay khả năng quay về GitHub với review/merge của một WorkOrder PCP. Không dùng nguồn CI để tự tuyên bố có PCP autonomous delivery.

`config/projects.yml` vẫn cố ý PARKED, không đổi các cờ `autonomy.allow_commit/push_ai_branch/create_pr/auto_merge_low_risk`, không bật `ddev.enabled`. Tài liệu/issue hoặc GH Actions PASS không nâng quyền. G0D-T01 yêu cầu hai arm có model+effort, toolchain, source, acceptance, CI/review giống nhau, mỗi arm workspace/DB/PR khác nhau, và tiến trình thật mới tính timestamp/usage/Owner intervention.

## 3. Phương án triển khai tiếp theo — chỉ là đề xuất, chưa kích hoạt

**Ưu tiên đề xuất:** một **VM/runner PCP độc lập hoàn toàn** với Docker daemon, DDEV router, file system/workspaces, Runtime/Executor/Router và DB bền vững **riêng**; không mount `/home/sonvh/chonhac`, `~/.coding-platform/workspaces` hiện hữu, Docker socket/credential/DB của máy đang chạy Chợ Nhạc, và không mở tunnel/PM Bridge sang Chợ Nhạc. Tái sử dụng phiên bản source PCP đã duyệt, default tất cả project khác không cho phép; chỉ fixture repo private với write scope tối thiểu cho PR. Cài và kiểm tra thực tế Codex 0.160.0 trong **hai** arm hoặc dùng bản CLI riêng trong direct arm (không downgrade host toàn cục). Kiểm tra model slug, reasoning effort, tài khoản/entitlement và mức quota/giới hạn tài nguyên theo provider policy; không đưa secrets vào GitHub Actions artifact/log.

**Không lựa chọn lúc này:** điều khiển Docker/Executor từ PCP trên máy Owner sang VM qua remote privileged broker, hoặc ghép GitHub-hosted job thành một Executor có credential toàn quyền. Đó là **thay đổi trust/network/authorization architecture**, cần ChangeProposal/Human Owner approval riêng; chứng minh toolchain chỉ là tiền đề kỹ thuật, không đủ quyền áp dụng.

### Gate chặn trước protected activation PR

1. Có địa chỉ/identity của VM độc lập **thật**, Docker/DDEV/DB chạy riêng, quyền thuộc fixture-only, không dùng nguồn Chợ Nhạc và không ảnh hưởng process/router chung. Thu live source SHA/deployed PCP binaries và preflight `project_id`, token scope, DDEV registry, resource headroom.
2. Xác nhận installed `codex --version` của PCP Runtime/Executor và direct arm **cùng phiên bản thực**, `model_id` và `reasoning_effort` có entitlement authenticated, cùng acceptance hash và CI/review; nếu provider unavailable, **STOP**, không chép credential của Codex đang làm Chợ Nhạc hoặc giả lập model.
3. Ràng buộc `pcp-g0-drupal-fixture` với exact protected approved seed `39ef13c2...`, `benchmark/pcp` và `benchmark/direct` tách biệt, base/PR/review gates rõ; GitHub delivery permissions chỉ cho repo fixture. Bằng chứng single writer/workspace/DB lease thật; không biến GH-89 hoặc historical PCP job thành test.
4. Trình Owner **ChangeProposal kích hoạt fixture-only** nếu cần sửa protected DDEV/autonomy/Executor/runtime/network fields; PR khai báo đúng Owner approval/scope, exact-head CI/review, tách rollout/rollback. **Không** tự chỉnh `config/pm-bridge.yml`, Constitution, authorization model hoặc restart PCP/Chợ Nhạc.
5. Chỉ khi bốn gate trên thỏa mãn mới cho phép **một** G0D-T01 A/B với hai PR nghiệm thu bằng cùng CI, times/usage thực; `scripts/pcp-parity-benchmark.py` loại cả các pair thiếu model/effort/CLI/workspace/toolchain hoặc QA. Không suy ra p50 dưới 3 cặp hay p90 dưới 10 cặp; G0 investment Go/No-Go thuộc Owner.

**Rollback/stop:** nếu không có VM độc lập hoặc chỉ có shared WSL đang chạy Chợ Nhạc, giữ `PARKED`, không start/restart DDEV ở máy đó, không chạm Chợ Nhạc. Không retry job mù, không cấp quyền host, không tự chạy G1 #596. Cập nhật #595 là `isolated prerequisites PASS; real PCP execution insufficient evidence`.

## 4. Quyết định Owner mới: PCP tiếp tục trên WSL (supersedes separate-VM preference)

**Decision DEC-G0-EXEC-02 / 2026-10-10:** Owner xác nhận tại ChatGPT “đồng ý. tiếp tục công việc”, sau khi PM đề xuất **giữ PCP ở Ubuntu WSL hiện tại**, không thuê VM độc lập. Quyết định đã được ghi tại [PCP #595](https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6096935630). Mục 3 phía trên và proposal VM cũ là **historical fallback**, không phải kiến trúc bắt buộc hoặc yêu cầu provision máy mới. Quyết định này **chưa** cho phép chuyển fixture từ PARKED sang active, cấp quyền Docker/model/GitHub mới, triển khai hoặc chạy G0D-T01.

### 4.1. Kiến trúc đã chọn và rủi ro còn lại

- PCP vẫn host tại `/home/sonvh/personal-coding-platform-v1` trong WSL/Docker Desktop. Fixture source là một checkout Git **mới, riêng**, đúng protected seed `39ef13c25b24c4a1b43a720ae53419f479996ed2`; không copy bất kỳ source/DB/media của Chợ Nhạc.
- `runtime.workspace_mode=isolated_clone`: mỗi WorkOrder có một workspace riêng dưới `CODING_WORKSPACES_ROOT`, branch `ai/*`, Git clone không giữ origin trong agent workspace. DDEV override do executor quản lý có tên `cp-<job_id[:10]>`, độc lập với DDEV project Chợ Nhạc; DB, volume, ports và review/CI phải được xác minh riêng.
- DDEV **có thể** chạy nhiều dự án trên một Docker daemon/router. Điều kiện an toàn thực tế là **không trùng project/port/hostname, đúng ownership, đủ tài nguyên**, không phải dừng các dự án đang hoạt động. Quy tắc bootstrap v1–v6 trước đó chặn mọi DDEV project active là chính sách thận trọng cho *bootstrap*; không chuyển quy tắc đó thành yêu cầu dừng Chợ Nhạc để benchmark. Không hạ gate của bootstrap cũ và không chạy nó trên Chợ Nhạc.
- Shared Docker daemon/socket là quyền thực thi mạnh có thể ảnh hưởng gián tiếp đến các project khác, kể cả khi lệnh nhắm vào fixture. DDEV router có thể cập nhật topology khi `ddev start`. Vì vậy **không thể bảo đảm hard isolation như VM riêng** bằng project name, CLI regex hay prompt. Trước lần chạy local đầu tiên cần quan sát router/host capacity + thiết lập ranh giới capability/ownership ở Executor, xác minh không có xung đột, theo dõi và có rollback không restart global. Nếu không đủ điều kiện, *giữ PARKED*, VM riêng là lựa chọn fallback.
- Cấm mọi PCP benchmark control, Git, DB, DDEV, preview, workspace, lease hoặc credential thao tác **trực tiếp nhắm vào Chợ Nhạc**. Không sử dụng Codex đang làm việc trên Chợ Nhạc. Không `ddev poweroff`, `ddev stop -a`, `docker system prune`, `docker restart`/Docker Desktop restart cho bước benchmark. Bất kỳ lệnh cleanup nào chỉ áp dụng đúng DDEV identity và project/volume của fixture, không xóa DB tùy tiện.

### 4.2. Guard đầu tiên đã triển khai ở source PCP, chưa rollout

Một lỗi thực đã phát hiện: `services/ddev-executor/app/main.py:phase()` trước đây **không kiểm tra `ddev.enabled`** trước khi gọi `ddev start`; endpoint quiesce cho isolated workspace cũng có thể gọi `ddev stop` khi project bị tắt. Do đó cấu hình PARKED không hoàn toàn là rào chắn ở Executor API.

Sửa kiểm soát `_require_ddev_enabled` dùng **boolean YAML `true`** (không chấp nhận string `"true"`, `"false"` hay int), từ chối `phase` và `quiesce` isolated trước kiểm tra/ghi vào workspace hoặc spawn DDEV khi disabled. Direct-workspace `quiesce` vốn no-op vẫn được giữ nguyên; tránh ảnh hưởng luồng hiện hữu. Negative tests tạo dự án giả trong `tmp_path`, monkeypatch mọi lệnh DDEV và filesystem callbacks, chứng minh fail-closed ở `preflight`, `targeted_tests`, `cleanup` và `remove_data=true`. Không test nào chạy DDEV thật, không thao tác trên Chợ Nhạc.

**Lưu ý:** guard này ngăn DDEV phase khi fixture PARKED; **không tự chứng minh** một project được bật sẽ không thể gửi lệnh tùy ý tới Docker socket. Gate nâng quyền/project-scoped broker/command allowlist và xác thực ownership của source/lease/DB là điều kiện riêng trước protected activation. Không được coi unit tests hoặc PR merge là local deploy.

### 4.3. Bước tiến hành tiếp, không tự kích hoạt

1. PM đã chuẩn bị **read-only WSL preflight** `scripts/g0-wsl-coexistence-preflight.py` cho metadata PCP/fixture và `ddev list -j`: kiểm tra CLI hiện cài, source HEAD/worktree, unique DDEV identity, context/ports/capacity, isolation markers; *không* gọi DDEV start/stop, không lấy credentials/DB/private files. Khi chủ sở hữu chạy thì chỉ xuất trạng thái đã ẩn tên project nhạy cảm và blocker/OK flags. Đầu ra này không là authorization.
2. Sau khi có bằng chứng read-only ở WSL, hoàn thiện proposal chi tiết **fixture-only activation**: scope `config/projects.yml` đúng một fixture ID, `base_branch=benchmark/pcp`, DDEV phases có Unit/Kernel/PHPCS thật, cleanup chỉ đúng job, auto production deploy OFF; cần quyền GitHub PR giới hạn fixture và review/CI. Kiểm tra rằng các entry/config của Chợ Nhạc không bị sửa.
3. So khớp **installed** Codex CLI (Runtime pin `0.160.0`; last observed host `0.162.0`), cùng `model_id`, reasoning effort, entitlement và quota. Dùng local **binary riêng** cho arm direct nếu thích hợp, không đổi global Codex đang phục vụ Chợ Nhạc. Phải có hai DB/workspace/CI/review độc lập, một pair G0D-T01 và stop nếu lệch.
4. ProjectBaseline seed `g0d01-seed-2026-10-10` **giữ nguyên không rewrite**. Protected config activation/rollout chỉ sau explicit Owner approval cho phạm vi, exact-head PR/CI/review và source-vs-deployed/live lease gate. **G0 NOT GO** cho đến khi có real A/B outcomes; p50 tối thiểu ba pairs, p90 tối thiểu mười pairs và Owner đầu tư quyết định.

**Rollback:** khi phát hiện DDEV project/route collision, resource pressure, wrong workspace/source/CLI, provider mismatch hoặc nghi ngờ tác động gián tiếp đến Chợ Nhạc: dừng **chỉ job fixture** theo guard chính thức, giữ diff/counters/lease, không stop/restart/destroy Chợ Nhạc hoặc Docker host. Nếu chưa thể chứng minh safe stop của fixture, không khởi chạy benchmark ngay từ đầu.

### 4.4. Read-only operator preflight đã được version hóa — chưa chạy trên WSL

Script `scripts/g0-wsl-coexistence-preflight.py` chỉ chạy những lệnh đã cho phép cố định: `ddev list -j`, `ddev --version`, `codex --version` và `git -C <PCP/fixture-only> rev-parse HEAD` / `status --porcelain=v1`. Không gọi Docker, DDEV start/stop, Git fetch, Codex exec/model, API, file Chợ Nhạc hay network. Dữ liệu DDEV registry được đọc để kiểm tra **trùng tên DDEV fixture**, trả về **số lượng** các project đang chạy và trạng thái, **không xuất tên/địa chỉ project khác**. Việc DDEV khác đang chạy **không tự động là collision**; script vẫn đánh dấu **shared router indirect impact unverified** và `ready_to_dispatch_g0d_t01=false`. CLI mismatch/sai seed/source chưa có checkout/status không xác minh cũng đều được báo là blocker. Unit tests dùng DDEV JSON giả, không đọc WSL.

Chỉ sau khi PR chứa script đã merge và khi operator thực sự cần quan sát (không yêu cầu sync/restart PCP), có thể chạy dưới **subshell** trong checkout PCP source đã được update qua rollout riêng:
```bash
(
  cd /home/sonvh/personal-coding-platform-v1 || exit 2
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/g0-wsl-coexistence-preflight.py
)
```
Lệnh này **không thực thi tự động tại phiên PM GitHub**: repository GitHub và môi trường WSL của Owner là hai ngữ cảnh khác nhau. Report chỉ là read-only metadata và không chứng minh local PCP đã deploy, project đã được cấp quyền, không ảnh hưởng gián tiếp tới Chợ Nhạc hay có provider parity.
