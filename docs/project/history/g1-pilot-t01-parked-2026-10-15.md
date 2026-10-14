# G1-T01 — Pilot PCP vs Direct Codex (PARKED)

**Trạng thái 15/10/2026:** Source-only candidate. **Không khởi chạy, không đăng nhập, không dùng model, không tạo job**, không tự động merge/deploy.

## 1. Bằng chứng đầu vào và phạm vi

- G1 smoke job hiện hữu `2c6db0aa6f19…` đã đạt `PASS_G1_CORRECTED_MCP_HTTP_EXECUTOR_NO_MODEL` (HTTP 200, `frontend_quality` rc=0, đúng marker, 0 model calls). Bất biến: không repurpose/restart/reset/xóa job, DB và các tài nguyên smoke này.
- PCP authoritative: GitHub `main` + [#596](https://github.com/sonvhse06072/personal-coding-platform/issues/596); G0 investment gate [#595](https://github.com/sonvhse06072/personal-coding-platform/issues/595) vẫn **HOLD / NOT GO**.
- Fixture gốc duy nhất: `sonvhse06072/pcp-g0-fullpath-fixture` tại `benchmark/g1-codex-smoke-v1@d4f4a56713e95f85ecc08c02bb43a5b5105a86a3`. Tách hai *clean* lane PCP/direct ở cùng seed commit; lịch sử F2 T01 overnight, G0D-T01 và Chợ Nhạc ngoài phạm vi.
- Capsule PARKED: [compose](../../../deploy/g1/compose.pilot.parked.yml), [model registry](../../../config/g1-pilot/models.yml), [routing policy](../../../config/g1-pilot/routing-policy.yml). Tất cả service có non-default profile **và** `entrypoint=/bin/false`. Runtime còn `PCP_RUNTIME_STARTUP_MODE=inspect` và broker `PCP_TRUSTED_CODEX_BROKER_ENABLED=""`. **Đây không phải manifest có thể kích hoạt bằng cách chỉ thêm profile hay environment variable.**

## 2. G1-T01 — Task độc lập để đo chất lượng

`WindowOverlapDetector::intersectionMinutes(int $start, int $end, int $otherStart, int $otherEnd): int`

**Yêu cầu:** Với hai khoảng nửa mở **trong cùng ngày** thỏa `0 <= start < end <= 1440`, trả về số phút giao nhau `max(0, min(end,otherEnd)-max(start,otherStart))`. Khoảng sai, rỗng, vượt 1440 hay qua nửa đêm trả 0. Không thay đổi `intersects()`, không thêm dependencies, schema, network, production code, hay behavior của F2-T01.

**Phạm vi diff mã nguồn tối đa hai path:**
- `web/modules/custom/pcp_f2_fixture/src/WindowOverlapDetector.php`
- `web/modules/custom/pcp_f2_fixture/tests/src/Unit/WindowOverlapDetectorTest.php`

**Acceptance:** bao gồm đối xứng, partially overlapping, containment, equal windows, touching, disjoint, 0/1440 boundaries, invalid/overnight=0; unit tests/PHPCS và exact-head GitHub CI. Không dùng điều kiện “AI thành công” thay cho assertions. Không truyền lời giải của lane này cho model ở lane kia.

## 3. So sánh công bằng / ngân sách

- Cùng task văn bản, cùng seed SHA, Codex CLI version, model **GPT-6 Luna**, reasoning **Medium** (chỉ nếu được Codex CLI/plan hiện tại chấp nhận; nếu không STOP, không tự đổi model/effort), 1 execute + tối đa 1 repair khi có bằng chứng, tối đa 2 changed paths. Router pilot registry **chỉ** cho phép `codex_gpt6_luna` ở profile fast; standard/complex/critical phải STOP thay vì chọn fallback.
- Chính sách G1 fast: tối đa 2 model calls, 1 repair, 3 tests, 20 phút, hard estimated USD $0.50 (giới hạn nội bộ, không phải bill thực). Một lượt in-turn MCP chỉ có các named phases được Executor allowlist; tuyệt đối không Docker socket/host shell/tokens/PAT ở model.
- Hai lane phải được tách workspace/branch, credentials riêng; thực hiện tuần tự nếu tên DDEV/xung đột tài nguyên. Cùng suite kiểm chứng, chuẩn PM review và exact-head CI. Không auto merge.
- Thu số phút wall-clock để đến **accepted PR**, riêng thời gian chuẩn bị, counts model/retries/tests, token input/output từ telemetry nếu có, số phút Owner can thiệp, và bill provider *chỉ khi thực sự có chứng từ*. Một cặp không đủ suy p50/p90 hay lợi thế định lượng vững chắc.

## 4. Gate chưa đạt — không được tự kích hoạt

| Gate | Trạng thái |
|---|---|
| G1 no-model MCP broker thực tế | **PASS** (tài nguyên smoke riêng) |
| Tài nguyên pilot mới, riêng smoke/F2/Chợ Nhạc | **CHƯA TẠO** |
| Fixture pilot và direct có 2 DDEV identity không xung đột | **NOT PROVEN** |
| Guard hardcoded `pcp-benchmark-g1-smoke` / DDEV name được mở *đúng* pilot identity đã duyệt | **NOT IMPLEMENTED** |
| Provider outbound (gateway + domain/secret isolation) | **NOT PROVEN** |
| Codex auth của PCP/direct riêng, có xác thực thực tế | **NOT PROVEN** |
| Repo-only GitHub token với quyền tối thiểu và explicit PR gate | **NOT PROVEN** |
| Runtime normal safe startup, Router lựa chọn đúng fast/Medium, Executor grant exact job | **NOT PROVEN** |
| Codex edit→MCP targeted tests→repair→GitHub CI→PR | **NOT RUN** |
| G0 GO | **NO** |

**Kiến trúc mạng PARKED:** `g1-pilot-control` chỉ nội bộ; Runtime có một provider-egress riêng, Executor có github-egress riêng, direct có provider-egress độc lập. `internal:false` trên mạng provider/GitHub chỉ là khả năng đi Internet, **không phải domain allowlisting**. Không được mở network/credential hoạt động trước khi có scoped outbound enforcement hoặc một quyết định rủi ro được phê duyệt riêng.

**Bảo vệ secrets:** `CODEX_HOME` của PCP và direct ở hai thư mục auth mới khác nhau, không clone thư mục auth cá nhân. GitHub token dạng Compose secret chỉ có ở Executor và phải là token repo-only mới; Router, Runtime, direct và DDEV web/db không được mount PAT. Docker socket chỉ ở Executor, và phải có allowlisted DDEV container/command attestation; không có socket ở Codex Runtime.

**Điểm phải chốt trước rollout:** Để tạo cặp workspace độc lập từ **cùng SHA** mà không đụng `pcp-g1-codex-smoke` hiện đang chạy, cần hai định danh DDEV riêng. Guard `_trusted_dev_plan`, `g1_ddev_isolation`, Runtime `project_config` hiện đang pin smoke project và container name. Các guard này **không được nới lỏng tự động bởi capsule**. Bước implementation kế tiếp là proposal có diff chính xác cho *một pilot identity và một direct identity* cùng nguồn, test deny mọi project khác, và operator one-shot (không nhiều stage); chỉ sau acceptance mới có thể cho model chạy.

## 5. Kiểm tra source không làm thay đổi hệ thống

`python3 scripts/g1-pilot-source-contract.py` đọc ba YAML source và xác nhận trạng thái PARKED/boundaries/model budget; không gọi Docker, network, provider hay Codex. Đây là **CI source contract** chứ không phải runtime preflight và cũng không là yêu cầu Owner phải chạy thêm. Khi các gate chưa chứng minh, kết quả `PASS_G1_PILOT_SOURCE_PARKED` luôn đi kèm `ready_for_model_dispatch=false`.

**Quy tắc STOP:** mọi tên resource, SHA, access scope, credentials, model/effort hay Docker inspect không khớp ⇒ giữ nguyên trạng thái, không retry, không xóa/đổi job cũ, không fallback host full access. Bảo toàn journal gốc, không ghi log token.
