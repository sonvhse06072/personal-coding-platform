# Postmerge V3 retirement and local observer follow-up — 2026-10-29

Execution authority: [DEC-PCP-815-RETIRE824-EXECUTE-V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6489438739).
Accepted source `ea6fc0ac5dd101068bf4fe6f8f8813495cc529bf` / mergedPR827.
Reviewed/merged tree `700dafdd92865dcbfde9ec561c9599ec8253e443` matches;
postmergeCI40827639082 executed four suites (5058 pass/135 skipped).
The whole execution record and merged maintenance procedure were read before
acting. No Developer acceptance/merge. Private0700 evidence root:
`/home/sonvh/.local/state/pcp-retire824-execute-v1`; private dumps, manifests,
approvals/connections0600. No full private manifests or credentials in this report.

## Actual execution receipt

**PHYSICAL PASS**, original transaction `2026-10-29T06:27:27.128313+00:00`.
Exact original DB/image/volume/network and22 stopped containers matched retained
inventory. The original DB has its named data volume and retained readonly initdb
bind; both matched. An initial overly strict helper assertion expected one mount;
it stopped before DB startup and was corrected against the retained two-mount
inventory. No real identity mismatch was waived. Original PG_VERSION17 verified.
Headroom at preflight:13,135MiB available RAM, swap0, approximately820GiB WSL free.
Docker child transport fixed to unix:///var/run/docker.sock, context/TLS redirection
removed; no global context or networking change.

Started only the original DB. Consistent custom pg_dump/list captured before
planning; the reviewed CLI captured its manifest once. Every original job/receipt/
lease field equals the retained final preimage. Fresh verification matched612-file
snapshot `50bb0d69ccfc270e2a2a935a95c30dc764cb1be6b1b8fabfd77f88a555f7ef81`,
Git clean HEAD `7b3833bdb06e59aabcad31e4ad2aed4ac5d003ea`, sole parent
`0c968dd99199c73f3fbc89c0b59da168844e8f73`, tree
`060958eca6aee88d3ce898a9243bc8b4ac99f258`. Proof was not refreshed.
Baseline remains `pcp-local-pilot-v3-verifier0c968-20261028`; issue-body SHA256
`7611145b19cde460f71ad769b699c88f2580b64e5ecd2be548c8e372d2ae8ce9` unchanged.

**PHYSICAL rehearsal PASS:** new `pcp-local-retire824-rehearsal-v1`, same pinned
PostgreSQL image, new named volume, network=none/no ports,1CPU/1GiB. Three role
placeholders execute only /bin/true, no credentials/workspaces/socket, readonly,
capabilities dropped and stopped. Restore used exit-on-error/no-owner/no-privileges.
All11 restored table contents and full business preimages equal original. Separate
copy-cluster manifest/approval; dry-run/APPLY/exact APPLY retry/read-only reconciliation
match. Post-retry rows unchanged. All4 copy containers stopped and volume retained.

Only then a separate original approval attested the real PM record, exact manifest,
accepted source and scope. Original dry-run succeeded; **one APPLY** succeeded and
same-manifest read-only reconciliation returned its exact outcome. No acknowledgement
uncertainty and no original APPLY retry. Complete expected postimages matched;
all other tables/row counts unchanged. Original after-dump/list retained. DB stopped;
all22 original containers remain exited with restart policy no. Frozen maintenance
checkout stays clean at accepted source; all code/docs work is in a separate checkout.

| Durable field | Before | After |
| --- | --- | --- |
| Job51a11aa704362d84ae5c7b70e85741f1 | delivering | cancelled |
| Disposition | unresolved delivery | incomplete_not_delivered |
| Execution/proof/result/error | verified, retained | identical original fields |
| Receipt | running/gen2 | blocked/gen3 |
| Same-owner lease | active/gen1 | released/gen1 |
| Model calls / input / output | 1 /29474 /3968 | unchanged |
| Gross / cached / reportedUSD | 257826 /228352 /0 | unchanged |
| Delivery attempts / test runs | 1 /2 | unchanged |
| Passing local tests | 213 | original proof preserved |

Only cp_jobs status/checkpoint audit/updated_at, exact receipt state/generation/
updated_at and exact lease state/updated_at changed. Original route/progress/task/
result/error/commit/proof/verification/timestamps outside these fields remain exact.
Job events32, quota collectors2, quota snapshots1 retained; no new job/event/model.
Historical824 is **retired incomplete/not delivered**, never successfully completed.
No assisted commit publication, issue-body mutation, new admission or provider login.

## Backup / manifest custody hashes

