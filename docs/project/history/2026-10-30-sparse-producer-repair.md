# #835 sparse producer compatibility — WorkReport and rollout packet

## Authority and outcome

[PM6513180988](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6513180988)
commissions one SOURCE/isolated FIXTURE repair from accepted
P=`a4b273afb3af4b9b4fd23412a547230df0b93011` on
`ai/835-sparse-producer-compatibility`, worktree
`/home/sonvh/pcp-sparse-producer-835`. One writer; separate [Draft repair PR839](https://github.com/sonvhse06072/personal-coding-platform/pull/839).
PR838 remains operational evidence, unmerged at
`426a819f4ddf669d05c9dd4bf0577425066a67cd` (run40988953273, four executed suites).
Its [retained-state receipt](https://github.com/sonvhse06072/personal-coding-platform/issues/835#issuecomment-6513114230)
supersedes P's stale pre-adoption continuity. Main stays P; Q does not exist yet.

**Real producer A → ordinary B: FIXTURE PASS.** No live admission, model call,
worker deployment, issue edit, baseline activation, permit or credential operation.
No original A metadata/proof is regenerated. The dashboard stays available.
Exact repair head and final hosted run/job results are in the Draft PR verification
receipt, avoiding a self-referential documentation commit. PM acceptance is pending.

## Reproduction, implementation and evidence

The test fixture invokes the actual Executor `create_workspace` handler in a
separate interpreter, with a synthetic singleton registry/canonical repository
and only its external activation reader replaced. The handler performs its real
clone, no-remote branch setup and `sparse-checkout set --no-cone '/*' '!/.ddev/'`.
Tracked synthetic `.ddev/config.yaml` is omitted. Verified A is constructed only
after this production output exists, committed and finalized through existing
paths, then presented to ordinary B's readers/registrar.

On P, that test produced **RED** at `pcp_local_retained_git_configuration` after A
completed; its non-sparse counterpart passed. Initial fixture setup accidentally
left the canonical source on A's branch; it was corrected to canonical `main`
before recording this RED. That setup error is not counted as the reproduction.

The repair changes only retained validation plus its focused test seams. The helper
functions stay in the authorized worker module: root tests caught the historical
inspect-image closed inventory rejecting an extra module; keeping the helper in
the existing file preserves that contract without a Dockerfile/allowlist change.

- Local and worktree config are parsed by Git using explicit files, no includes,
  neutral cwd and a clean environment. Keys are normalized; duplicate keys reject
  even if equal. Git boolean aliases/case are handled explicitly (implicit true,
  explicit empty false); unsupported values reject. Behavioral keys default-deny.
- Only the producer worktree extension, two exact sparse settings, exact pattern
  bytes and omitted `.ddev` tree are supported. Older ordinary clones retain inert
  origin/tracking metadata support. Unknown extensions, includes, hooks, filters,
  monitors, external diff/attributes/excludes/worktrees/objects remain denied.
- Descriptor-relative, no-follow/no-atime reads reject symlinks, hardlinks and
  special files. A private byte snapshot is used for proof; no Git command runs
  against original retained metadata. This avoids executable-config races and
  original index refreshes. Full original content/mode/inode/owner/mtime/ctime
  preimages are compared afterwards, alongside the existing full-row recheck.
- Index flags are inspected with sparse interpretation disabled, before proof:
  Git otherwise clears skip-worktree on present files. Only `.ddev/` omission may
  carry that flag; assume-unchanged/fsmonitor-valid, unmerged/sparse-directory or
  unexpected entries reject. The original recovery proof algorithm runs unchanged
  in an isolated interpreter against the private snapshot: exact files/tree/modes,
  branch, sole parent and diff remain mandatory. No refreshed expected proof.
- Existing completed/PM evidence, source/baseline, receipt/lease/full-row checks,
  developer sibling isolation, ordinary source binding and registrar stay intact.
  Recovery/provider/Router/CLI/permissions/producer/CI contracts are unchanged.

| Class | Result | Measured scope |
| --- | --- | --- |
| SOURCE / RED | PASS | Actual Executor-produced sparse A rejected at P; plain A passes |
| FIXTURE / Git | PASS | 104 tests: plain and actual sparse producer, exact proof and repeat preservation, both config locations, external read/command escapes, duplicate/case/boolean rules, symlinks/hardlinks/FIFO/alternates, sparse/index/content/mode/parent drift and config races |
| FIXTURE / Git + PostgreSQL17 | PASS | 102 final repeatability cases, including actual sparse A through all eight readers and existing ordinary registrar; A bytes/config/index/metadata/proof/rows/counters unchanged; lease1→2 once, exact reacquisition, duplicate/concurrent/stale/crash/lost-ack/full-row and config-race rejection |
| FIXTURE / recovery adjacency | PASS | Final combined run141 passed (102 repeatability plus39 existing consolidation/claim-recovery PostgreSQL cases) |
| FIXTURE / pinned Git2.39.5 | PASS | 10 selected real-producer/proof/skip/omission tests in retained disposable Runtime, candidate source overlay; no rebuilt image or live data |
| FIXTURE / pinned Codex0.160.0 | PASS | Checked credential-free sandbox probe using actual unchanged adapter argv/config/environment: B read/write/Python/Git work; A reads/stat/list/symlink/Git/process escapes, provider data and network denied; zero inference |
| SOURCE / full local suites | PASS | Runtime2709 passed/267 skipped; Router132; Executor797; root1755 passed |
| SOURCE / hosted CI | Required | All four actual test steps at exact final repair head; links/counts in PR receipt |
| LIVE | NOT TESTED | No repaired worker image/build/admission/task delivery. Prior actual dashboard/adoption evidence remains PR838; this session checks availability/preservation only |

The kernel inotify watches on external include/attribute/exclude targets observe
zero OPEN/ACCESS events on rejected paths, and execution markers remain absent.
Config-race tests permit proof only in the previously validated snapshot, then
reject original drift without changing durable rows or admitting B. HTTP/GitHub,
provider/Router and external Executor observations in PG fixtures remain doubles;
real production reader/registrar/storage/Git functions run. This is not live
provider/publication evidence. The snapshot adds temporary disk/read cost; the
retained live A measured16MiB, but actual Q-image aggregate latency/capacity must
still pass the next rollout. No candidate image has been accepted here.

Two unrelated optional full-PostgreSQL baseline failures remain unresolved and
were not rerun: `test_initial_supervised_hold_rejects_mutated_ready_set`
(unsupported `continuation_key`) and
`test_pr_acceptance_does_not_hold_but_durable_merge_does` (stale initial-supervision
expectation). See [accepted #835 report](2026-10-29-local-repeatability.md).
Hosted/default suites skip optional DB tests and cannot establish these as PASS.

Private source-session logs/receipts: `/home/sonvh/.local/state/pcp-sparse-producer835`.
The sandbox used candidate app files in tmpfs over retained R image; no credentials,
network or mounts. Probe SHA256
`4fc2b695d23f7f102e5b15d2ad718ef64f438b1b49b3d2fbf3e2653d10f24091`;
unchanged adapter SHA256
`9570d160afc37801de1934e251de5e4de9870bb12b9420948b00a2fccb7fcd06`;
probe output SHA256
`8cbc1d62786c4d4e61dc9d96bc2bd14199aa51000f09d3b8d16e89db7658ecdc`.
The first probe loader used a newer tar API than pinned Python; it failed before
the probe. Explicit regular-file copying fixed that fixture loader without an
image/CLI change. Neither loader failure is counted as isolation evidence.

## Preserved operational state and scoped retention

PR838 records successful no-clobber quarantine of the exact118-byte config
(hash304afa3e), unchanged credentials and completed physical adoption, then a
readiness stop. Original file remains at V4 release
`releases/repeatability-P/rollback/disabled-codex-project-trust-304afa3e.toml`.
Never repeat quarantine, replace newly generated config, restore this file to
CODEX_HOME, or edit completed A's Git metadata to pass a guard.

V4 root `/home/sonvh/pcp-local-adoption825-v4`; canonical source P. Installed
P baseline `pcp-local-repeatability-a4b273afb3af-20261030` remains immutable.
Fresh activation is disabled intact at release
`rollback/disabled-activation-after-readiness-block.json`, SHA256
`1747f4d838038fd485d2fbac83e7f79c1b46762cc87c687f3e2b8d112f1e2acc`.
Old permits/activations and canonical S backup remain disabled/retained.
A831 `a8851f89dd3e4e582c697ec1fe6d8cdb`: completed/PM accepted,
delivered/gen3, released/gen1, counters1 model/2 tests/1 delivery. Retired824 remains
incomplete, never delivered. Prior full11-table/3-sequence and A manifests remain
PR838 evidence, not a new SQL audit in this source session.

Current exact owned resources (same IDs, no live service replacement):

| State | Resource | Container ID |
| --- | --- | --- |
| Stopped | Runtime P image `sha256:60c4b0ba3eed3429500df3a677a433e3dd0e8b62232909f9246901ad5418ac27` | `4acbed19a1878b6c2f7ed0a0022b52acc601fc5b3cfa90671c4d16d7874d4414` |
| Stopped | Executor R image `sha256:3cd95064283590141192d8d10216961239c35537c096d173d463130095c734bb` | `50fc20a1c3cdab401a4c5df6d1cbb4b59aebb05a5a7c2f500688997d850b9777` |
| Stopped | Router S image `sha256:422d41413115ce46c24a063a018f942dfd63e04205b167d0b97e6e4d10660319` | `f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6` |
| Running | Existing DB | `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8` |
| Running | Tokenless observer | `5d6b3e9b578745877f162f9c34e4413cc855a40a8c4281c32d3c6ed711b05411` |
| Running | HTTPS frontend | `d22a5bf0ef1adee16464c27ccab10bf3cf22dc7320fa65ed5a995fbd5ea4daf2` |

**https://localhost:18443/dashboard — loopback_readonly; no login/token/cookie.**
This session verified trusted TLS HTTP200 for dashboard and snapshot without a
cookie/token: exactly A831, completed, no B. Six live config/image/mount/lifecycle
preimages match (mount-list order normalized; rolling DB health logs excluded);
59 containers remain, 3 running/56 stopped. No new browser/VPN parity claim.
No observer swap, TLS bypass, trust-store/network/global configuration change.
The two reused disposable835 resources are stopped at handoff, retained:
PG `31c6e3c644409b6eced47f6fa19d72c86cd5f2ccb01efe366c6c4d1233674084`
(image `sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27`,
volume `pcp-repeatability835-postgres-data`), and probe
`6d30d5f751895679d44847f9bf9d43bdec15b1b2af6e23064ebf47a6c400373e`
(image `sha256:0b4d39efde3cdb12be9b650bfb74477bd4d800dcf3e457235e9bea4db2da6bde`).
Only isolated fixture schemas/roles were created/removed. No live DDL or SQL writes.

## One consolidated next rollout / pre-admission rebinding packet

This is preparation. The next PM checkpoint supplies exact Q, contract, baseline,
release IDs and execution authority; none is inferred from this Draft PR.

1. **Review and source hold.** Independent PM accepts exact repair head and all
   four executed suites, merges only this repair, verifies postmerge CI and records
   its real merge as Q. Release P hold only for that merge; establish Q hold through
   task837 delivery. PR838 and later evidence stay unmerged during that window.
2. **Reconcile before rebinding.** With all three workers stopped, privately capture
   exact image/config fingerprints, complete DB rows/sequences and A bytes/Git/proof/
   counters. Check issue837 and remote branch/PR plus local receipt/job/workspace/
   invocation/reservation: all must still be absent. Any artifact invalidates this
   pre-admission strategy; preserve it and return its reconciled state. Take a fresh
   consistent private `pg_dump` of the same V4 DB, hash it and verify a restored
   disposable copy. Preserve releases, canonical P, original S, current container
   definitions/images and quarantine/disabled activation with full preimages.
3. **PM changes SAME issue837 before admission.** Archive original full body/hash
   `c6f297e7b6a3977cd0897bf3521e0431895ca6855535f6dffb88aba3c2afb035`,
   P baseline/disabled activation and predicted ID
   `32ba6eb9c8e207c15459888f9365a3f7` as an **unadmitted proposal**. PM revises only
   `base_sha` to Q; keep key `pcp-local-evidence-cross-count-v1`, goal/mode and:
   `scripts/pcp-light-evidence-summary.py`,
   `tests/test_pcp_light_evidence_summary.py`,
   `docs/pcp-light/evidence-summary.md`. Approve a NEW immutable Q baseline; leave
   P and older definitions unchanged. Using `verify_issue`, `stable_job_id` and
   `claimed_source_receipt` from accepted Q, derive new exact body/baseline/job/
   branch bindings. It is a new ordinary identity, not recovery of the old predicted
   ID. No receipt reset, P/Q exception or recovery permit. Budget2/900s/3/USD0 and
   absolute expiry2026-11-01T17:00:00Z remain; expiry requires explicit disposition.
4. **Build only required inputs, serially.** From clean detached Q, use the accepted
   service-only archive/build recipe and pinned base/tool digests retained under
   `releases/repeatability-P`; create a NEW Q release directory, immutable source
   archive/hash, input hashes, `.iid`, labels and logs. Runtime changes, so build
   Runtime once at Q and use that exact ID for task verifier. Compare Executor/
   Router complete service inputs to their retained originals before reuse; if
   normal binding checks cannot truthfully accept reuse, build that service once
   from Q. Do not relabel R/S images or build the observer. No new instance or
   bootstrap/database initialization: this is same-instance succession.
5. **Actual-image gates before authority.** In authorized disposable no-credential
   containers, validate packaged source including the retained validation helper, pinned Git/CLI/
   pytest, actual Executor sparse producer→validator/proof and read isolation.
   Repeat immutable0755 askpass outside noexec tmpfs, non-root/read-only root,
   nonrecursive mounts/capabilities/resource limits, verifier positive and negative
   checks. Measure snapshot temp-space and aggregate eight-reader latency. Retain
   reports and fail closed on unknown/failed gates; fixture overlays in this PR
   are not a substitute for Q-image checks.
6. **Install exact reviewed diffs.** Preserve canonical P whole; install clean Q at
   the SAME canonical path. Append approved Q baseline and update only active_revision
   plus approved project/task verification inputs. Use the exact Q Runtime/verifier
   IDs and truthful unchanged service-input bindings; keep current observer binding,
   network/DB identity and existing scoped credentials. Retain/recreate only worker
   containers with full create records, then measure stable post-start fingerprints
   before writing newly approved activation. Do not refresh expected evidence to
   conceal a mismatch. Keep inherited-config guard and quarantine intact; no old
   permits or old activation restoration.
7. **Readiness then one ordinary admission.** Existing schema must already exist:
   SELECT-only table/sequence privilege/tool/source/ownership checks, no schema
   initialization. Check authenticated provider/publisher through supported paths,
   with Owner interaction only if genuinely required. Run the container-resident
   client below with PM's actual new ID; require aggregate ready=true and all eight
   trusted readers, unchanged A and absent B artifacts immediately before mutation.
   In the existing Runtime, send exactly one authenticated `POST
   /v1/pcp-local/run-once` using `httpx.post('http://127.0.0.1:8787/v1/pcp-local/run-once',
   headers={'Authorization':'Bearer '+os.environ['RUNTIME_API_TOKEN']},
   timeout=None)` from the accepted private operator
   harness. Never print token, use command-line secrets, or repeat an uncertain
   POST. Read supported status and reconcile durable receipt/job/remote state first.
8. **Delivery and retained shutdown.** Preserve the same new job/proof/counters
   through configured targeted/full verification, exact complete Git tree/sole Q
   parent, one real Draft task PR and all four actually executed exact-head suites.
   Observe A+B in the real trusted tokenless dashboard, fixed terminal timers and
   truthful usage. Developer does not finalize or merge without independent PM
   review. Capture full afterimages/private backup/remote receipts. Stop only exact
   adopted workers; disable new authority intact, retain images/workspaces/evidence,
   leave DB/observer/frontend available. Update one evidence PR on the Q hold.
9. **Rollback.** Before admission, stop new workers, disable their authority intact,
   preserve failed release evidence, and restore only the reviewed recorded P
   files/images/canonical preimages if PM's rollout authorizes it. P still has the
   sparse defect and stays stopped; rollback is not renewed dispatch authority.
   After any durable admission, no DB restore/receipt reset/counter rollback: keep
   job/lease/proof and reconcile under PM. Quarantine and A are never rollback targets.

Supported read-only command after accepted deployment (standalone script; placeholders
must be supplied by the exact PM release record, never guessed):

```sh
scripts/pcp-local-session.sh EXACT_Q_RUNTIME_CONTAINER_ID readiness \
  --job-id EXACT_RECOMPUTED_837_JOB_ID --phase admission --json
scripts/pcp-local-session.sh EXACT_Q_RUNTIME_CONTAINER_ID \
  --job-id EXACT_RECOMPUTED_837_JOB_ID --json
```

Current resource stop commands (already stopped workers; no Compose down/prune):

```sh
docker --host unix:///var/run/docker.sock stop --time 20 \
  4acbed19a1878b6c2f7ed0a0022b52acc601fc5b3cfa90671c4d16d7874d4414 \
  50fc20a1c3cdab401a4c5df6d1cbb4b59aebb05a5a7c2f500688997d850b9777 \
  f03edbd929aa323c011b990d51e30880b60e2fe68c908af10ca8e7db9cd3a6c6
# Reused disposable fixtures only; retain their containers and data volume.
docker --host unix:///var/run/docker.sock stop --time 20 \
  31c6e3c644409b6eced47f6fa19d72c86cd5f2ccb01efe366c6c4d1233674084 \
  6d30d5f751895679d44847f9bf9d43bdec15b1b2af6e23064ebf47a6c400373e
```
