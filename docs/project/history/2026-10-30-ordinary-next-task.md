# Ordinary next-task preparation — WorkReport and review packet

Date: 2026-10-30. Authority: [WO6525074512](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6525074512).
Engineering anchor72d71a80fa5a0ec2a742fb9ff1d15a3709cc632f;
branch `ai/835-ordinary-next-task`. One writer, SOURCE/FIXTURE only.
The Draft PR supplies exact candidate head and hosted CI; this report cannot name
its own future merge. PM acceptance and execution authority are separate gates.

## Outcome and dependency diagnosis

The candidate repairs three demonstrated defects using existing mechanisms:

1. `reconcile_commit` called `status`, staging/tree construction and other Git
   commands against the original workspace. A private index alone did not prevent
   `.git` directory/index/object metadata changes. Both plain Git and actual
   Executor sparse-checkout output reproduce the failure. Reconciliation and
   uncommitted delivery readiness now copy through the existing descriptor-safe
   snapshot reader, validate exact config/index/sparse contracts, inspect in a clean
   subprocess, and compare the complete original preimage afterwards. Bytes, modes,
   inode/owner/link identity and directory/file mtime/ctime guards remain intact.
   Commit-writing paths still write intentionally; no expected proof is refreshed.
   This is an isolated reproducer, **not proof of the historical B timestamp cause**.
2. Admission readiness launched the quota collector concurrently with trusted-source
   configuration checks. The collector starts `codex app-server`, so an independent
   failed check did not fence that process. The collector now checks the existing
   provider-home/system-config guard first. Hostile config reaches no subprocess.
   Configuration rejection is unchanged; no trusted-file whitelist or auth copying.
3. Observer assistance used only a legacy checkpoint name. Actual held verification
   and claim recovery recorded other durable checkpoints and projected false.
   Projection now recognizes those and verified-delivery recovery. It records
   assistance, not success; ordinary B/C remain false. No observer image was swapped.

The remaining installed-state blocker is explicit: retained legacy
`CODEX_HOME/config.toml` is still rejected. Accepted R2 already prevents the pinned
CLI's own project-trust write via exact in-memory project config. Actual CLI0.160.0
RED (prevention disabled) creates config; that retained home blocks the next adapter
invocation without a child. GREEN, repeat and a different next workspace in the
same clean home create no config. This is a reusable clean-home lifecycle, not a
blanket inherited-config exemption. The API account collector and developer must
both see a clean reviewed config boundary before ordinary admission.

Changing CODEX_HOME also changes `auth.json` custody. The inspected pinned CLI's
`--ignore-user-config` skips the user config layer but does not provide a separately
reviewed authentication home for this installation; app-server has its own loader.
Per-job auth copying/symlinking/login, global CLI changes or accepting arbitrary
inherited settings would change the credential/security boundary. None is added.
The minimal recommended future disposition is in Gate 2 below. Until accepted,
**ordinary installed C is BLOCKED**, even though fresh-home fixtures pass.

## Complete lifecycle contract

Paths below are relative to `services/runtime/app/` unless otherwise noted.

