# Current Project State and Handoff

Tier-1 mutable execution index; not project-frame authority, baseline approval
or physical attestation. Constitution, architecture and approved immutable
ProjectBaseline revisions outrank this snapshot. Reverify GitHub before action.

## Active work — GH-815 PR-A

Updated 2026-10-27. Branch `ai/815-trusted-local-pr-a`, isolated source checkout
`/home/sonvh/pcp-815-pr-a-source`; independently verified base
`8ce2e51f7abde098e49e974011b06eb9f305d4d9`. No legacy runtime/DB/Host was inspected.

- **Approved SOURCE:** [V1](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6438475541)
  local bootstrap/policy; [V2](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6438904126)
  adds three protected execution paths for PR-B; [V3](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6440446016)
  adds three legacy test paths to PR-A and retires legacy compatibility as a
  product requirement. PR-A ceiling is 13 paths; total approved union is 22.
- **Implementation prepared, not yet source-accepted:** fresh-root bootstrap
  dry-run plus separately gated future apply; three existing service Dockerfiles,
  explicit base/tool pins, unique local tags and image IDs/build logs; PCP-only
  hook-free DDEV instance, fresh internal service tokens, no provider/publisher
  credential migration. Apply never starts DDEV/DB/services or dispatches Codex.
- **Default OFF:** all custom services opt-in; real Runtime image currently uses
  existing `pcp_local_inspect` health startup. Registries remain draft/path-null,
  delivery rights off, `active_revision: null`, no invented revision/source SHA.
  PR-B must wire actual admitted execution before a live task is possible.
- **Tests:** 17 focused unittest cases PASS with strict fake Docker/DDEV and
  temporary Git/files only; `bash -n` and `git diff --check` PASS. Host pytest is
  absent; no package installation. Historical H1c/H1b tests now use their frozen
  inputs, and placeholder-only profile assertions are replaced with current
  boundary checks. Full hosted four-suite CI and independent PM review pending.
- **Next:** publish one Draft PR, obtain actual exact-head root/Router/Runtime/
  Executor hosted CI, then independent ChatGPT PM review. Developer does not
  approve or merge. PM must verify actual Owner consent and exact protected path
  declarations; PR metadata and CI alone are not independent human proof.

## PR-B handoff and physical boundary

Only after PR-A acceptance and refreshed `main`, use the existing approved PR-B
paths: `main.py`, `pcp_local_worker_loop.py`, new `pcp_local_trusted_readers.py`,
`engine_core.py`, `engine.py`, `engine_delivery.py` and the three startup/worker/
runtime-dispatch test files. Repeat T1/authority updates only inside approved
scope. Reuse the current receipt/CAS/one-shot registration; install real trusted
project/baseline/isolation/provider/budget/writer/publisher/model readers and a
separate admitted execution/delivery path. Generic legacy SOURCE denial remains;
no replacement queue/service. Keep `developer_permission_mode=bounded`.

Physical registration/baseline activation, DDEV global-name/shared-resource
checks, actual image/CLI health, provider login and publisher custody, job-only
verification configuration and the first issue/model/budget permit remain later
pilot work. The instance does not inherit legacy hooks; do not start the tracked
legacy `.ddev` inside the source clone for platform or job verification.

**HOST/DDEV/DB=STOP; CODEX_LIVE=STOP; A3B2_IMAGE_BUILD=STOP.** No Docker/DDEV,
GHCR workflow dispatch, credential provisioning, model/provider API or physical
cleanup was performed in this SOURCE task. The bootstrap future apply path is
covered by fake tests only. Local build IDs and CI do not prove working deployment
or developer credential isolation. One bounded operational delegation can cover
routine approved local work after acceptance; it cannot cover foreign resources,
production, destructive operations or protected/material decisions implicitly.

## Other execution gates

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
- **Chợ Nhạc strict no-touch:** no repository, worktree, DDEV, DB, job, lease,
  credentials or deployment access by this task. Accepted local risk is not
  authority over unrelated projects or shared resources.

Durable policy: [Operating Model](operating-model.md), [Roadmap](roadmap.md).
Practical setup and failure/rollback contract: [PCP Local](../pcp-portable/README.md).
Historical continuity remains available in Git and the linked issues; this file
replaces stale A3b execution history rather than accumulating another transcript.
