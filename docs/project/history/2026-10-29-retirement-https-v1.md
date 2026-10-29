# Integrated retirement and HTTPS WorkReport — 2026-10-29

Authority: [DEC-PCP-815-RETIREMENT-HTTPS-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6488558812),
Owner chat direction recorded through delegated PM. One writer, no subagents.
Branch `ai/815-retirement-https-v1`, base `bca7189a53cadba3feb38330dcfd658b95002048`.
The one PR carries exact final source/head/CI; this report does not guess its own
future commit. [PR826 acceptance/postmerge receipt](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6487825349)
verified again: CI40816963431, four actual suites,5032 passed/97 skipped. V4
application/images remain at accepted PR825 source5adfd120, not this docs merge.

## Evidence and remaining gates

| Class | Item | Result and limits |
|---|---|---|
| SOURCE | Default-dry-run operator retirement | Implemented; independent PM acceptance pending. No Engine/admin HTTP/schema initialization/provider/GitHub calls. |
| FIXTURE | Real disposable PostgreSQL + Git |38 cases PASS, including session-timezone normalization. Uses separate V4 fixture DB/random schemas, no original V3 data. |
| FIXTURE | Approval/custody/quiescence contracts |26 unit cases PASS; process doubles are not physical worker evidence or actual PM approval. |
| PHYSICAL | Accepted V4 DB/Runtime identity |PASS; exact original DB selectively started, distinct observer created, actual instance database still empty. |
| PHYSICAL | Observer database permissions |PASS; six SELECT grants, no table writes/sequence privileges; DELETE/public DDL/nextval each denied42501 after explicitly disabling transaction read-only. |
| PHYSICAL | Operator DB channel |PASS; actual authenticated PostgreSQL query through temporary private Unix socket/fixed docker-exec transport; no host TCP listener, socket removed on exit. |
| PHYSICAL | Nginx/leaf/chain/binds |Syntax and OpenSSL trust PASS; quoted regex, all temporary directories on noexec tmpfs, host IPv4loopback bindings. |
| LIVE | Trusted Chromium login/logout/reconnect |PASS: actual password form, default TLS verification, browser DELETE-session logout and offline/online reconnect. Exact NSS fingerprint independently rechecked after Owner import. Empty actual V4; no injected cookies. |
| LIVE | V3 retirement / new admission / model / publication |NOT TESTED and not performed; PM postmerge execution checkpoint required. No model invocations or run-once. |
| PHYSICAL | VPN matrix |Owner-confirmed OFF: DNS/TLS PASS; GitHub200, registry401/auth404/provider401 without credentials. ON pending Owner state change; no parity claim. |

## Retirement behavior and regression evidence

The old source could neither finish an unsuccessful campaign honestly nor free
its exact reservation without successful delivery evidence. The maintenance path
now uses existing cancelled/blocked/released vocabulary plus the explicit retained
`incomplete_not_delivered` audit. Full preimages and separate operator attestation
bind repository/project, instance/database cluster/OIDs/container, stopped workers,
job/issue/body/source/baseline/commit, generations, decision/reason/authority.
The CLI verifies its clean checkout against the approved source. The attestation
is trusted operator input after actual independent PM verification, not a URL/hash
interpreted as approval or a cryptographic proof of human identity.

The job retains original result/error, source/branch/workspace, verification tree/
modes/parent, assisted commit, usage/model/test counters and provider history.
Receipt increments once into blocked; same job-owned lease becomes released with
its ownership generation unchanged. Full rows are locked/compared in the same
transaction and project advisory lock as admission/claim/recovery. Before-images,
approval and identical repeat outcome survive COMMIT acknowledgement loss.

Real regressions exercise full job/receipt/lease drift (including timestamps,
proof/usage/source/body/baseline/generations), exact retry, conflicting authority,
foreign DB, active writer refusal, second-write rollback, commit-then-response-loss,
concurrent old claim/recovery, old activation denial before executor observation,
failed resurrection through update/lease/recovery, and real subsequent registration.
An arbitrary blocked receipt or tampered audit still blocks admission. Registration
uses synthetic reviewed authority in the fixture; it is not a live activation.
Normal successful PM finalization and non-PCP lease/activity suites remain required.