Canonical manifest digests differ from pretty-printed JSON file hashes.

| Artifact | SHA256 |
| --- | --- |
| Original before dump | `2e8f04c8217f0b6d13ad70b01df21f4c3952e1c51c315640d5fa44eab99ec5d9` |
| Original after dump | `08263e0bf9e705cbf62cb7635b63ee7f7a2e191e5b8d22a1b6c1fc34a260a97a` |
| Original canonical manifest | `c10def59b16a91d796f04fd464f5ee9a57ad368804f77f0359cbe9d3d32042ad` |
| Rehearsal canonical manifest | `ca725b595b9f9594d31d83a45caf6089e07fde3dd483f7ab9e194f6db1b0ccd1` |

Original database identity: `{"name": "pcp_local", "oid": "16384", "schema": "public", "schema_oid": "2200", "system_identifier": "7701584812351246361"}`.
Copy identity: `{"name": "pcp_local", "oid": "16384", "schema": "public", "schema_oid": "2200", "system_identifier": "7701972487631282220"}`.

Before/after dumps validate with pg_restore --list. The copy is explicitly mapped
to the original-before dump hash above. Audit retains the complete original manifest,
approval and outcome. Lost acknowledgement/rollback/conflict/concurrency/drift are
covered by accepted827 regressions (prior38 actual PG/Git cases plus CLI/audit tests),
not fault-injected into the original this session. No restoration over original is
a rollback option for an already committed retirement. Preserve all data/evidence.

## Exact resource disposition

Original namespace `pcp-local-pilot815-v3`: all22 stopped. Exact current resources:

| Resource | Full ID / name |
| --- | --- |
| DB | `3424d36e5de6b54fcae40eaa4c12557ff310fed23c26311930f991d1bfc9fcd1` |
| Runtime | `11ec281b7a6227559976f8d66c00ac2b70b8aff988a335fd57435154392ccdf4` |
| Router | `583ba00431bae454ee46b95a2c33a2f9f8a68f467b8c091302e44721a2aa8d9e` |
| Executor | `c3e49e48c95c38b50170d2ff5472c9742d20a85622a609d8fa80b4f4bbf2a835` |
| DB image | `sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27` |
| Data volume | `pcp-local-pilot815-v3-postgres-data` |
| Network | `064fff94593732cecb10011c7a602720f1e32335682a853c3f26d274f445ee09` /10.255.255.192/27 |

The remaining18 historical containers retain their full IDs in private preflight/
final-retention inventory; none was started/deleted. Old workers retain old binaries
and must never restart; installed activation remains disabled. New source fences
do not upgrade those binaries. Rehearsal volume
`pcp-local-retire824-rehearsal-v1-postgres-data` and root
`/home/sonvh/pcp-local-retire824-rehearsal-v1` retained, networknone:

- DB stopped: `20148d38281c671984d973e2b50c6ecf6cdb23d5ac5e9af29df9d2357cb512a0`.
- inert Runtime stopped: `0a8ae75fd99bb0f18a585b7f115abc1a844a28120a12108beb43cecf12373248`.
- inert Router stopped: `b030592fd0a01afa2aa0cc74ef08972b7c2e4be6e3b81d9121ade4feb8fe765a`.
- inert Executor stopped: `fefa371f90b5667a01d2d7b0226d7bbdfa6e7006fc80a438f36c18a5fa77b63f`.

V4 unchanged:23 retained containers, exactly these3 running; other20 stopped.

- `pcp-local-adoption825-v4-db`: `8b72a8d38971f4ddb67b6f7ce66e5289d5de63d2c861fac493964e67eff9a4e8`.
- `pcp-local-adoption825-v4-observer-live-configured`: `41aabe0d4c63f23056bf4bd0a0fdeb4c0b91cfe6dc296f20f71f3f55db596823`.
- `pcp-local-adoption825-v4-https-live`: `3b5cc02c77e96847c2e04446e802c3ee20fbb770d30956f42c7911f3a3443cab`.

Existing **https://localhost:18443/dashboard** is still token-authenticated.
Open the private0600 file
`/home/sonvh/pcp-local-adoption825-v4/observer-https/read-token` in a private editor,
enter it in the existing password form; never share/log it. Existing trusted browser
form login/logout/reconnect and SELECT-role denial evidence remain in the prior
[WorkReport](2026-10-29-retirement-https-v1.md). This session freshly checked HTTPS200
with default certificate verification, the login form, exact running identities,
all11 actual DB tables empty, SELECT on6 tables and no DML/public DDL/sequence USAGE.
No observer config/image/token/trust change. Latest Owner-selected VPN OFF evidence
is retained; VPN ON is NOT TESTED, not parity. No global networking changes.

