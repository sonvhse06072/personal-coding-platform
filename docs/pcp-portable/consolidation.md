# PCP Local consolidation execution checklist

Scope: Owner-delegated same-job non-model salvage (GH-815 comment 6475561621),
readiness/bootstrap/recovery repairs, and GH-822 read-only dashboard. One writer,
no merge, no additional PCP-managed model call or live pilot. Base/main remains
0c968dd99199c73f3fbc89c0b59da168844e8f73; approved baseline is unchanged.

Session start: 2026-10-28 17:22:46 UTC. Physical recovery deadline:
2026-10-28 19:22:46 UTC (earlier than original 22:53 UTC absolute ceiling).

- [x] Reconcile governing docs, issues 815/822/824 and original receipts.
- [x] Verify full IDs/ownership of 22 stopped containers and private network.
- [x] Preserve private preimages; verify all 612 tested-tree file hashes.
- [x] Start only owned DB, install exact accepted-source telemetry DDL as owner.
- [x] Commit exact existing three-file result with repository-local automation identity.
- [x] Locked/CAS same-job checkpoint reconciliation; guarded delivery blocked by retained askpass execution, remote absent; all 22 stopped again.
- [x] Reliability implementation and focused regressions.
- [x] Read-only dashboard projection/UI and representative browser fixtures.
- [x] Full local suites: root 1742; Runtime 2437/88 skipped; Router 132; Executor 680.
- [x] Browser fixtures: seven states, 1440/390 px, no overflow/page errors.
- [x] Concrete PM review/retained-pilot disposition/observer adoption packet.
- [ ] Draft PR delivery and exact-head hosted CI observation.

## Minimal implementation map

- Runtime `pcp_local_worker_loop.py`, `engine.py`: aggregate read-only readiness,
  activation normalization, durable verified-tree/commit stages, same-job recovery.
- Runtime `storage.py`, `telemetry_storage.py`: schema-only setup/permissions,
  atomic evidence CAS, primary-error preservation for telemetry side effects.
- Executor `main.py`: scoped identity, publisher/verifier capability readiness.
- Runtime `dashboard.py`, existing UI modules, `main.py`: scoped read projection,
  exact authenticated read-route allowlist; no orchestration/schema startup.
- Immutable Executor `github_askpass.sh` / publisher helper: no executable tmpfs generation.
- Source-only inspection context: four literal Runtime Python inputs, matching draft ignore digest and exact archive/original-oracle regressions; no build/authority advancement.
- Relevant Runtime/Executor/root tests; existing operational docs/current-state.

No authority, approved baseline, policy, CI workflow, global DNS/VPN, shared
resource or retained V3 code change. New source is reviewed before adoption.

## Order and acceptance

Reliability first; dashboard next; PM review/eligible merge after exact-head CI;
separate reviewed-source rollout; only then a separately authorized clean pilot.
Source and fixture success do not establish live V3 deployment or PM acceptance.

## Acceptance evidence

Local full suites: 4,991 passed / 88 skipped. The optional PostgreSQL/integration
skips remain explicit, not executed acceptance. Focused Runtime/recovery/dashboard
and continuity run: 244 passed. `git diff --check` passes. Browser evidence is in
`evidence/consolidation-dashboard/`; no live dashboard or VPN-state parity is
claimed. Router/Executor were unchanged after their successful full-suite runs.
Hosted head/run/jobs and the independent-review status belong to the Draft PR;
check the exact final head rather than reusing an earlier-head run.
