# Current Project State and Handoff

Tier-1 mutable execution index; not project-frame authority, baseline approval
or physical attestation. Constitution, architecture and approved immutable
ProjectBaseline revisions outrank this snapshot. Reverify GitHub before action.

## Active work — GH-815 native Compose V5 SOURCE

Updated 2026-10-28. Accepted main is
`7a13a8e23de69b475ff3033660e9420cc581e93c` (PR-A #817 and PR-B #818 merged).
Actual push/main [run 40525215411](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40525215411)
executed all four suites at that exact SHA: root 1736 passed/1 skipped, Runtime
2403 passed/88 skipped, Router 132, Executor 663; 4934 passed/89 skipped.

[Physical Pilot V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6447369553)
stopped in Stage A before preparation: pinned DDEV start changes daemon-global
`ddev-global-cache` through its utility helper even with private HOME and custom
Compose mounts. Root remained absent; images/services/credentials/jobs/model
calls were zero. Approval for that original SHA expires 2026-10-28 22:52 ICT and
cannot authorize V5 or any resumed/repointed pilot.

[V5 Owner SOURCE approval](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6447953456)
authorizes exactly nine paths in one PR. Checkout
`/home/sonvh/pcp-815-native-v5-source`, branch `ai/815-local-native-compose-v5`.
Implementation prepares native Compose for existing Router/Runtime/Executor and
owned PostgreSQL 17; bootstrap has no DDEV prerequisite or lifecycle. It stages
fresh service/DB credentials with separate non-superuser Runtime database role,
retains exact build/image evidence, refuses collisions/partial roots and starts
nothing. Original registry/baseline templates remain draft/inactive.

PCP-only Executor verification uses the source-bound Runtime image's existing
Python/pytest/PyYAML/Git toolchain, an owned immutable snapshot, one non-root,
read-only, network-none bounded container and private tmpfs. Actual image and
container identity are checked before start. Tool readiness and positive passed
counts are mandatory. Container/snapshot evidence is retained; duplicate names
refuse replay. Existing Runtime admission/CAS/lease/model budgets/delivery and
PM review remain intact. Ordinary non-PCP stack-specific behavior is retained.

## Immediate next safe actions

Finish V5 fake/static checks and a Draft PR, obtain all four actual hosted
suite results at its exact final HEAD, then independent ChatGPT PM review.
The PR description/checks will carry the final immutable CI evidence. Developer
never self-approves or merges. No SOURCE/fake result is physical PASS. Available
Host pytest/service dependencies remain absent; no packages are installed.

After accepted merge and actual postmerge CI, propose separate **Physical Pilot
V2** with the successor SHA and native manifest. Mandatory future physical gates:
exact pins/tool hashes and PostgreSQL UID/volume compatibility; constrained
builder/disk/resource envelope; fresh names/network/volume; Runtime parent-secret
boundary and scoped credentials; dedicated schema-only initialization; real
Runtime-image timeout/pytest compatibility; approved immutable baseline, one fresh
Owner-authored issue and both nonempty mandatory phase lists including its test.
Bind verification_image equal to the exact owned runtime_image_id. Do not reuse
V1 approval, old jobs/receipts or any legacy physical data.

Native startup is opt-in and uses explicit project name, directory/env/file.
Inspection health uses original draft/inactive configs; only after an owned
Runtime stop and coherent baseline/registration/activation transition may a
separately authorized worker process start. Existing Runtime endpoints and
independent exact-head GitHub PM review/finalization remain the delivery seam;
queued/claimed is never model execution or acceptance. Preserve uncertainty,
receipt/job/lease/diff/counters; no duplicate invocation or Developer merge.

**HOST/DDEV/DB=STOP; CODEX_LIVE=STOP; A3B2_IMAGE_BUILD=STOP.** This V5 work runs
only source/fake tests, no real Docker/DDEV build/start, credentials, database or
provider/pilot calls. Rollback/removal is not authorized. Topical setup and
retention contract: [PCP Local](../pcp-portable/README.md).

## Active PCP issues and owner attention

- #752 remains PARKED; #595 G0 remains HOLD / NOT GO. No comparable accepted
  benchmark cohort or unattended local worker result is inferred from source.
- Historical F2/T01/Guardian/legacy jobs are not dependencies of the new local
  architecture. None are resumed, reset, queried or physically deleted here.
  Removal needs a separate exact ownership/dependency operation.
- #665: Owner accepted private FREE/unprotected-main residual. Hosted CI and
  exact-head PM review/expected-head merge are mandatory process gates, not
  claimed server-enforced branch protection. No runner/security-setting change.
- Guardian remains operationally parked; no recovery or service health is
  inferred. #493/#512 residual physical evidence is separate from this work.
## Standing safety boundary

**Chợ Nhạc strict no-touch:** no repository, worktree, DDEV, DB, job, lease,
  credentials or deployment access by this task. Accepted local risk is not
  authority over unrelated projects or shared resources.

<!-- PCP:CONTINUITY:START -->
## Automated continuity snapshot

No PCP-local live job is admitted or running in this SOURCE work. Registration
is draft, baseline inactive, and worker execution STOP. This replaceable block
is reserved for future evidence-backed Runtime publication; it grants no action.
<!-- PCP:CONTINUITY:END -->

Durable policy: [Operating Model](operating-model.md), [Roadmap](roadmap.md).
Practical setup and failure/rollback contract: [PCP Local](../pcp-portable/README.md).
Historical continuity remains available in Git and the linked issues; this file
replaces stale A3b execution history rather than accumulating another transcript.