Already executed shutdown was scoped to original/copy DBs; no worker start:

```sh
timeout 60 docker --host unix:///var/run/docker.sock stop --time 20 \
  3424d36e5de6b54fcae40eaa4c12557ff310fed23c26311930f991d1bfc9fcd1 \
  20148d38281c671984d973e2b50c6ecf6cdb23d5ac5e9af29df9d2357cb512a0
```

Do not rerun maintenance from this receipt. V4 exact scoped stop commands remain
in [operations](../../pcp-portable/local-operations.md#v4-shutdown-and-retention).
No deletion/prune/down-v. Private data/images/configs remain for independent audit.

## Source and fixture evidence; deployment boundary

Later [Owner request6489495501](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6489495501)
authorizes only the named local read exception. Source branch
`ai/815-local-observer-no-token` / `/home/sonvh/pcp-local-observer-no-token`.
Successful startup latch and exact local Host/Origin/peer checks precede SELECT;
invalid/worker/legacy configurations, forwarded headers, mode flips, controls,
foreign jobs and CORS preflights fail closed. Shared _require_session unchanged.
No form/session/cookie in local mode; token mode keeps Secure/HttpOnly/Strict login.

An added SSE regression exposed an adjacent seam: public_event bounded activity
text but replay/SSE did not apply the local snapshot redactor to retained messages.
A synthetic GITHUB_TOKEN message reproduced leakage; local replay/stream now reuse
snapshot sanitization and suppress raw event data. No stored evidence was rewritten.

**FIXTURE PASS:** fresh Chromium page fulfilled by the real ASGI application and
fake SELECT store, no cookies/token/form/session requests; three actual JavaScript
polls, denied control and no page errors. This does not test a deployed frontend,
real TLS or real DB for tokenless mode. Prior token-mode PHYSICAL evidence is
separate. Actual tokenless browser/container/LAN adoption is **NOT TESTED** pending
independent review/merge/postmerge and the next image/config checkpoint.

Required local root/Runtime/Router/Executor results and exact final-head four-suite
hosted run/jobs are in the PR handoff, including skips; none substitutes for PM
review or physical adoption. No new inference/provider/publisher operations.

## Accepted service-input comparison and next packet

Git trees/blobs compared5adfd120 → ea6fc0ac (including modes/requirements/Dockerfiles):

| Input | V4 object | Accepted827 object | Equal |
| --- | --- | --- | --- |
| `services/runtime` | `9470755ec6e4d43d90bb5938caef453a7d702af9` | `f5c780059c51c341f0aa80d02f4213cf127f55aa` | False |
| `services/router` | `a8fe2fd51ab2bbd6046cbc6d88435ba043d99d83` | `a8fe2fd51ab2bbd6046cbc6d88435ba043d99d83` | True |
| `services/ddev-executor` | `d599349233ae5e85ab46ac70105e0bb2c4286486` | `d599349233ae5e85ab46ac70105e0bb2c4286486` | True |
| `config` | `a328a76318fd03ed910384be2cfaa8fa03ddc1d7` | `a328a76318fd03ed910384be2cfaa8fa03ddc1d7` | True |
| `profiles/pcp-local/docker-compose.local.yaml` | `0cab3417436234a989e9b7b87552c6cc3854a713` | `0cab3417436234a989e9b7b87552c6cc3854a713` | True |

Actual existing images, each with truthful revision5adfd120:

- router: `sha256:5cba32331a6ae525193da8955043fd7a455583baca1950d450f2218fc06f5cf9`.
- runtime: `sha256:0391589bf34d58a3e3a4aae326539e9c46833fd44da591d4b57ca89904c0b1e2`.
- ddev-executor: `sha256:8a98a5057faeb80e0065f3884b71fa154cba897b5acdc28857b0d0a337465d9b`.

Runtime needs a new accepted-source build; Router/Executor unchanged inputs do
not by themselves create a supported mixed-source binding. The later Owner auth
decision explicitly combines the build with next reviewed adoption, so no interim
ea6 image was built. The [exact draft baseline/config/task packet](2026-10-29-successor-observer-packet.md)
and [next rollout procedure](../../pcp-portable/local-operations.md#tokenless-observer-next-adoption)
state pins, supported-binding gap, immutable succession, frontend/upstream
restrictions, meaningful physical probes and rollback. Draft schema/50 authority
classes/three-path contract shape passed; none was activated, admitted or run.
