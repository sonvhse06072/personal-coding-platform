# Current Project State and Handoff

Tier-1 mutable continuity, not baseline, merge or admission authority. Reverify
exact source/PM/physical receipts before acting.

## Postmerge retirement completed; local observer simplification candidate

Updated 2026-10-29. [PR827](https://github.com/sonvhse06072/personal-coding-platform/pull/827)
merged at `ea6fc0ac5dd101068bf4fe6f8f8813495cc529bf`; postmerge
[CI40827639082](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40827639082)
executed four suites: 5058 passed/135 skipped. Independent PM review and
[execution record6489438739](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6489438739)
supersede the premerge retirement hold. Clean frozen maintenance checkout
`/home/sonvh/pcp-retire824-execute-v1` remains at that exact accepted source.

**PHYSICAL PASS:** exact original V3 inventory/quiescence, private consistent
backup, full original preimages, restored-copy dry-run/APPLY/exact retry, then
one original dry-run/APPLY and read-only reconciliation. Original transaction
committed at **2026-10-29 06:27:27.128313 UTC**. Complete postimages match and all
other tables/row counts remain unchanged. DB after-backup retained; all22 V3
containers and all4 rehearsal containers stopped. No uncertain acknowledgement,
original retry, model invocation or publication occurred.

[Owner-requested local observer decision6489495501](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6489495501)
adds an explicit loopback-only read exception. One writer/no nested agents in
`/home/sonvh/pcp-local-observer-no-token`, branch `ai/815-local-observer-no-token`.
This follow-up combines implementation/regressions with the retirement handoff.
Only protected `services/runtime/app/main.py` and `docs/project/operating-model.md`
change under that decision. Frozen maintenance source and running observer stay
unchanged. Default token/worker/legacy/control authentication remains enforced;
local events/replay now reuse snapshot secret sanitization.

[Single checklist](../pcp-portable/consolidation.md),
[maintenance receipt](history/2026-10-29-retire824-execution.md),
[successor/config/task packet](history/2026-10-29-successor-observer-packet.md).
Source and browser fixtures do not prove tokenless deployment. Required final-head
CI and review are tracked by this branch's PR; Developer never self-merges.

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

## Existing V4 observer — unchanged token mode

**https://localhost:18443/dashboard** remains available on accepted source
`5adfd120dbd6aa4718cf9549ddc6fae0bab8f12d`, Runtime image `0391589bf34d…`.
DB/observer/Nginx are the only three running V4 containers. Read-token entry is
still required; private login and exact stop IDs remain in
[local operations](../pcp-portable/local-operations.md#actual-v4-https-observer).
Actual trusted browser login/logout/reconnect and SELECT-only permissions passed
in the prior physical session; this session rechecked trusted HTTPS and preserved
resource identities. The actual empty database is not a development activity claim.

## Immediate next safe actions

1. Independent PM reviews this follow-up's exact source/protected diff and four
   genuinely executed final-head suites, then handles eligible merge/postmerge CI.
2. Adopt one Runtime image containing retirement and the accepted local-auth change.
   The later decision explicitly defers the interim ea6-only build to avoid two
   builds. No candidate image was built/swapped here. Router/Executor retain5ad
   provenance; identical inputs do not silently authorize mixed-source adoption.
3. Review the frozen ea6 draft registry and concrete successor packet. Since the
   auth change is newer, generate a NEW immutable revision from its final accepted
   merge; never advance an old approved/draft revision in place or guess its SHA.
4. Apply only the next reviewed local ingress/config rollout, prove fresh browser
   tokenless polling and container/LAN rejection, retain token-mode rollback.
5. PM separately resolves final baseline/image bindings, activation and a fresh
   issue for the three-path evidence-summary task. No admission, run-once,
   provider/publisher login or inference was authorized/performed here.

## Active PCP issues and owner attention

GH-815/822/824 remain open; GitHub/Runtime evidence stays scoped. Retirement is recorded as incomplete; review/adoption/admission remain separate checkpoints. No routine repair approval
is needed. Legacy `A3B2_IMAGE_BUILD=STOP` remains independent of the named V4
observer permission; `CODEX_LIVE=STOP` still forbids PCP-managed inference.

## Standing safety boundary

Chợ Nhạc/foreign workloads untouched; #752 PARKED and #595 G0 HOLD. No production,
force push, self-merge, new paid service, global VPN/DNS change, baseline rewrite,
V3 worker restart, old activation reuse or PCP-managed model invocation. VPN
second state remains NOT TESTED until Owner selects it and actual probes run.
Private-repo review/CI remains a process gate, not claimed server enforcement.

<!-- PCP:CONTINUITY:START -->
Execution6489438739: original V3 retired incomplete, evidence retained, all stopped.
Decision6489495501: isolated source candidate for tokenless local reads; live V4
still token-authenticated. Next gate: independent source review and image adoption.
<!-- PCP:CONTINUITY:END -->