| Stage | Existing authoritative entrypoint / acceptance | Evidence and remaining boundary |
| --- | --- | --- |
| Source/frame/image | `TrustedReaders.authority/source` in `pcp_local_worker_loop.py`, `verify_issue` in `pcp_local_task_queue.py`; immutable issue/body/base/baseline, exact release observer | Real production helpers in fixtures; future accepted merge/image/baseline/task IDs unresolved |
| Config/provider/schema | `pcp_local_readiness.collect_readiness`, `CodexAdapter.require_isolated_configuration`, real `schema_readiness` roles/sequences | Real PG and actual CLI/container probes; real retained config and login not changed/tested |
| Eight readers | `TrustedReaders.readers/refresh`: project, baseline, isolation, provider, budget, writer, publisher, model_choice | All eight execute in real PG fixture; external source/Executor/Router/provider facts are synthetic |
| Receipt/registrar/lease | `RuntimeEngine.run_pcp_local_once` -> queue `record` -> `dispatch_pcp_local_once` -> existing atomic registrar; `run_admitted_job` owns running transition/lease | Finalized A -> ordinary B -> ordinary C; exact fresh identities, generations2/3; duplicate/concurrent/crash/reservation cases reuse real PG regressions |
| Producer/developer | Executor `create_workspace` actual subprocess producer; `run_admitted_job` -> `CodexAdapter.run` | Real sparse checkout/Git, real adapter arguments; synthetic provider response writes one allowed fixture test, no model |
| Mandatory verification | `RuntimeEngine.verify_pcp_local` targeted/full phases | Both execute real pytest in synthetic repository; transport substitutes for Executor container API, so not installed verifier evidence |
| Commit/proof | `verified_tree`, `commit_verified`, `reconcile_commit` in `pcp_local_recovery.py` | Exact complete tree/modes/sole parent; changed proof/index/config/ownership rejected; read-only original metadata preserved |
| Delivery/CI | Existing `deliver_pcp_local`, `retry_pcp_local_delivery`; remote reconciliation before uncertain writes | Synthetic branch/PR/CI responses, lost PR acknowledgement followed by read-only reconciliation; one developer/publish/PR call. No real task publication |
| PM finalization | `collect_readiness(phase='finalization')`, `finalize_pcp_local_review`; existing operator `session` | Real PG commit and exact retry/concurrency/full-row cases; synthetic independent review/CI; no self-approval |
| Observer/next task | `build_local_snapshot` from real recorded rows; retained-workspace reader before next ordinary registrar | Recovery assistance true, ordinary false; A/B full rows/workspaces unchanged when C completes; no old permit |

Fresh C is not a held/claimed recovery. Fixtures retain original verification,
progress and ownership history. Existing blocked receipts still block, and no model
replay follows uncertain registration, execution, publication or finalization.

## Reproduction and verification

Private raw logs and synthetic artifacts:
`/home/sonvh/.local/state/pcp-ordinary-next835-fixtures` (no credentials/live manifests).

| Evidence | Result | What was actually executed |
| --- | --- | --- |
| SOURCE / RED | Reproduced | `red.log`: two direct real-Git metadata failures; `red-pg.log`: two real PG readiness metadata failures and one held assistance failure; `red-quota.log`: collector reached despite hostile config. Initial PG startup errors are setup failures, not RED evidence |
| FIXTURE / focused | PASS | `focused-final.log`: 427 tests, 159.64s, actual isolated PG/Git plus existing recovery/admission/finalization/client regressions |
| FIXTURE / strengthened entrypoints | PASS | `entrypoint-final.log`: 30 tests, 28.70s; supported one-shot method and delivery retry, real metadata races/external-read guards, isolated project-policy fixtures |
| FIXTURE / actual accepted image + candidate adapter | PASS | `overlaid-cli-lifecycle.log`, `overlaid-cli-isolation.log`: real CLI0.160.0; synthetic SSE, no inference/credentials/egress. RED config write, strict retained-home rejection, clean repeat/next; deny sibling/config/auth/process-env/network escapes, allow current job/tools |
| SOURCE / required full verification | Recorded below | Four local suites plus actual final-head hosted suites in the PR; skipped optional tests are not database evidence |
| PHYSICAL / candidate release adoption | NOT TESTED | No image build or installed candidate. Overlay probe proves candidate adapter with the accepted toolchain, not a built release/provenance binding |
| LIVE execution | NOT RUN | No live worker/permit/baseline/admission/model/task publication/finalization; retained-resource inspection and normal-TLS dashboard GET200 only, no new browser/VPN/LAN claim |

The source/fixture files are the four Runtime application files
`adapters/codex.py`, `pcp_local_readiness.py`, `pcp_local_recovery.py`,
`dashboard_local.py`; relevant existing regression modules, sparse fixture helper,
CLI lifecycle probe and new `test_pcp_local_ordinary_cycle.py`.
The operational-policy fixture now uses a synthetic provider home: its initial
17 full-suite failures exposed host-home dependence after the tighter probe fence;
no assertion or production guard was weakened. New direct inspection tests watch
external files with inotify and reject drift after the snapshot.

