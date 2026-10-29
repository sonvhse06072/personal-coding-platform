# Current Project State and Handoff

Tier-1 mutable continuity, not baseline, merge or admission authority. Reverify
exact source/PM/physical receipts before acting.

## Accepted observer828 physically adopted

Updated 2026-10-29 under [DEC-PCP-815-OBSERVER828-ADOPT-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6490872107).
[PR828](https://github.com/sonvhse06072/personal-coding-platform/pull/828) is merged
at **51349be73b54ca2fb827a4becc30e00ba62acd7d**, independently reviewed. Reviewed
and merged tree `eb700feb9e43f1b246d315476947e08d3106be78` match. Exact postmerge
[CI40836381983](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40836381983)
executed all four suites: **5093 passed / 135 skipped**. This supersedes the
premerge observer hold, not baseline/admission authority.

**https://localhost:18443/dashboard — loopback_readonly, no login/token/cookie.**
Actual fresh Chromium with normal TLS validation passed empty-state rendering,
six successful polls and offline/reconnect. Actual V4 DB stays empty; this is no
claim of active development or provider entitlement. Other local OS processes
can read, as explicitly approved; remote anonymous access is not authorized.

One build each from accepted51349, new full-SHA tags and immutable IDs:
Runtime `d7761e08e8f9…`, Router `9f0d95058423…`, Executor `70a5d315c671…`.
Only Runtime observer was deployed; Router/Executor are preparation images.
Image contents/modes/toolchains, non-root/read-only/noexec and immutable askpass
passed. Live observer has no worker, activation, schema initialization or
provider/publisher credentials. Runtime upstream is namespace127.0.0.1:18787;
only host127.0.0.1:18443 is published. Exact frontend peer192.168.64.1 remeasured.

**PHYSICAL PASS:** another container's upstream connection refused; frontend403
with valid Host/Origin and spoofed headers; foreign Host/Origin/cross-site and
controls/sessions denied. Own-host non-loopback probes refused/timed out; a true
second-machine LAN test is **NOT TESTED**. Actual read role denied writes/DDL/
sequence use; all11 tables and sequences have identical before/after hash.
**FIXTURE PASS:**74 isolated container tests cover auth, events/SSE sanitization,
terminal timers and usage provenance. No synthetic jobs were inserted into V4.

V4 has33 retained containers: only DB/new observer/new frontend running,30 stopped.
Old token-mode pair/config/token/images retained unchanged for rollback. All22 V3
and4 retirement-rehearsal containers remain stopped; no retirement replay.
Current VPN state was queried but not reconfirmed; earlier Owner-reported OFF
remains historical. VPN ON/parity is NOT TESTED; no VPN/DNS changes.

One documentation writer in `/home/sonvh/pcp-observer828-adoption`, branch
`ai/815-observer828-adoption`. Accepted application checkout is separately pinned
at `/home/sonvh/pcp-local-adoption825-v4/releases/observer828-51349be/source`.
[Single checklist](../pcp-portable/consolidation.md),
[physical receipt and successor packet](history/2026-10-29-observer828-adoption.md),
[exact stop/rollback operations](../pcp-portable/local-operations.md#v4-shutdown-and-retention).
This documentation PR does not change application source or activate a baseline;
its own exact-head CI/PM review remains separate from accepted application CI.

## Original #824 — retired incomplete, never delivered

Job `51a11aa704362d84ae5c7b70e85741f1`, instance `pcp-local-pilot815-v3`:
`delivering / execution verified` → **`cancelled / incomplete_not_delivered`**.
Receipt `running/gen2` → **`blocked/gen3`**; same-owner lease `active/gen1` →
**`released/gen1`**. Original result/error/verification/history/usage remain intact,
including213 passing tests, one model call, input29,474/output3,968,
gross257,826/cached228,352/reportedUSD0. Assisted commit
`7b3833bdb06e59aabcad31e4ad2aed4ac5d003ea`, source
`0c968dd99199c73f3fbc89c0b59da168844e8f73`, baseline
`pcp-local-pilot-v3-verifier0c968-20261028` and verified snapshot are unchanged.
No remote branch/PR was published. Full before/after evidence is private at
`/home/sonvh/.local/state/pcp-retire824-execute-v1`; backup/manifest hashes are
in the sanitized receipt. Old binaries stay fenced/stopped and activation off.
Retirement resolves only this reservation; it does not authorize another job.

## Immediate next safe actions

1. PM independently reviews this physical receipt and documentation PR with its
   applicable exact-head CI; Developer never self-merges.
2. Review NEW immutable DRAFT `pcp-local-successor-828-51349be-20261029`, same-source
   release/image mapping, exact private registry/config diffs and task packet.
   All50 protected classes and both prior drafts preserved; active_revision null.
   Installed registries/autonomy stay draft/off. No mixed-source exception needed.
3. Separately authorize baseline approval/activation, operational project config,
   fresh source clone and expiring worker/Executor activation. Retired824 resolves
   only its old ownership; it grants no successor reservation or dispatch right.
4. Create a fresh actual issue for the three-path evidence-summary CLI/test/doc
   contract. Re-read trusted current main and regenerate body/base/goal bindings
   if docs merge advances main; keep the accepted51349 baseline/image authority
   distinct. Synthetic issue888 validation is not live issue approval.
5. Only under the next admission WorkOrder: scoped provider/publisher readiness,
   physical worker/verification/publisher validation and one clean admission.
   No credentials, admission, run-once or PCP-managed inference in this session.

## Active PCP issues and owner attention

GH-815/822/824 remain open; GitHub/Runtime evidence stays scoped. Dashboard is now
usable locally without a token. Source acceptance, physical adoption and next
admission are separate checkpoints. Legacy `A3B2_IMAGE_BUILD=STOP` is independent
of the three explicitly authorized V4 builds; `CODEX_LIVE=STOP` remains in force.

## Standing safety boundary

Chợ Nhạc/foreign workloads untouched; #752 PARKED and #595 G0 HOLD. No production,
force push, self-merge, new paid service, global VPN/DNS/trust-store change,
baseline rewrite, V3 worker restart, old activation reuse or model invocation.
Private-repo review/CI remains a process gate, not claimed server enforcement.

<!-- PCP:CONTINUITY:START -->
Decision6490872107: accepted51349 same-source images built; real tokenless HTTPS
observer adopted. Only DB/observer828/https828 run. Successor baseline/task DRAFT,
not installed/active/admitted. Next: independent physical handoff/PR review.
<!-- PCP:CONTINUITY:END -->
