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

## 5. Owner WSL read-only inventory observed — next source-only staging

**Actual Owner-run JSON on 2026-10-10** from `scripts/g0-wsl-coexistence-preflight.py`, not a PM-generated estimate:

- Local PCP Git checkout `/home/sonvh/personal-coding-platform-v1` **exists and is clean**, HEAD `d53fbb07524bb3ca13324e2ed7edac1513367072` (behind verified GitHub source). This alone does **not** prove installed runtime/Executor currently runs that exact HEAD; no sync/restart authorized.
- **DDEV 1.25.4**, **17 projects registered, three active**; fixture project-name collision `false`. The report intentionally does not reveal names/paths of those other projects. Shared Docker/router indirect effect, host port and resource capacity are **not yet verified**. Do not stop other running projects.
- Expected fixture source path **does not exist** (`fixture_source_not_observed`), so no PCP fixture checkout can be used by Runtime. Exact approved seed for `benchmark/pcp` and `benchmark/direct`: `39ef13c25b24c4a1b43a720ae53419f479996ed2`, Composer lock SHA256 `3a3d086be59571b43f05301ab099dc4d710a2ca1da0b25af60341d527f531f2b`. The remote private repo's two benchmark refs remain pinned at seed.
- Host `codex-cli 0.162.0`, PCP checked-in `config/tool-versions.env` source pin `0.160.0`; **actual deployed Runtime binary still unknown**. Do not downgrade global host CLI or replace Codex session active for Chợ Nhạc.
- `actual_runtime_binary_unverified=true`, `lease_unverified=true`, `model_and_effort_unverified=true`, `port_resource_headroom_unverified=true`, `ready_to_dispatch_g0d_t01=false`, **0 real paired accepted outcomes**.

### 5.1. Minimal next operation — approved isolated Git source checkout only

New `scripts/g0-stage-local-fixture.py` (PCP source-only, **not deployed**) offers two explicit modes:
- **default / `--inspect`:** read-only, authenticated GitHub private repo and exact frozen `benchmark/pcp` + `benchmark/direct` commit checks; ensure the only fixed target `$HOME/pcp-g0-fixtures/pcp-g0-drupal-fixture` is new and not a symlink. No source/file creation.
- **`--create`:** after successful preflight, create at most that one new user-owned parent directory and clone only the fixed private repo's `benchmark/pcp` branch, single branch, no tags. Verify exact Git HEAD `39ef13c2...`, clean tree, HTTPS/SSH origin repo identity, `composer.lock` SHA256 and baseline document. Do **not** fetch/update/pull PCP local, copy owner project data, rewrite an existing fixture, delete/retry partial clone, install Composer/DDEV, change Codex, or call PCP Runtime/Chợ Nhạc.

**Expected execution:** from this ChatGPT conversation PM can merge the script via PR/CI but **cannot execute the Owner WSL shell**. When the branch is merged and Owner is ready, use an isolated subshell and `gh api` (read-only to PCP GitHub) to stream the exact merged source to `python3 - --inspect`, then `--create` only if preflight passes. This downloads executable code through a trusted exact Git SHA, so review the PR/script first. `gh repo clone` requires the Owner's already authenticated GitHub CLI; if unavailable/failed, STOP and do not ask for tokens. No DDEV operations are necessary to stage source while other projects are running.

After source staging, rerun the **existing read-only WSL preflight**; expect the fixture Git source blocker to clear only if the real checkout exactly matches the protected seed and is clean. Host CLI mismatch/actual Runtime binary, model/effort/provider, local project path mapping, lease, ports/resource and indirect router impact remain separate blockers. **No protected fixture DDEV/delivery activation or G0D-T01 dispatch** from source checkout; ProjectBaseline remains PARKED until separately approved reviewed rollout.

## 6. Fixture đã có trên WSL — read-only container mount and Runtime CLI gate (2026-10-10)