Authority: implementation/tests are ordinary source scope; current-state and
portable checklist/operations are mutable continuity; this report is evidence.
No protected worker-loop, baseline, Constitution/architecture/security/budget,
provider policy, CI, Docker recipe, CLI pin or dependency file changes.

Known unrelated optional PostgreSQL failures remain tracked from the accepted
[repeatability report](2026-10-29-local-repeatability.md):
`test_initial_supervised_hold_rejects_mutated_ready_set` (unsupported
`continuation_key`) and `test_pr_acceptance_does_not_hold_but_durable_merge_does`
(supervision checkpoint expectation). They were reproduced on the earlier baseline;
this session does not repair or claim an all-PostgreSQL green suite. Hosted optional
PG skips do not resolve them.

Snapshot cost is a rollout prerequisite. The unchanged retained-sibling wrapper
already makes a scratch copy; the now-safe public reconciliation makes a second
copy inside it. Only one sibling is inspected at a time, but allow at least twice
the largest retained workspace plus Git scratch space and normal worker headroom.
A synthetic 32MiB file, two simultaneous 32MiB copies and original recheck took
0.093651s on the host; it is **not** real A/B latency, container peak memory or a
capacity guarantee. `snapshot-measurement.json` records it. Real retained-set
observation must fit the existing freshness/timeout/resource limits without
refreshing stale evidence or removing metadata checks. No protected reader rewrite
or new general snapshot subsystem is justified by this small-fixture result.

## Proposed task C — evidence input ambiguity repair (not implemented)

Backlog inspection found #835 repeatability and #595 HOLD as the relevant campaign,
not a ready new eligible light task. The existing evidence-summary CLI is a useful
bounded dependency: at this source, duplicate JSON member names silently replace
prior values before its validation. Synthetic input containing `class=FIXTURE` then
`class=LIVE` is accepted as one LIVE/PASS record. The input remained unchanged.
Reproducer/log are `task-c-ambiguous-synthetic.json` / `task-c-reproduction.txt`.
No task source/test/document solution was changed or prepared for either arm.

Goal: reject ambiguous duplicate JSON member names at the CLI boundary while
preserving its existing valid-input/output contract. Business value: avoid silently
promoting contradictory evidence and reduce PM review ambiguity.
Exactly three proposed allowed paths (satisfies current 2–4 paths with a test):

- `scripts/pcp-light-evidence-summary.py`
- `tests/test_pcp_light_evidence_summary.py`
- `docs/pcp-light/evidence-summary.md`

Acceptance: duplicate members in any input object fail deterministically with a
sanitized JSON error/nonzero exit, no partial counts or raw-input disclosure;
valid unique-key input and existing totals/class-outcome projections remain exact;
empty input, malformed/non-array input, invalid record/source SHA and source
mismatch keep their existing contracts; input bytes are unchanged on success/error.
Tests exercise raw JSON through the CLI, since an already-decoded dictionary cannot
represent duplicate members. Both mandatory configured phases must include the
exact test file; full repository tests, all four hosted suites and independent PM
review of exact task head remain required. No new service/network/policy authority.
PM must first bind a fresh issue/body digest, accepted source and immutable baseline.

## Minimal measurement and comparison

Use existing job/receipt/event/attempt records, sanitized operator logs, GitHub run
and review timestamps; append one private stage ledger, no telemetry service.
Each stage records UTC start/end, local `time.monotonic_ns()` elapsed on the same
process, source/job/PR identity and evidence link. Do not subtract monotonic clocks
from different boots. Missing boundaries/attention/usage/cash are null/Unknown.

