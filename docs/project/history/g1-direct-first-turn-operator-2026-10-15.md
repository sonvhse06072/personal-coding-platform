# G1-T01 Direct first coding turn — one-shot activation handoff

**State:** SOURCE-ONLY. This file does not authorize a Docker/model call by itself.

The Owner's private Codex device-auth roots `~/.pcp-g1-pilot/auth/pcp` and `auth/direct` are already PASS. Do not re-login or copy global `~/.codex`. Accepted G1 MCP smoke remains frozen: job prefix `2c6db0aa6f19`, `0` model calls, no restart/reset/reuse.

## One real direct model turn, then equal PCP turn

The first scoped model action is `scripts/g1-pilot-direct-first-turn.py` and uses **only** the direct-control lane. It is intentionally **not** a PCP autonomous E2E claim. The sole allowed coding task matches [G1-T01](g1-pilot-t01-parked-2026-10-15.md): implement same-day `WindowOverlapDetector::intersectionMinutes()` and tests without changing `intersects()`, other project code, dependencies, DDEV or config. Pin `benchmark/g1-codex-smoke-v1@d4f4a56713e95f85ecc08c02bb43a5b5105a86a3`, model `gpt-6-luna`, effort `medium`, one turn at most 20 minutes.

**Activation posture:** Operator must be run on clean PCP `main` at its reviewed **MERGE SHA**, supplied explicitly with `--expected-pcp-sha`. It verifies exact source SHA and no existing G1 pilot source/workspace/Docker container/volume/network, reads the immutable G1 smoke **source** only (not old job workspace), and validates both separate prior auth roots' ownership/permissions. Then it writes `~/.pcp-g1-pilot/direct-t01-evidence.json` exclusively **before** any Docker/Git mutation, clones a NEW `direct-workspace`, builds only the existing Runtime image, starts only a time-limited direct-provider proxy, and executes exactly one `codex exec --json --sandbox workspace-write` in the Docker **direct** service. It cannot access the host Docker socket, Github token, PCP Runtime, or other DDEV projects.

**Proxy:** the Codex container belongs only to `pcp-g1-pilot-direct-control` internal network. A separate direct-only proxy spans this and `pcp-g1-pilot-direct-provider-egress`; no published port. Exact permitted provider domains, DNS/global-unicast, TLS SNI verification from PR #716 remain enforced. Unexpected OAuth endpoints STOP; do not broaden to a wildcard. Neither the new PCP service nor Executor/Router/DB or DDEV is started. A disabled dummy GitHub secret exists solely to satisfy Compose parsing for *unstarted* services.

**Result:** the operator records `model_calls=1` if Codex was actually invoked, terminal event, source SHA, token counts if surfaced, elapsed seconds, changed file scope and a LOCAL commit if exactly allowed two PHP files were modified without diff-check errors. It never prints raw JSONL, Codex output, credentials or provider links. It creates **no GitHub PR**, does **not** claim hosted CI or acceptance. A failure reports one sanitized STOP code and preserves all work and containers for analysis. **Never rerun** this script or create a replacement workspace to bypass a blocker.

A direct coding PASS is only `PASS_G1_DIRECT_CODE_READY_FOR_CI`, not a benchmark success. Next, Owner-assisted publish/exact-head hosted CI + PM review (using existing GitHub connector if needed), then one PCP coding lane with the SAME seed/task/model/effort and comparable accepted-PR metrics. Direct output MUST NOT be forwarded to the PCP Codex model.

**NO touch:** G1 accepted smoke, F2, G0D-T01, unrelated DDEV sites, Chợ Nhạc, production. G0 #595 remains HOLD / NOT GO until paired accepted output. Do not substitute a single direct coding run for a statistical result.


## 1.1. Recovery sau STOP đầu tiên — giữ nguyên workspace (15/10/2026)

Owner thực hiện đúng một lượt operator #717, trả `STOP_G1_DIRECT_ONE_SHOT / g1_direct_compose_operation_failed`. Read-only triage hiện trường: `compose_config=PASS`, `direct_workspace_exists=true`, `workspace_seed_ok=true`, `runtime_image_present=false`, `direct_proxy_present=false`, `direct_control_network_present=false`, `direct_egress_network_present=false`, `journal_state=started`, `recorded_attempts=0`. Từ source, mọi thao tác Compose có thể phát sinh lỗi này đều nằm **trước** marker `model_launched` và lệnh `codex exec` đầu tiên. Kết quả: 0 model calls; không có bằng chứng Codex đã chạy.

**Không rerun** `g1-pilot-direct-first-turn.py`; không `git reset`, xóa/đổi/clone thay thế workspace, Docker prune, restart G1 smoke hoặc tạo PCP job. G1-T01 direct workspace hiện tại vẫn là canonical.

Source fix chỉ tạo image **Codex direct-only** bằng [Dockerfile.direct-codex](../../../deploy/g1/Dockerfile.direct-codex) và [parked overlay](../../../deploy/g1/compose.pilot.direct-build.parked.yml): không build toàn bộ Runtime/Router, không cài OpenCode hoặc Python Runtime dependency. Nguyên nhân cụ thể của Docker build cũ chưa được chứng minh từ stderr đã bị bỏ; đây là biện pháp giảm bề mặt lỗi build và chi phí chuẩn bị, **không suy diễn lỗi là do OpenCode**.

Chỉ sau PM review/exact CI/merge, **một** `scripts/g1-pilot-direct-preserved-continuation.py --expected-pcp-sha <exact-mergesha>` mới được phép: xác minh journal gốc `state=started; attempts=0`, đúng root và workspace/branch/seed SHA còn sạch, không có image/network/container/resource pilot ngoại lai; kiểm tra source contract vẫn PARKED và auth roots độc lập (chỉ file metadata). Ghi **một marker mới, độc lập và exclusive** trước build. Chạy Compose render read-only + build **chỉ** image direct, không tạo job/source clone mới, không touch Runtime/DB/Executor; lưu `returncode` và error class đã phân loại nếu build fail. Chỉ nếu image/capability, proxy riêng, auth + allow/deny TLS trong cùng direct container PASS mới đánh dấu `model_launched` và gọi Codex **tối đa một lượt**. Tất cả STOP bảo toàn cả hai journal và workspace; không retry/cleanup tự động.

Một lượt direct code PASS chỉ tạo **commit local**, chưa phải PR hoặc hosted CI, chưa đủ chốt thắng/thua. G0 #595 tiếp tục HOLD / NOT GO.

