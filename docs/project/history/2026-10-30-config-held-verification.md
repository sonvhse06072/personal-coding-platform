# Config lifecycle and held verification — WorkReport / review packet

## Authority and current state

[PM6516240084](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6516240084)
authorizes SOURCE/FIXTURE only, one writer, branch `ai/835-config-held-verification`,
worktree `/home/sonvh/pcp-config-held-835`, starting at accepted
Q `e3b19700dffcc3e2eae45bdde78230819466c9e1`. The separate PR838 operational
[report](https://github.com/sonvhse06072/personal-coding-platform/blob/1e5eafb0f9f308ef790bfb6d4a0d8e0d9bc09041/docs/project/history/2026-10-30-q-adoption837.md)
and receipt6516098356 supersede Q's stale pre-admission continuity.
[Draft repair PR840](https://github.com/sonvhse06072/personal-coding-platform/pull/840)
records the exact final source head and four genuinely executed hosted suites.
No developer acceptance or merge is implied by this evidence.

B837 `ccb57d244cfd1fc069a98fd8c17734a1` remains LIVE blocked/held, receipt
running/gen2, lease active/gen2, counters1 model/0 mandatory tests/0 delivery.
No live continuation, task PR/CI, approval, merge, authority restoration, config
quarantine or login occurred. A831 remains completed/PM accepted, delivered/gen3,
original proof/workspace/counters1/2/1 preserved. Current project ownership belongs
to B; A's historical released/gen1 is not the current lease. Retired824 untouched.
Main remains Q; future independently accepted repair is called R2, not yet known.

## Implemented behavior

Codex0.160.0 `thread/start` persists implicit project trust when its effective
profile permits writing the requested cwd, even with ignore-user-config. This is
visible in upstream pinned [thread_processor.rs](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/app-server/src/request_processors/thread_processor.rs).
The actual packaged CLI reproduced the write with synthetic SSE transport, no
credential/provider egress/inference. The test records child PID, kernel inotify
file events, config bytes and structured completion. It is a process/file lifecycle
reproduction, not retrospective syscall attribution for the historical B process.

The adapter now supplies **only exact current-workspace trust in memory** with its
existing explicit named restrictive permission profile. The pinned writer condition
is not entered. Fresh, repeated and next-workspace CLI turns finish with no config;
authentication custody remains the original writable CODEX_HOME. All inherited
config remains rejected, including trusted-looking metadata, foreign projects,
permissions, hooks/MCP/includes/model/provider changes, ambiguous TOML and links.
A second guard immediately before spawn catches config drift during preparation.
No cleanup, metadata whitelist, alternate credential home or CLI upgrade.
Existing B and historical304afa3e configs remain intact; this repair intentionally
does not grant permission to use either for a future developer invocation.

A separate default-off `PCP_LOCAL_HELD_VERIFY_ENABLED=owner-approved` operation
uses private `/config/pcp-local-held-verification.json` and
`/config/pcp-local-held-original-activation.json`. Ordinary activation and claimed
recovery must remain disabled. No HTTP caller can supply authority, workspace,
command, source or model. Default plan is read-only; the new path never imports or
calls a developer adapter and never enqueues. Existing fresh admission is fenced
while the held authority is installed. No new schema or service.

Eligibility requires the exact held error/attempt, one successful recorded Codex
attempt with usage, full job/receipt/lease preimages, original authority and baseline,
no verifier/commit/result, and an explicit PM legacy-returned attestation. The latter
binds progress and corroborating returned-log/shutdown hashes; it is **not** an invented
old checkpoint. Future ordinary calls retain returned-stage evidence even on hold.
Legacy B already has returncode0/failure_kind null and recorded usage; retained logs,
stopped-writer receipt and after-backup corroborate it. The missing item is a future
independently approved finite permit with exact accepted R2/image/config identities,
not missing historical mandatory verification. No such permit exists today.

Retained bytes are UNVERIFIED. A descriptor-relative snapshot validates Git config,
index/sparse semantics, links, hooks, branch/base and allowed paths before computing
complete Git tree/modes/diff/file identity plus a full workspace metadata digest.
The expected candidate is never refreshed after tests. A cross-process advisory
operation lock serializes network/Git work; the existing project transaction lock
and full three-row CAS fence every intent/result. Receipt and lease are not updated.
Original error/progress/checkpoints remain in the audit; model usage is unchanged.

Mandatory targeted/full phases use the original Q project configuration/verifier.
Each phase intent precedes its external call; each returned command and cumulative
active time are recorded before another phase. Unknown results remain unknown;
returned partial results/counters survive. Failure or uncertainty cannot trigger
coding or automatically retry tests. This permit permits one verification attempt.
Only genuine success and unchanged candidate establish `verified_uncommitted`, then
existing commit/reconcile and delivery/CI paths run. Lost commit/publication responses
use their existing distinct read-only reconciliation before any further writes.
No self-finalization. No retry of uncertain verification is implemented by this permit;
a later explicitly bounded test-work disposition is required if that state occurs.

Implementation stays in existing Runtime recovery/readiness/worker/engine/operator
seams. The held logic was consolidated into `pcp_local_recovery.py` after root tests
caught the historical closed app-input inventory; no historical image allowlist or
CI policy was changed. Executor adds only private held-authority reading and exact
release observation. Shared range/image validation keeps claimed-only eligibility
unchanged, and proves task Q versus Runtime/Executor R2. Router may retain its true
older source only with full input-history equality; verifier remains the original Q
image. Task paths cannot have changed anywhere in the repair range.

## Executed evidence and limits

- SOURCE: local full suites and final exact-head hosted results are recorded in
  the Draft PR receipt. Hosted skips are reported explicitly; CI is not task837 CI.
- FIXTURE: real Git/PostgreSQL eligible success, hostile config/hooks/index/links,
  content/mode drift, typed full-row/ownership drift, concurrency, rollback, lost DB
  ack, partial/unknown/failed tests, commit lost ack and synthetic publication lost
  ack. Adapter sentinels fail on any model call. Actual A→ordinary B uses all eight
  readers/registrar, then phase-aware non-provider readers for held verification;
  original A bytes/metadata/proof/rows remain unchanged.
- FIXTURE: actual Codex0.160.0 complete RED→GREEN plus repeat/next workspace,
  credential-free loopback synthetic SSE in network-none container. Candidate adapter
  overlay is explicit; this is not a new built/deployed Runtime. Existing sandbox
  probe still denies sibling/provider/process/Git/network escapes and permits B tools.
- FIXTURE / actual Q image: private `v4-after.dump` restored into isolated
  `held837_rehearsal_v1`. Original B eligibility passed; immutable candidate copies
  ran actual Q targeted13/full13 tests and supported commit. Fixture paths were
  explicitly relocated; original rows/files were never mutated. A copy and original
  A/B full manifests remained unchanged. No remote publication or model in rehearsal.
- LIVE: preservation/availability only. Workers off, authorities disabled; observer
  image/config unchanged. No candidate deployment, browser reacceptance, VPN parity,
  real auth refresh or task verification/delivery claimed. Synthetic home writes show
  the fix does not make authentication storage read-only; no real login was requested.
- Two unrelated optional PostgreSQL supervision failures remain tracked from #835;
  they were not rerun or folded into this repair.

Local suite receipts: root1755, Runtime2722 (313 opt-in skips), Executor808 and
Router132 passed. Final request-correlation coverage additionally passed6 cases;
the exact final-head hosted receipt on this PR is authoritative for the final tree.
Focused held/readiness/HTTP/Git/PostgreSQL50 and Executor binding/private-file28
passed; returned-stage regression7 passed. These sets overlap and are not summed.
Selected held-work PG cases executed in the isolated local PG runs, not hosted CI.
Other optional skipped coverage is not claimed; the known supervision gap remains.

The restored backup SHA256 is
`321cac271486da2927c5185a1053a807bddc68bfae2a861dbfa65c208669ba6c`.
The rehearsal ran before the final module consolidation/request-correlation audit;
final real-PG regressions cover those code changes. It is not a final R2-image test.
Final read-only LIVE comparison matched the complete retained database/sequence
snapshot and both original workspace manifests; configs/authority/resources matched.
HTTPS returned200 with ordinary certificate verification0, no ignored TLS errors.

Private evidence `/home/sonvh/.local/state/pcp-config-held-835` retains logs, source
inspection, original/restored preimages, rehearsal bindings and fixture identities.
Initial synthetic SSE lacked total_tokens and failed completion parsing; corrected
fixture then completed. An initial unreachable transport timed out after producing
config; it was never treated as successful CLI operation. Root test invocation
initially recursed into all service directories; corrected invocation is `pytest tests`.
These diagnostic failures are distinct from final acceptance checks.
The same-workspace repeat probe initially hit the fixture-only128 PID limit
(`pids.events max=7`); the existing Q worker uses256. Matching that bounded limit
made RED, fresh GREEN, same-workspace repeat and next-workspace turns all complete.
The fixture stayed network-none, read-only, non-root and512MiB. No live limit changed.
Continuity checks caught omitted stable headings/index wording; these were restored.

## One executable next rollout packet — PM execution checkpoint still required

1. Independently review the entire repair, actual exact-head CI and this packet.
   PM records accepted merge R2/postmerge CI and finite non-model authority. Do not
   invent R2, change issue837/body/base Q, rewrite Q baseline, renew old activation,
   or reuse claimed recovery. PR838 remains evidence-only.
2. Reconcile exact stopped current workers, original A and B full rows/workspaces,
   both configs, disabled authorities, ownership running2/active2 and remote absence.
   Take fresh consistent private backup and restore rehearsal; never restore over live.
   Record full original activation bytes/hash and exact current candidate from the
   read-only `candidate(workspace, task)` helper. PM reviews these UNVERIFIED bytes.
3. Serial build Runtime and Executor at accepted R2 with existing pins/limits. Keep
   Q canonical task checkout and Q verifier image43e4baf6; fetch R2 objects into the
   canonical repository without changing its Q checkout so range checks can run.
   Keep Router at its truthful source only if every intermediate input comparison
   passes; observer stays unchanged. Verify actual packaged images, immutability,
   noexec/nonrecursive mounts, askpass, permission boundary and stopped rollback IDs.
4. Prepare a NEW private held permit version1. Exact fields are enforced by
   `HeldPermit`: decision_id/execution_record, not_before/expires_at (finite <=24h),
   original_activation_sha256, full before {job,receipt,lease}, candidate,
   invocation_attestation {kind=independent_pm_legacy_returned, attempt=1,
   progress_sha256, returned_log_sha256, shutdown_sha256, returncode=0,
   provider_failed=false}, repair_source, complete repair_commits/repair_paths,
   roles {runtime,executor,router,verifier} with exact image/source and worker
   configuration digests, verification_seconds10..900. No paths/images/hash
   placeholders may be installed. Files0600, regular/single-link/owned, original
   activation retained byte-identical and OFF. Do not copy credentials into fixtures.
5. Retain old containers; adopt only reviewed Runtime/Executor. Finalize real
   post-start fingerprints with no active execution authority, then install the
   independently reviewed held permit atomically. Keep ordinary activation/claim
   permits disabled. No Router/provider/model readiness call is needed for this
   non-model operation; current GitHub main must equal R2, task/canonical/verifier Q,
   all existing source/ownership/isolation/publisher/schema checks must pass.
6. Use the supported container-resident interface, exact new Runtime ID from the
   accepted release record. These commands are preparation, **not permission now**:

   ```sh
   scripts/pcp-local-session.sh RUNTIME_ID readiness --job-id ccb57d244cfd1fc069a98fd8c17734a1 --phase held-verification --json
   scripts/pcp-local-session.sh RUNTIME_ID verify-held --job-id ccb57d244cfd1fc069a98fd8c17734a1 --json
   # Only after the future PM execution checkpoint and matching read-only plan:
   scripts/pcp-local-session.sh RUNTIME_ID verify-held --job-id ccb57d244cfd1fc069a98fd8c17734a1 --apply --json
   ```

   GET `/v1/pcp-local/held-verification` is plan/status; POST same path is one
   authenticated named operation bound to job_id/permit_sha256 from the plan, no model. The client sends at most one
   POST and a bounded read-only GET even for protocol errors. Inspect durable
   phases/afterimages before any further request. `verifying` with missing result
   is UNKNOWN, never PASS and never replays under this permit. Failed verification
   stays held. Verified-uncommitted/commit-uncertain use existing authenticated
   `/v1/pcp-local/deliver` reconciliation under the same finite held authority;
   no `/run-once`, new job, manual SQL or manual Git publication.
7. Require exact tested tree/modes/sole Q parent, real Draft task PR, all required
   hosted suites at task head, real dashboard and retained A comparison. Independent
   PM review/finalization remains separate. Do not interpret fixture CI/publication
   as that future task acceptance. Original model usage and active ownership persist.
8. Capture after-backup/rows/workspaces/log hashes; stop only current worker IDs,
   disable the held permit intact, retain all assets. DB/observer/frontend may stay
   available. Before any B operation, worker rollback is reversible with authority
   off; after any intent/result, never roll DB/counters/workspace back. Reconcile
   the same operation. Historical config disposition for a later fresh task remains
   explicit; this code never quarantines it automatically.

## Retained resource identities and stop commands

Live root `/home/sonvh/pcp-local-adoption825-v4`; current Q Runtime3c8e847d,
Executor50fc20a1, Routerf03edbd9 remain stopped. DB8b72a8d3, observer5d6b3e9b,
frontendd22a5bf0 remain available. Full IDs/network/volume/backup hashes and exact
live stop commands are retained in the linked Q execution report above; no resource
was replaced here. Dashboard **https://localhost:18443/dashboard**, tokenless
`loopback_readonly`; no login/cookie. No global networking/trust or foreign changes.

This session's scoped fixture shutdown (retain containers/volumes/files):

```sh
docker --host unix:///var/run/docker.sock stop --time 10 \
  c151b1c9cf0d83954ff5018c77c822f94efd140b78e5eb317462c7b5542313d6 \
  31c6e3c644409b6eced47f6fa19d72c86cd5f2ccb01efe366c6c4d1233674084
```

Both actual-Q verifier fixtures already exited0 and remain retained:
`1ed6e549700f34d2bd49b2d06366c8cc0bf69844681628cc15fa71d7382adca0`,
`2f8317aa42db6874d2707799f83ad5b20703d8bb2d6b5531de9e6c823bac828c`.
PG volume `pcp-repeatability835-postgres-data` and restored databases retained.
Final shutdown verified both IDs stopped: PG exit0; the sleep-only CLI probe was
stopped with the scoped timeout (exit137, no OOM claim). Verifier fixtures exited0.
No cleanup/prune/Compose down. Source acceptance still does not deploy R2.