Measure setup/build/backup/config work separately before an executable ticket is
released. Primary wall interval: PM releases an executable ticket with all authority
ready -> independently accepted outcome (record acceptance and durable finalization
separately). Record developer, mandatory verification, publication, hosted CI,
independent review and Owner waiting intervals; overlapping waiting must not be
summed twice. Durable developer duration is only one phase. Human ledger fields:
request reason/start/reply, actual active Owner minutes if supplied, intervention
count and assistance. Tool waiting is not Owner active work; source engineering and
historical B interventions are not C's operating time. No invented retrospective
zero. Record cumulative model/token/cache/test/delivery/repair counters and provider
observation/estimation provenance before/after; never reset them for comparison.

C is **repeatability-only**, not a Drupal/frontend benchmark or a controlled pair
in this session. No direct-Codex run is authorized. The next protocol-appropriate
pair is a fresh deterministic validation repair in the real
`pcp-g0-drupal-fixture` module, with Unit/Kernel/PHPCS/lint and exact CI/review gates;
select and freeze a new seed after code audit, not the exposed historical T01 task.
Do not register it or touch Chợ Nhạc/other local projects now.
Before any pair, PM must approve cohort/fixture/baseline and identical task/source/
criteria/model/effort/observed CLI/toolchain/quality gates, independent databases,
workspaces and contexts, and prevent solution leakage. Record as-operated version
mismatch separately, never normalize by relabeling. Use existing
`scripts/pcp-parity-benchmark.py` and the
[2026-10-10 protocol](g0-02-benchmark-protocol-2026-10-10.md) only when its schema
truthfully describes that cohort. Fewer than3 accepted pairs: no p50/p90;3–9:
descriptive p50 only;10+ with required classes enables metrics, not automatic GO.
#595 stays HOLD; no unattended-operation or benchmark PASS claim.

## One consolidated future execution packet — proposal only

**Gate 0 — accept source and reserve exact identities.** Independent PM reviews this
candidate and all four actually executed final-head suites, merges separately and
verifies four postmerge suites. Call that exact accepted merge **N (unresolved)**;
never substitute later HEAD. Resolve remote main explicitly. Propose immutable
revision `pcp-local-ordinary-c-<N12>-<approval-date>` with source N. Retain old approved
revisions untouched. A future reviewed registry/config diff appends that revision,
selects it only at the activation checkpoint, binds canonical/task/verifier N,
new C issue/body/goal/paths/job via production `verify_issue`/`stable_job_id`, and
configures both test phases above. No C issue, hash or activation exists yet.

