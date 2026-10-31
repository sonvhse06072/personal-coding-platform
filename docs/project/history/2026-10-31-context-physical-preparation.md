# H context preparation — WorkReport and inactive rollout packet

Authority: [WO6535472577](https://github.com/sonvhse06072/personal-coding-platform/issues/604#issuecomment-6535472577).
[Draft evidence PR847](https://github.com/sonvhse06072/personal-coding-platform/pull/847),
branch `ai/604-context-physical-prep-v1`, exact accepted H
`871fbf2485a1ffb89a88a69e1daaaca10e25b318`. PR846 merged after independent
review5719623294; postmerge [CI41142412566](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/41142412566)
checked: four actual test steps passed. Main is H; deployed baseline remains N85e415f1.
One writer, no delegated agents. Private evidence: `/home/sonvh/.local/state/pcp604-physical-prep-v1`.

Preparation start **2026-10-30T23:13:59.933001Z**, expiry **2026-10-31T07:13:59.933001Z**.
No automatic extension. This is preparation only; proposed authority is inactive and
uninstalled. [Machine-readable candidate/evidence packet](2026-10-31-context-physical-packet.json)
contains full image/container IDs, draft baseline definition, config hashes and task paths.
It is evidence_history, never an approved ProjectBaseline or deployment manifest.

## Actual outcomes

| Class | Result | Evidence and limits |
| --- | --- | --- |
| SOURCE | PASS | Exact H, unchanged Dockerfiles/CLI/dependency pins; complete Executor/R2 and Router/S service inputs equal H; packaged hashes/modes match H |
| PHYSICAL, read-only live custody | PASS | Full11-table/3-sequence V4 before/after match C closeout SHA e7ffb472…; A/B/C original byte/metadata snapshots unchanged; workers stopped; config/disabled authority unchanged;22 V3 containers stopped |
| FIXTURE | PASS | Fresh private backup restored to isolated PostgreSQL; all historical public rows/sequences identical before and after context rehearsal; restored real Runtime role passes9-table/3-sequence checks |
| PHYSICAL | PASS | One successful cached Runtime build, exact packaged files/modes, non-root/read-only/no-network, noexec tmpfs, immutable executable askpass; real Executor producer -> H validator; actual verifier17 tests, nonrecursive/read-only mount and effective noexec |
| FIXTURE in candidate image | PASS |59 tests: actual packaged ordinary admission/repair/review, real Git/PG, synthetic provider/GitHub transport; two diagnostic-driven repairs, missing/drift/hostile input, publication lost-ack reconciliation; historical public state unchanged |
| PHYSICAL measurement | PASS | Full H canonical context88,470 UTF-8 bytes;77.632ms snapshot+composition,15.946ms composition,32,480KiB process peak RSS. Synthetic task identity only, no admission |
| LIVE adoption/inference/task publication | NOT TESTED | No live worker startup, baseline installation, model/login, admission, completed-task replay, finalization or merge |

Actual candidate isolation uses the existing pinned CLI's credential-free kernel probe;
no `codex exec` inference. Provider tokens/semantic comprehension/internal CLI compaction
retention remain Unknown or unproven. Integration verification transport executes real
pytest in synthetic Git repositories; the separate physical verifier test proves the
container recipe. Neither fixture result claims a real task PR or hosted task CI.

## Exact custody, build and restoration

Fresh backup **228687 bytes**, SHA256
`8cc0944416678efeed4c3acc6f4b5678677ba4f4b5cf6e0d8f434ecbac39d50c`.
Archive listing verified; restore has no owner/ACL replay. Full public state hash before
and after: `e7ffb472d502d454813f12f6651215a1bb6a5cd618e6561d439b494f7b04b75b`.
Original A/B/C snapshots:

- A831 `a8851f89dd3e4e582c697ec1fe6d8cdb`: `7bfae0fb5c55ff9fb7f8806e15fac009bce444a96b59e2dcf8865707dda38d52`.
- B837 `ccb57d244cfd1fc069a98fd8c17734a1`: `e16a553257a771cb887a54cb9fe1970018abb1a6bb994887a87e3bc91fc397cc`.
- C843 `4d0f1df36be0b9b971c18b04af870950`: `dee964280100c635ec5bd27d70afd52ff9bfbca2747448cd7e991a75f89c444b`.

All three remain completed/pm_review_accepted, finalizedtrue, counters1/2/1;
receipts delivered/gen3, shared lease released/gen3. No counters or ownership reset.
Retired824's stored retirement evidence is retained; its stopped V3 database was not
started/requeried, so this is resource/evidence preservation rather than a fresh V3 SQL claim.
Original disabled authority hash9e4c8b0d… is unchanged; no old permit is reused.

Owned backing capacity was864,969,318,400B free; host876,310,650,880B, available
memory8,090,688KiB. Copied A/B/C file bytes13,959,138 /14,401,234 /14,777,399.
H validation of all three restored siblings:1.865771s, cgroup peak116,142,080B under
2CPU/3GiB/256pids/256MiB noexec tmpfs. No pruning or foreign workload inspection.
Copied fixture directories intentionally use0700; original directory metadata remains exact.

Runtime candidate:
`sha256:d9f553ac9a3376b33f0343f3f5ad014689ed383107ca64ceefd85a4a6f6c9d3b`.
One successful Docker build,3.233s using existing cache; no failed Docker build/artifact.
Frozen service archive SHA `d779995ed9cf5fca6758fb8564b6baf017a7ee2d3d4e0353e51f9e66e3ece648`;
build log SHA `1a37d8db2ba23067e747b0f387923abc522973343ae5618a0f42ab9656c1a8b3`.
Existing approved recipe uses the same pinned FROM digest override, Codex0.160.0 and
OpenCode1.19.4. No floating pull or recipe/package change. Actual Python3.11.2,
Node22.23.4, Git2.39.5, pytest8.4.1/PyYAML6.0.2. All278 packaged Runtime inputs checked.

Reused Executor image `sha256:78a752c0dbfc6bb9f4120660a0cba4ad6bc6dd1673b1240fd651597d6edf6aae`
retains source R2 `f02d9a14af33d9efeb99aa573d776aab3119dec1`; Router
`sha256:422d41413115ce46c24a063a018f942dfd63e04205b167d0b97e6e4d10660319`
retains source S `b97ade581fecad4db2146258e5ca02c3902189e0`.
Complete relevant service input diffs (plus Router model/policy inputs) are empty;
actual44 Executor/29 Router packaged inputs/modes match H. No relabeling as H.
Existing ordinary observation/verification contracts bind Runtime/verifier to H, while
honest unchanged service reuse and separately bound N observer are retained. Full live
readiness remains a future gate, not simulated by package equality.

## Rehearsal diagnostics and operator measurements

External operator: **gpt-6.1-sol**; effort setting and token/cache/cost usage **Unknown**
(not exposed). PCP-managed inference0; no live counters changed. Owner requests/actions0
observed; Owner active minutes Unknown, not inferred as zero from no prompts. Operator
elapsed includes inspection, setup, diagnostics, writing and CI waiting; start/closeout
UTCs and stage ledger are private. This is not an unattended/benchmark result.

There were **8 failed operator-script invocations**, grouped into six setup/research
corrections: initialized PG entrypoint socket mismatch (same retained volume restarted
after diagnosis, no reset); old build orchestration key mismatch before Docker build;
restore comparison JSON tuples/private directory modes/leading-slash sizing (three
checks corrected without refreshing original expectations); missing fixture `/config`
mount (preserved failed container, separate corrected fixture); proposed-task reproduction
using a different host Python version; measurement mounted directly below root (O_NOATIME
parent ownership guard correctly rejected it, then used an owned parent). No application
source repair or image patch. Failed fixtures/logs are retained, not represented as PASS.

The integration fixture uses shipped Runtime tests/app without overlay. Its synthetic
Executor subprocess dependency is the exact H Executor package mounted read-only, with
public H fixture config and isolated PG socket; no live config/credentials/workspaces.
A separate actual Executor-image producer test independently proves producer compatibility.
The measurement temporarily interprets draft metadata as an approved **synthetic** frame
only inside the no-network fixture; proposed files remain draft and uninstalled.

## Inactive successor and task proposal

Draft revision `pcp-local-context-871fbf2485a1-20261031-draft`, source H. Active revision
stays `pcp-local-ordinary-c-85e415f1f53c-20261030`; every old revision object is preserved.
All8 reference categories and authority rules are retained without section narrowing;
coverage is exact old-reference -> same reference at H, with every source/section resolved.
Full developer packet88,470B is within existing fixture capacity; no unsupported promise
of token savings. Private `packet/baseline.diff` and public JSON record the exact delta:
new draft only/source N->H, no active-pointer or existing authority/reference change.
Models/policy/project-registration files are copied into the draft only, exact hashes in
JSON; registration remains pcp-local only. No config/activation was installed or generated
with usable live authority. Future task baseline approval must be a separate PM decision.

No already approved, fresh, dependency-ready local ticket was found among inspected open
issues: #835/#604 are broader campaign work; G1/G2 dependencies and #595 HOLD remain.
Propose a **functional validation repair**, not a new evidence document: the evidence-summary
CLI crashes with an unhandled RecursionError on deeply nested JSON under actual candidate
Python3.11.2. The same fixture under host Python3.12 returns a typed schema rejection;
record the version difference, do not fabricate cross-toolchain parity. No solution written.

Exact body draft/hash,3 allowed paths and budget are in JSON/private packet:
`scripts/pcp-light-evidence-summary.py`, `tests/test_pcp_light_evidence_summary.py`,
`docs/pcp-light/evidence-summary.md`. Goal: deterministic sanitized INVALID JSON/nonzero
exit for nested arrays/objects; no traceback/input disclosure or mutation; valid counts,
duplicate-member rejection and all current invalid-input behavior preserved. Tests must
exercise raw CLI input on the pinned verifier Python. Both configured mandatory phases
already name that test file; full root and four hosted suites plus independent review
remain required. Proposed envelope3 model calls/900s/3 files/$0 paid spend. No issue or
job is created: future PM supplies immutable issue/body/baseline bindings, then production
helpers derive the real job ID. Synthetic900604 was used only to validate packet shape.

The shortest matched Drupal path remains a fresh validation seed in approved fixture
`pcp-g0-drupal-fixture`, using Unit/Kernel/PHPCS/lint and identical source/model/effort/
CLI/toolchain/quality gates, independent DB/workspaces and no solution leakage. Existing
`config/g0-fixture-only/projects.yml` is PARKED, DDEV disabled, autonomy off; current local
source intake is hard-scoped to PCP and bounded Python paths. This is a concrete registration/
provider-toolchain/authority gap. PM must commission the separate benchmark lane/cohort
under the existing G0 protocol; no scope allowlist or Chợ Nhạc change in this session.

## One next execution decision and shutdown/rollback

PM reviews this candidate image, draft baseline, exact config/source deltas, task value
and all evidence together. Decide whether to approve this task or select another useful
ticket, approve the successor frame and finite execution budget/expiry. No additional
Routine Owner command approval is proposed. Any genuine authentication step occurs only
under that later execution decision; retained credential bytes/modes are unchanged and
were not used for provider authentication here. Provider expiry/readiness is Unknown.

PM must keep main at H during binding/admission/delivery: review this evidence PR
without merging it into that stable-source window. The ordinary lane requires current
main == task base, and verifier image revision == task base. If PM advances main first,
this H task/image binding is no longer admission-ready; obtain a newly reviewed binding
and required image build rather than treating documentation-only movement as an exception.

After that decision: consistent backup/rehearsal -> check active writers and original
A/B/C/V3 -> reconcile service-input equality/source labels -> adopt exact H Runtime and
verification image while retaining approved existing observer/Executor/Router -> install
new reviewed baseline/config/task bindings -> scoped credentials -> all eight readers /
aggregate readiness -> one ordinary admission -> mandatory verification -> Draft task PR /
actual exact-head CI -> independent PM review/finalization. Reconcile ambiguous effects
read-only, never replay unknown model/test/publication. Do not restore old authority.
If service reuse fails a current guard, STOP and request the exact additional accepted-
source service build; do not relabel or weaken source checks. Observer remains N throughout
this proposal; future observer changes need their own reviewed adoption.

All15 task-owned containers are stopped, retained with their logs/data volume; full IDs,
including diagnostic failures, are in JSON. Exact isolated PG is
`5fcaefe2f542fcdfc702629dc7d1480652a64c711fa8df3d5fb698d84beb4f69`,
volume `pcp604-h-prep-pg-data`. Idempotent scoped stop (never cleanup):
```sh
(env -u DOCKER_CONTEXT -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH 
 docker --host unix:///var/run/docker.sock stop --time 10 
 5fcaefe2f542fcdfc702629dc7d1480652a64c711fa8df3d5fb698d84beb4f69)
```
Remaining original running resources: DB8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8,
N observerda6c434797c46a3312f0ca185b20e0b5fbb9234ce137aee9f81ebc2fb9241660,
HTTPS601c552bd0562b947529a591b84c70570a1eaa556fb43e50a8c2ae0d76e362aa.
Dashboard `https://localhost:18443/dashboard`, retained tokenless loopback-readonly.
No browser/deployment/VPN parity revalidation is claimed here. Original workers are
stopped with exact IDs in the prior closeout and this packet's custody receipt.

Rollback assets are the unchanged N image/configs, historical workspaces, disabled
original authorities and fresh private backup. This session installed nothing to roll
back. A later adopted H must stop exact workers and disable new authority intact before
reviewed restoration; retain new evidence/DB state, never reset counters or overwrite
completed jobs with an old dump. Required final PR CI is linked in the PR receipt; JSON
artifact is intentional so all four suites execute rather than document-only skips.
