# Current Project State and Handoff

Tier-1 mutable continuity, not baseline, merge or admission authority. Reverify
source, PM decisions and current GitHub/Runtime physical state before acting.

## Active source WorkOrder #835

[WO835](https://github.com/sonvhse06072/personal-coding-platform/issues/835) and
[clarification6502893427](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6502893427)
authorize SOURCE and disposable FIXTURE work only. One writer on
`ai/835-local-repeatability`, `/home/sonvh/pcp-local-repeatability-835`.
Engineering anchor: **34c0e9ac99a057eef0a08a15f0c3828b3c1addfa**.

[PM receipt6502481811](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6502481811)
closed the stable-R hold: task PR833 merged at
`b1e94ee197bec2c8b5be09580d6cbf6a1be3f8fd`, evidence PR834 at the anchor above;
postmerge40912349585 executed all four suites (5254 passed/166 skipped).
GitHub main and both merge receipts were rechecked during #835. Main is **not
frozen**. This engineering anchor does not activate a successor ProjectBaseline.

The candidate adds authenticated phase readiness, a container-resident status/
finalization client, non-model delivery checks and stronger atomic finalization.
Real isolated Git/PostgreSQL regressions cover proof/ownership drift, duplicate,
concurrent finalization, rollback and acknowledgement loss. Exact tests and final
PR/CI receipt: [WorkReport/adoption packet](history/2026-10-29-local-repeatability.md).
No candidate image is deployed.

**Remaining boundary:** ordinary task B still fails `pcp_local_foreign_workspace`
with completed A retained. Actual offline Codex0.160 `:workspace` sandbox read a
synthetic sibling job's proof. Removing that guard would expose prior-job data.
The guard remains closed; B admission/repeatability is NOT demonstrated. The
WorkOrder's explicit boundary exception is used; the report gives one concrete
read-isolation proposal and its acceptance gates. No history was relocated or
rewritten to make admission pass.

## Retained completed #831 and deployed services

Job `a8851f89dd3e4e582c697ec1fe6d8cdb` remains **completed /
pm_review_accepted**, receipt **delivered/gen3**, lease **released/gen1**;
proof/checkpoint/audit and counters **one model / two verifier runs / one delivery**
are retained. Review5700617139 accepted task head
`4161ba059002c7aaf3fd35a88e3b0b80065c62b7`; task833 is now merged. The full
[execution/finalization report](history/2026-10-29-recovery832-live.md) is history,
including premerge instructions that the newer PM receipt supersedes.

Deployed, stopped Runtime/Executor remain repair
**R=1f9b5d50a18a7b93e6a22c6191d59985d4d3892a**. Original task/baseline/verifier/Router
remain **S=b97ade581fecad4db2146258e5ca02c3902189e0** and baseline
`pcp-local-successor-830-b97ade5-20261029`. Old activation and both permits remain
disabled intact; no restoration, renewal, worker start or replay is authorized.

**https://localhost:18443/dashboard — loopback_readonly, no login/token/cookie.**
Existing DB/observer/frontend remain available. Historical LIVE proof includes
completed terminal state, delivered/released ownership, fixed67.801641624s duration,
changing observation age, reported-cost/tool-calls Unknown versus estimated cost0,
and trusted Chromium reconnect. #835 does not claim a new browser/VPN test or
candidate deployment. Failed/cancelled LIVE UI, VPN parity and LAN remain NOT TESTED.

Private historical evidence: `/home/sonvh/.local/state/pcp-recovery832-live-v1`;
new isolated fixture evidence: `/home/sonvh/.local/state/pcp-repeatability835`.
[Operations](../pcp-portable/local-operations.md) and [one checklist](../pcp-portable/consolidation.md)
track exact retained resources, supported commands and the next review gate.

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

## Active PCP issues and owner attention

#835 is the active source WorkOrder. No interactive Owner login/VPN step is
pending. The retained-workspace read-isolation decision belongs in PM's combined
acceptance packet; it is not a request to continue ordinary engineering.

## Immediate next safe actions

1. Independent PM reviews the single #835 Draft PR and actual final-head CI;
   resolve the read-isolation proposal before claiming two-task repeatability.
2. After accepted merge/postmerge evidence, complete the consolidated adoption
   packet with the exact accepted SHA, new immutable baseline and separately
   authorized task/release bindings. No numeric next issue has been invented.
3. Keep current dashboard available, workers/permits disabled and all history.
   No fresh admission, model call, baseline activation or physical adoption here.

## Standing safety boundary

`A3B2_IMAGE_BUILD=STOP` and `CODEX_LIVE=STOP` remain effective outside their exact
finite approved campaigns. #835 does not lift these gates.
Chợ Nhạc/foreign workloads untouched; #752 PARKED and #595 G0 HOLD. No production,
force push, new paid service, global VPN/DNS/trust change, baseline rewrite or V3
restart. Unrelated H1b/A3B2/Codex gates remain. CI is a process gate, not server
branch protection; Developer never merges or self-approves independent review.

<!-- PCP:CONTINUITY:START -->
PM6502481811 closed R hold; PR833/834 merged, engineering main34c0e9a.
WO835 SOURCE/FIXTURE on ai/835-local-repeatability: phase readiness/operator client
and atomic finalization candidate; real Git/PG evidence and one rollout packet.
Sequential B still blocked by retained workspace: measured sibling-read boundary,
no guard bypass. No LIVE dispatch/deployment or historical state/permit change.
Completed831/delivered3/released1/counters1/2/1 and retired824 preserved; dashboard up.
<!-- PCP:CONTINUITY:END -->
