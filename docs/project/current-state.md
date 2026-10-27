# Current Project State and Handoff

Tier-1 mutable execution index; not project-frame authority, baseline approval
or physical attestation. Constitution, architecture and approved immutable
ProjectBaseline revisions outrank this snapshot. Reverify GitHub before action.

## Active work — GH-815 PR-B SOURCE implementation

Updated 2026-10-27. Checkout `/home/sonvh/pcp-815-pr-b-source`, branch
`ai/815-trusted-local-pr-b`, base `f9bf5fd1a62810c4dcc429bae690fe82ce3d6e29`.
[PR-A #817](https://github.com/sonvhse06072/personal-coding-platform/pull/817)
is merged and accepted. Its actual postmerge push/main
[run 40504187048](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40504187048)
executed all four suites successfully at that exact main SHA.

Authority: [V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6438475541),
[V2](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6438904126),
and verified [V4 Owner approval](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6443075044).
V4 adds only Executor `app/main.py` and `tests/test_workspace.py` to the nine
Runtime source/test paths. This T1 continuity file remains permitted. No scope
expansion or source change to registry, baseline, Compose or Constitution.

Implementation prepared in [Draft PR #818](https://github.com/sonvhse06072/personal-coding-platform/pull/818),
not yet independently SOURCE-accepted:

- Dedicated `pcp_local_worker` startup checks installed operational authority;
  startup starts no scheduler, model, DB initializer or historical replay.
  Authenticated one-shot ingress uses the existing source receipt, CAS, queue,
  project lease and CodexAdapter. Generic legacy controls remain denied.
- Concrete readers in the existing worker module use fresh registry/baseline/model/policy files, authenticated
  Executor/GitHub, Docker inspection through Executor, PostgreSQL writer state,
  Router choice and subscription CLI quota. Environment flags alone cannot
  install authority. Consumed execution receipts cannot automatically replay;
  uncertain outcomes retain the original job, lease, diff and counters.
- PCP verification uses an Executor-owned source copy and controlled DDEV
  configuration, private network/cache, pinned web base and generated Python
  test image extension. Developer sparse clones omit legacy `.ddev`; verification
  never uses source hooks/custom Compose. Non-PCP behavior is retained.
- Mandatory checks must actually execute with positive test counts. Disabled,
  empty and all-skipped verification cannot pass. Draft PR delivery reuses
  existing GitHub/CI transport and requires the exact `tests` workflow HEAD;
  independent PM acceptance remains separate from model success. The dedicated
  PM endpoint fetches the exact GitHub review and four executed suites, applies
  existing standalone PM merge gates, and atomically finalizes the original
  receipt/job/lease. It records eligibility but never merges. Exact retries
  acknowledge the persisted outcome without replaying execution.

## Immediate next safe actions

Independent ChatGPT PM review of [PR #818](https://github.com/sonvhse06072/personal-coding-platform/pull/818):
verify the final exact HEAD against all four actual
[hosted checks](https://github.com/sonvhse06072/personal-coding-platform/pull/818/checks)
and the developer evidence in its description before any eligible merge.
Developer does not self-approve or merge. The PR description/checks carry the
final head-specific CI receipt so this T1 index does not claim a future SHA's
result from an earlier run.
GitHub/Runtime evidence is separate: no live Runtime was queried or activated.
Local pytest/service dependencies are absent; no Host packages were installed.
Python AST checks, `git diff --check`, 17 fake bootstrap unittest cases and the
historical in-memory context integrity check pass. Actual
[run 40516561074](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/40516561074)
executed all four suites successfully at `c6995893ba48caf1e0d42ee7c46d9f858366d0c2`.
The initial root-suite failure exposed a historical fixed filename set; placing
readers in the existing worker module resolved it without changing/weakening
historical tests or adding an unapproved path. Later checks remain exact-head
specific; do not substitute this earlier receipt for final HEAD acceptance.

## Physical pilot prerequisites and boundary

After source acceptance and postmerge CI, obtain one bounded physical delegation:

- Fresh PR-A instance/source/workspace roots, private PCP service network,
  exact reviewed Runtime/Executor/Router images and DDEV/Compose versions;
  Compose must support `!override`/`!reset`. No shared network peers or legacy
  hooks. The verification web base is digest-pinned; its generated extension
  installs Python venv, pytest 8.3.5 and PyYAML 6.0.2 inside the image only.
- Approved singleton registration with `bounded`/`isolated_clone`, exact source
  path, delivery rights and `ddev.enabled=true`. Configure nonempty
  `targeted_tests` and `full_tests` as lists of approved
  `tests/test_pcp_light_*.py` paths. Activate an approved immutable baseline
  revision separately; no source commit/revision is fabricated by PR-B.
- Fresh dedicated PostgreSQL schema including existing receipt/lease/job tables;
  no foreign/historical jobs. Dedicated Runtime subscription login, Executor-only
  GitHub publisher, service tokens, read-only config and hardened Runtime process.
  No developer socket, source-root/Host HOME or publisher credential mount.
- Install `/config/pcp-local-activation.json` outside developer-writeable storage:
  `project_id`, `repository`, `issue_number`, `body_sha256`, `base_sha`,
  `baseline_revision`, `baseline_source_commit`, `developer_permission_mode`,
  `expires_at` (Unix seconds), fresh instance `root`, `runtime_image_id`,
  `runtime_network`, `codex_version`, authorized independent `pm_login`,
  digest-pinned DDEV `verification_image`, and
  `budget` (`model_calls`, `max_wall_seconds`, `cash_ceiling_usd`). Runtime and
  Executor must see identical bytes/values. This is operational delegation,
  not an issue-authored evidence dictionary. Keep all task switches OFF until
  the independent physical boundary checks and pilot authorization are complete.
- After the pilot's exact-source receipt, one-shot `/v1/pcp-local/run-once` may
  invoke its admitted job. Uncertain claims never replay; diagnosis retains the
  same job/diff/counters/lease. `/v1/pcp-local/deliver` may reconcile an already
  verified commit under fresh authority; it never invokes Codex again.
  Verification stops only its owned test container;
  it preserves copies, images, cache and logs. Removal is separately scoped.
- The independent PM posts an exact-head GitHub review from `pm_login`, then
  submits `/v1/pcp-local/pm-review` with source/head/branch/baseline/PR/review IDs.
  Review body: `<!-- coding-platform:pcp-local-pm-review:v1 -->` followed by JSON
  binding `job_id`, `source_commit`, `expected_head`, `baseline_revision`,
  `diff_hash`, `verdict: "pass"`, `findings: []` and substantive `summary`.
  The original source issue/activation cannot authorize its own review. GitHub
  metadata proves the configured account, not independent human identity;
  independent ChatGPT PM review remains a process gate. No Developer merge API.

**HOST/DDEV/DB=STOP; CODEX_LIVE=STOP; A3B2_IMAGE_BUILD=STOP.** No real Docker/DDEV,
image build, credential provisioning, provider/model API, DB/job mutation or
cleanup occurred in this SOURCE task. Local checks and hosted CI do not prove
live isolation, deployed health, quota entitlement or successful Codex delivery.

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