**Evidence trực tiếp từ Owner đã thực thi:** [approved source-only stage PR #628](https://github.com/sonvhse06072/personal-coding-platform/pull/628) merged at `dbf938f66fdaba4bb78c1f3d7f15cb979b4a9d3f`; Owner ran the exact `--create` source-only tool and the follow-up read-only coexistence audit. Stage reported `clean_new_source_checkout_verified`, `repository_private=true`, target `/home/sonvh/pcp-g0-fixtures/pcp-g0-drupal-fixture`, `benchmark/pcp`, frozen seed `39ef13c25b24c4a1b43a720ae53419f479996ed2`, and Composer lock SHA256 `3a3d086be59571b43f05301ab099dc4d710a2ca1da0b25af60341d527f531f2b`. Read-only follow-up observed **Git exists/clean/source seed exact**; previous `fixture_source_not_observed` is **RESOLVED**. DDEV 1.25.4, 17 projects registered / 3 active, no fixture DDEV name collision. No DDEV/Composer/Codex/PCP runtime mutation performed.

**Remaining evidence gaps (actual state, not source assumptions):** local PCP checkout stays clean at `d53fbb07524bb3ca13324e2ed7edac1513367072` behind GitHub; host Codex `0.162.0` while `config/tool-versions.env` pin is `0.160.0`, **actual deployed PCP Runtime CLI is unknown**. Model slug, reasoning effort, provider entitlement, lease and ports/resources remain unknown, and indirect shared DDEV router impact is not disproven. `ready_to_dispatch_g0d_t01=false`, 0 accepted PCP/direct task pairs.

### 6.1. Critical mount mismatch possibility

Authoritative PCP `config/projects.yml` registers the fixture at `${CODING_PROJECTS_ROOT}/pcp-g0-fixtures/pcp-g0-drupal-fixture`. PCP's `.ddev/docker-compose.platform.yaml` bind-mounts **only** `${CODING_PROJECTS_ROOT}:${CODING_PROJECTS_ROOT}` into `ddev-executor`. The checked-in README documents default `CODING_PROJECTS_ROOT=$HOME/projects`; Owner's actual local environment might override this. Thus a Git checkout at `$HOME/pcp-g0-fixtures/...` **does not prove it is under the live Executor's configured project root or visible in its container**. Do not assume a match, do not edit `.ddev/.env` to coerce it, do not symlink around mount ownership and do not move/copy the already clean fixture speculatively. Confirm the actual live Executor root and mount/fixture visibility **first**, and choose a narrowly reviewed corrective approach only if a mismatch is proven.

### 6.2. Versioned PCP-only live observation probe

New `scripts/g0-pcp-live-mount-probe.py` reads only the **two exact PCP service containers** `ddev-personal-coding-platform-ddev-executor` and `ddev-personal-coding-platform-coding-runtime`. It calls `docker inspect --format` only for **Name, Labels, State.Running and Mounts** (not `Config.Env`), validates PCP ownership labels before further calls, and runs bounded read-only `docker exec <PCP-executor> printenv CODING_PROJECTS_ROOT`, conditional `test -d/-f` on the exact approved fixture path, and `docker exec <PCP-runtime> codex --version`. These `docker exec` commands start **read-only check processes inside PCP containers only**; they are not a fully passive observation but **do not start/stop/restart containers, invoke a model, authenticate, change globals, request DDEV actions or touch Chợ Nhạc**. Unexpected/stopped/non-PCP container identities fail closed; no fallback `docker ps`, no arbitrary Docker inspect or environment dump. The JSON report emits only booleans and observed version/resource numbers, **no unrelated project names, mount source paths or credentials**.

The script also computes only the already approved local fixture's lock SHA256 and Linux filesystem/RAM observations; it **does not verify the full live Runtime source/lease/port or provider state**. Regardless of finding, `ready_to_dispatch_g0d_t01=false`; fixture remains `PARKED`. Tests stub Docker entirely, prove allowed PCP commands and reject all container operations on Chợ Nhạc. This script will be run **only by the Owner on WSL, after exact-HEAD reviewed/merged source**, not from this GitHub PM session.

**Gate:** If Executor does not mount the directory the registered project points to, address only that proven discrepancy via separate guarded plan/PR. If Runtime Codex is `0.160.0`, future direct arm can use an **isolated pinned 0.160.0 binary**; **never downgrade host/global 0.162.0** used by Chợ Nhạc. Even with both facts matched, require live lease/resources/router safety, authenticated same model/effort, exact source-vs-deployed checks and separate protected fixture activation before any G0D-T01 dispatch. G0 remains **NOT GO**.

## 7. Owner read-only result: mount **MATCH**, all PCP services **EXITED** (2026-10-10)

### 7.1. Verified live Docker metadata, not inferred source configuration

Owner executed [PR #629](https://github.com/sonvhse06072/personal-coding-platform/pull/629) PCP-only mount/Runtime observation probe. It **stopped correctly** at `pcp_container_identity_or_running_state_mismatch`. A subsequent targeted, read-only Docker inspection of the **four exact PCP containers** established:

| PCP service | Docker state | Exit code | OOMKilled | Finished (UTC) |
| --- | --- | --- | --- | --- |
| Router | exited | 255 | false | `2026-10-10T07:21:54.279352010Z` |
| Coding Runtime | exited | 255 | false | `2026-10-10T07:21:54.285823544Z` |
| DDEV Executor | exited | 255 | false | `2026-10-10T07:21:54.279358068Z` |
| n8n | exited | 255 | false | `2026-10-10T07:21:54.285849788Z` |

All four have correct container names; they finished within **6.5 milliseconds** of each other at approximately 14:21:54 in Vietnam. A common Docker Desktop/WSL/daemon lifecycle event or coordinated stop is more plausible than four independent app failures, but **deliberate stop vs host failure is unknown**. This does not establish a PCP code defect, nor does per-container `OOMKilled=false` disprove all memory pressure. Existing `.ddev/docker-compose.platform.yaml` specifies `restart: "no"`; stopped services will not necessarily recover automatically.

Owner then performed a scoped **Docker inspect metadata-only** check on the stopped PCP Executor, with this sanitized exact result:

```json
{
  "executor_status": "exited",
  "executor_projects_root": "/home/sonvh",
  "configured_fixture_matches_local_checkout": true,
  "projects_root_bind_present": true,
  "restart_policy": "no",
  "ready_to_dispatch_g0d_t01": false
}
```

Therefore **the suspected `CODING_PROJECTS_ROOT` mismatch is RESOLVED**: the actual Executor project root is `/home/sonvh`, its host bind destination exists, and the clean frozen fixture at `/home/sonvh/pcp-g0-fixtures/pcp-g0-drupal-fixture` is at the registered relative path. **Do not** move/clone the fixture again, add symlinks, edit `.ddev/.env` or reconfigure mounts without a separate evidenced reason. A Docker bind declaration is a *reachability precondition*, **not proof the stopped service can currently read fixture files inside a live container**.

### 7.2. Project-scoped safety consequences

**Broad bind risk:** `/home/sonvh` is a broad host path and the DDEV Executor holds a Docker-socket capability. The mount contains more than just the fixture; project-name checks, prompt policies and a shared DDEV router are not OS-level hard isolation. Before any trusted fixture activation or developer execution on shared WSL, confirm the Executor's project-scoped API access, exact source/workspace identity and non-target operation bounds with negative tests. Keep Chợ Nhạc no-touch and do not equate read-only inspection with enforcement.

**Do not restart blindly:** `.ddev/config.yaml` defines PCP `pre-start` hooks building PCP service images via `scripts/pcp-build-images.sh` and starting PCP's Antigravity host bridge. A new `ddev start` would run real host/build actions; `docker start` would run stopped containers against possibly outdated images/config and skip normal rollout checks. Neither is a neutral diagnostic. No Docker/Desktop/WSL reset, DDEV poweroff, global cleanup or Chợ Nhạc stop is permitted as a workaround for these PCP-only missing-runtime observations.

**Safe recovery gate (not executed):**
1. Establish whether the concurrent PCP stop was intentional or coincided with a host/daemon lifecycle interruption, using Owner recollection and scoped read-only PCP-specific Docker state/host event metadata as needed. Do not infer a service crash from exit code alone.
2. Confirm local PCP Git still clean; compare local `d53fbb0` with approved remote `99939ef155cbb38910502dfc557664fc011f7b42`, and preserve any durable jobs, state, historical leases and active resources before any source sync, image build, startup or rollout. Never auto-reset, clean worktrees or release a lease.
3. Review available CPU/RAM/disk, DDEV project/router/port identity, Builder use, intended PCP-only startup hooks and a bounded rollback. Keep existing Chợ Nhạc containers untouched. Explicit Owner-gated activation and source/deployed parity are separate from a documentary PR.
4. After a deliberately approved PCP-only recovery, rerun mount and Runtime Codex version checks; verify actual in-container fixture visibility and file hash. Only then establish provider/model/effort equivalence, protected fixture `ddev.enabled` and delivery approval, and a single G0D-T01 matched trial.

**Remaining:** checked-in CLI pin `0.160.0` is **not** an observed running Runtime binary, and host global Codex `0.162.0` must not be changed for this benchmark. Fixture remains `PARKED`; **zero accepted A/B pairs**, G0 NOT GO and G1 #596 unapproved.

## 8. Owner xác nhận PCP đã được dừng chủ động — không có incident cần repair (2026-10-10)

**Thông tin mới từ chính Human Owner:** khi PM hỏi có chủ động dừng PCP/WSL/Docker Desktop vào khoảng 14:21 ngày 10/10 không, Owner đáp **“tôi có dừng vào thời gian đó”**. Vì vậy không cần tiếp tục theo đuổi giả thuyết crash Docker daemon, WSL, thiếu bộ nhớ hoặc bốn ứng dụng PCP đồng thời lỗi. Các timestamp/exit code tại mục 7 vẫn chính xác là **quan sát kỹ thuật**, nhưng sự kiện dừng PCP là **chủ động**. Không biến `ExitCode=255` thành incident phần mềm, không sửa retry/restart policy chỉ để phản ứng với sự kiện đã biết.

**G0 readiness hiện tại:** fixture đã có Git source mới, sạch và đúng seed/lock; `CODING_PROJECTS_ROOT=/home/sonvh` trong metadata stopped Executor cùng bind root đúng, nên nghi ngờ sai đường dẫn đã giải quyết. Nhưng PCP local source đã quan sát `d53fbb0` là bản cũ so với GitHub main, Runtime/Executor đều dừng, và `ddev.enabled=false`/delivery OFF vẫn là gate có chủ đích. Bản `ddev.enabled` guard sửa ở GitHub source chưa được chứng minh triển khai; `codex --version` trong Runtime và trạng thái các job/lease không thể suy ra từ host Codex.

### 8.1. Thứ tự khôi phục PCP duy nhất theo phạm vi đã duyệt

1. **Read-only pre-start audit trên chính PCP:** xác nhận `git branch --show-current`, `git status --porcelain`, HEAD local + main GitHub SHA; xác nhận đúng những container PCP đang dừng, kiểm tra ảnh build PCP còn tồn tại và RAM/đĩa/CPU còn đủ. Chỉ xuất trạng thái đã lược bỏ thông tin nhạy cảm; không xem thư mục/chạy lệnh trên Chợ Nhạc.
2. **Quiescence/job/lease + source rollout:** nếu còn durable active work/recovery hay không chắc về ownership, stop tại đây; không xóa, reset, kill hoặc đổi counter. Quyết định đồng bộ PCP Git clean/fast-forward và kế hoạch image build/Antigravity bridge dựa trên diff mới nhất. `.ddev/config.yaml` có `pre-start` hooks build images bằng `pcp-builder` và start bridge; nên `ddev start` không phải thao tác chẩn đoán chỉ đọc.
3. **PCP-only guarded startup**, sau khi Owner đã phê duyệt đúng scope và có điều kiện dừng/rollback; không `docker system prune`, restart Docker Desktop, `ddev poweroff` hoặc bất kỳ thao tác nào nhắm Chợ Nhạc. Shared Docker/DDEV router vẫn là rủi ro gián tiếp cần giám sát.
4. **Post-start verification:** health PCP/Executor, thực tế fixture accessible trong executor, source/deployed SHA, Runtime Codex pin/model/effort, DB/job/lease và resource headroom. Chỉ khi đạt đầy đủ mới chuẩn bị **PR protected fixture-only activation**. Giữ hai benchmark refs nguyên seed, không dispatch G0D-T01 sớm.

**Phạm vi/quyền:** Owner xác nhận lý do dừng **không đồng nghĩa đồng ý chạy lại hoặc đồng bộ local PCP ngay**. Không động tới Codex host đang phục vụ Chợ Nhạc; không tạo VM, không tự mở `ddev.enabled` hoặc GitHub delivery. G0 vẫn **NOT GO** với 0 cặp A/B accepted.