The [concrete backup/rehearsal/dry-run/apply/retention procedure](../../pcp-portable/local-operations.md#reviewed-retirement-procedure)
is preparation only. No original V3 database/schema/row, worker, lease, activation,
source/image, historical commit or counter was changed/read into fixtures. Preserve
job51a11aa704362d84ae5c7b70e85741f1 and assisted commit7b3833bdb06e59aabcad31e4ad2aed4ac5d003ea.
Its historical delivering/verified, receipt running/gen2, lease active/gen1,
one invocation/213 tests remain last-reported evidence, not fresh observations.

## Physical identities and custody

- Root `/home/sonvh/pcp-local-adoption825-v4`; private current evidence
  `/home/sonvh/.local/state/pcp-retirement-https-v1`; previous evidence unchanged.
- Accepted observer source `5adfd120dbd6aa4718cf9549ddc6fae0bab8f12d`, Runtime image
  `sha256:0391589bf34d58a3e3a4aae326539e9c46833fd44da591d4b57ca89904c0b1e2`.
- Original V4 DB `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8`,
  image `sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27`,
  volume `pcp-local-adoption825-v4-postgres-data`.
- New configured observer `41aabe0d4c63f23056bf4bd0a0fdeb4c0b91cfe6dc296f20f71f3f55db596823`.
- New Nginx frontend `3b5cc02c77e96847c2e04446e802c3ee20fbb770d30956f42c7911f3a3443cab`;
  official `nginx:1.28.0-bookworm`, immutable registry digest
  `sha256:552e7481ca93ffccd046aa658dbbed22caefbc09c66fa7cd247cbb90b8a5c609`.
- Existing private network `4f39b2458e6bbb9cee83bcee01053d4022bc9e49aa4877f3815c1a1161d571d5`,
  `pcp-local-adoption825-v4-private`, subnet192.168.64.0/27. No global network changes.
- Observer768MiB/1CPU, frontend128MiB/.25CPU, original DB1GiB/1CPU;
  serial fixture1GiB/1.5CPU. Non-root1000, read-only, cap-dropALL, no-new-privileges,
  noexec tmpfs. Frontend mounts only leaf/key/config; observer config/env contains
  no provider/publisher credentials or activation. No socket/source mount.
- Docker host publications are127.0.0.1:18443 and127.0.0.1:18787 only. Frontend
  shares the observer network namespace and reaches127.0.0.1:18787 there. No LAN
  ingress. Raw PostgreSQL bridge IP is not host-reachable; operator channel avoids
  adding DB ports/services or weakening credentials.

TLS private files under root `observer-https` are0600 in0700 directory. Existing
Windows mkcert CA generated a new localhost/127.0.0.1 leaf through supported mkcert;
issuer private key never enters frontend/repo. OpenSSL chain PASS; Chromium1243
with default TLS verification rejected the CA until user NSS trust is available.
Exact public fingerprint/store/removal and interactive Owner script are in
[operations](../../pcp-portable/local-operations.md#actual-v4-https-observer).
Never count ignored TLS errors or manual cookie injection as acceptance.

Verified URL is `https://localhost:18443/dashboard`; Owner reads local0600
`/home/sonvh/pcp-local-adoption825-v4/observer-https/read-token` privately and uses
the password form. No token in chat/Git/URL/logs. The accepted UI lacks a logout
button; the supported browser DELETE-session operation is documented separately.

## Diagnosed failures and retention

First observer startup lacked its required read-only config mount; it exited and
was retained, replaced by a distinctly named correctly configured observer using
the same accepted image. Initial Nginx syntax test parsed successfully but failed
creating fastcgi temp on read-only root; all Nginx temp paths moved to noexec tmpfs
and actual syntax test passed. Both failed containers/logs are retained.
Initial browser executable default mismatched installed revision; using installed
Chromium1243 explicitly exposed the real CA error. No TLS bypass was used. New
observer/frontend were stopped on browser gate failure while DB supported
independent fixtures. Owner's first import report was checked; missing NSS store
was reported and a precise follow-up requested. The second import was independently
verified against the exact fingerprint; subsequent real browser checks PASS at
2026-10-29 05:47:33UTC. The three scoped services may now remain for Owner use.

Source iteration diagnosed mock SQL/lock hooks needing the new shared lock while
preserving their original assertions. Real PG tests independently verify behavior.
Generated untracked Python bytecode from this worktree was archived privately to
keep image source contexts clean; subsequent tests disable bytecode. Continuity
keeps its required active-issues/next-actions anchors and legacy STOP vocabulary.
No foreign cleanup or service operation occurred.

## Handoff checkpoints

Final source head/CI and running-state receipt are recorded with the one PR.
The [corrected next-task packet](../../pcp-portable/local-operations.md#vpn-scoped-credentials-and-next-admissible-task)
proposes three allowed code/test/doc paths for a useful evidence-summary validator;
it preserves2–4-path/test requirements and does not execute that task. Successor
baseline stays draft pending final accepted implementation/image/input identities.
No provider/publisher provisioning, original V3 retirement, admission, PM self-review
or merge was performed by Developer. Chợ Nhạc and all foreign resources preserved.

Build-context integration: the existing protected inspect-image allowlist fixes
the Runtime package file set. Retirement therefore shares `pcp_local_recovery.py`
with the existing non-model maintenance seam; the CLI is separate under scripts.
No protected Dockerfile/ignore/authority checker/CI change or acceptance weakening.

Final local verification: root1741 passed/1 optional import skip; Runtime2504
passed/134 opt-in skips, plus the subsequently added reviewed-source CLI regression
passes in the26-case focused suite; Executor680 passed; Router132 passed.
Real Git/PostgreSQL/container retirement matrix38 passed separately (not skipped).
Hosted exact-final-head results are attached to the PR after all changes.

Physical retention receipt:23 owned V4 containers retained, exactly3 running
(DB/new configured observer/new frontend); all11 actual `pcp_local` tables are0
rows. Host loopback-only ports, private0700/0600 custody, noexec/capability/mount
boundaries and logs without token/DSN PASS. Screenshot and machine-readable
`final-physical.json`, browser/DB/channel/network proofs remain in the private
current evidence directory. Original V4 workers and prior fixture observer remain
stopped; no V3/foreign resource was started. Scoped stop commands are in operations.