**Gate 1 — custody/build/physical proof with execution OFF.** Take a consistent
private DB dump plus full A/B rows, receipts/lease/events/counters and descriptor-safe
workspace/config preimages; rehearse on a named isolated restore first. Reconcile
A completed, B completed/delivered3/released2 and824 retired incomplete. Preserve old
workers/images/source/config/quarantine/credentials/backups. Use a detached clean N
checkout, committed service-only archives, hashes of complete service inputs,
recipes and approved base pins. Serial Runtime/verifier build is required because
Runtime changed; rebuild Executor/Router only if complete relevant input/pin hashes
changed or the reviewed release decision requires it. Otherwise retain honest
original source labels and explicitly approve measured reuse. Never relabel old
images as N. Use the existing build recipe in the
[832 packet](2026-10-29-claim-recovery832.md#1-accepted-source-custody-and-build), with
fresh exact N parameters/paths, not its old permit operations. Record `--iidfile`,
archive/input/recipe/config digests and actual image IDs.

Use current approved Node/Python base digests and Codex0.160.0/OpenCode1.19.4;
no pin upgrade is proposed. Inspect shipped toolchain/adapter, non-root/read-only,
nonrecursive mounts, noexec tmpfs, immutable executable askpass outside tmpfs,
Docker20 corrections, resource limits, exact network peers and source binding.
Run the checked-in credential-free CLI/config/isolation probes in the **built**
Runtime, without candidate overlay, and the actual producer/validator/verifier
path. Measure full A/B snapshot capacity/latency before activation. New source
acceptance alone does not prove any of these physical checks.

**Gate 2 — one legacy-config decision, not recurring exceptions.** Recommended exact
future PM/Owner disposition: while all writers are stopped, capture full private
preimages of the known legacy B-generated Runtime-home config, compare with the
accepted historical digest `323b12e7fb0dce3cf5c4984aebf7dc513e89b9bf3991ac227dbc275716af10fc`
(118 bytes,0600,uid1000; historical evidence, not freshly inspected here), and authorize
one no-overwrite archival rename of that exact file into a new private evidence path.
Preserve bytes, owner/mode/timestamps, both earlier configs/quarantine and auth assets;
record before/after hashes and the reversible restore procedure before mutation.
The archive operation and its directory metadata changes must be explicitly included
in the approved preimage/afterimage contract. Any mismatch stops it. Credentials
stay in their existing Runtime custody; no copying/relogin merely for isolation.
Rollback may restore exact archived bytes only with stopped writers and absent
replacement config. Never overwrite newly generated configuration.

Then use the accepted in-memory no-write producer with the unchanged strict guard
for C and later tasks. Any newly created config is a preserved STOP needing diagnosis,
not another automatic quarantine. If this one legacy disposition is unacceptable,
the concrete alternative is a separately reviewed provider-auth/per-job-home custody
design; that is outside this tightening-only source work. Do not deploy just the
other repairs and discover this known blocker through another live trial.

**Gate 3 — one physical/authority checkpoint.** Preserve the current DB/observer/
HTTPS IDs; do not use a new instance to evade reservations. Reuse scoped credentials
only under the future decision; check real entitlement and executor-only publication.
Only genuine interactive expiry requires Owner login. No secret in argv/logs/chat.
Review exact worker create/config diff, stable post-start fingerprints, source/image/
observer/registry/config hashes, schema grants and all eight readers together.
Old held/claim permits stay disabled forever for C. A new finite ordinary activation
must name N, baseline, C issue/body/job, exact images/containers and budget.
Suggested small-task envelope for PM review: one initial developer invocation,
mandatory targeted/full phases, three changed files, no paid-provider fallback,
USD cash ceiling0, one task/lease,900s initial execution target and an eight-hour
UTC authority window starting at the later execution approval. Values are proposals,
not authority; no consumed counter reset or static elapsed-time Owner gate replaces
the existing healthy-progress/anomaly policy. No automatic expiry renewal.

**Gate 4 — ordinary commands, only after that decision.** Use the accepted
`scripts/pcp-local-session.sh` against the exact new Runtime ID. It reads the existing
container token internally. First `readiness --phase admission --json`, then ONE
supported authenticated `POST /v1/pcp-local/run-once` (not claim/held recovery).
A future private standalone client can call existing `session_request('run-once', {})`
inside Runtime; its fixed endpoint/token custody avoids shell secrets. Capture intent
before POST; on any uncertain response use session status/readiness and exact remote
branch/all-state PR/head/CI observations before another mutation. Do not replay this
POST, verification or model execution. Keep the same job and counters.

After actual tests, commit and real Draft task PR, require genuinely executed
exact-head CI. Delivery `ci_success` means await independent PM, not publish again.
Only after an exact independent acceptance and finalization decision:

```sh
# Placeholders MUST come from the later reviewed release/task record.
scripts/pcp-local-session.sh EXACT_RUNTIME_ID readiness \
  --job-id EXACT_C_JOB_ID --phase finalization --review-id EXACT_REVIEW_ID --json
scripts/pcp-local-session.sh EXACT_RUNTIME_ID finalize \
  --job-id EXACT_C_JOB_ID --review-id EXACT_REVIEW_ID --json
```

No `--apply` for finalize. Its bounded read-only reconciliation must establish
completed/pm_review_accepted, delivered/gen3 and C's exact released lease generation,
with original proof/usage/counters preserved. Unknown verification is never replayed.

**Gate 5 — observation, shutdown and rollback.** Keep
https://localhost:18443/dashboard tokenless/local/read-only. Verify actual C terminal
state, fixed timer, usage provenance and reconnect with trusted TLS. Observer label
repair requires its own reviewed Runtime-image adoption; until then retain the old
image and disclose its assistance-label limitation. Measure VPN only in the Owner's
reported state; an unmeasured second state/LAN is NOT TESTED, no global change.
Capture full afterimages and consistent backup, publish sanitized evidence, stop only
exact approved Runtime/Executor/Router IDs and disable new authority intact. Leave
DB/observer/HTTPS available. On mismatch stop dependent actions and preserve evidence.
Retained images/config are rollback assets; never restore an old DB over newer
ownership or reactivate a consumed/expired permit. No merge/self-finalization by Developer.

## Fixture inventory and retention

- PG container `b1af0bf9d30558a06499395cded49030ae01ee4fd9ed503aedd639fcc6e0f453`,
  name `pcp-ordinary-next835-fixture-pg`, image
  `sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27`.
  New volume `pcp-ordinary-next835-fixture-pg-data`, network none, no ports,
  task-only Unix socket,512MiB/1CPU/128pids. Actual PG17.11 with test-owned roles/schemas.
- CLI container `16915911492ffc9159b3458c8e248d655a40c831d28c7ba91be1fda513f21cea`,
  name `pcp-ordinary-next835-fixture-cli`, accepted R2 Runtime image
  `sha256:8018b3d1fe948e5f10b256aa5b52c95865c1788598f2463c551430e002259c77`.
  Network none, no binds/ports/credentials, uid1000,read-only,cap-drop ALL,
  no-new-privileges,512MiB/1CPU/256pids; tmpfs512MiB noexec/nosuid/nodev.
  Candidate source overlay in tmpfs; probe logs retained outside container.

Scoped stop only (retain containers, PG volume, private logs; no prune/remove):

```sh
env -u DOCKER_CONTEXT -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  docker --host unix:///var/run/docker.sock stop \
  16915911492ffc9159b3458c8e248d655a40c831d28c7ba91be1fda513f21cea \
  b1af0bf9d30558a06499395cded49030ae01ee4fd9ed503aedd639fcc6e0f453
```

Final verification/stop receipt is recorded below before handoff. No live V3/V4
mounts, data, credentials, source trees, authority or foreign workload was used.

### Final local verification and retention receipt

Required suites: Runtime **2734 passed /321 optional skipped**, Router **132 passed**,
Executor **808 passed**, repository **1755 passed**. Final changed real Git/PG
fixtures: **117 passed in66.06s**; earlier focused427 and strengthened-entrypoint30
results above cover unchanged integrated paths. `git diff --check` and the declared
path classifier pass; no protected path is changed. Exact-head hosted results are
recorded on the Draft PR after push, not inferred from these local checks.

The actual-image proof probe (`container-git.log`) passed uncommitted, committed,
retained-sibling and mode-drift cases with original metadata unchanged; three small
inspections took0.313090s. Final CLI probes attest candidate adapter SHA256
`b77ddb6e0cf2ce5d422053eb631d02e11adf96c86a6d555932c62feed9bba0f2`.
An earlier probe was shadowed by `/app` imports; its logs are retained as
`import-shadowed-r2-*`, not candidate proof. The corrected `/tmp` working directory
and explicit imported-adapter hash establish the final overlay identity. No build
or live adoption occurred.

At15:02:52 UTC both named fixture containers were inspected **exited**, their volume
and private logs retained. The two fixture IDs above are the entire fixture inventory;
no running fixture remains. Sanitized evidence manifest `evidence-sha256.json`:
`7f6bc7d41fdb322034692f91b13e45e130a3b6b352bbc1277f3a0351113c0a93`.

Scoped read-only inspection also reconfirmed retained Runtimee5d8a338,
Executor9cba24de and Routerf03edbd9 **exited**, with original finalization-era stop
times. DB8b72a8d3, observer5d6b3e9b and HTTPSd22a5bf0 remain **running** at their
original image IDs. A normal-certificate HTTPS GET to the existing dashboard
returned200; this is availability evidence only, not a new browser/reconnect,
completed-row/proof audit or candidate deployment. Full IDs/images/statuses are in
`stopped-inventory.json`; historical exact resource/proof custody remains in the
[finalization report](2026-10-30-held837-finalization.md).
