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
