# PCP-light v1 — one existing Codex CLI, no PCP services

This is a **new workstream**, not a resume/replacement for frozen G1-T01, F2, or old no-model smoke. The existing Runtime PM Bridge (`coding-platform:pm-plan:v1`) remains unchanged. PCP-light uses a separate Github issue marker and **only targets `sonvhse06072/personal-coding-platform`** in v1. Chợ Nhạc, other repositories, `scripts/g0-*`, `scripts/g1-*`, `deploy/g1`, protected policy/docs, data, Docker and DDEV are not eligible.

## GitHub handoff

Create a *new* PCP issue using the Owner GitHub account; the issue body must contain exactly one marker followed by one JSON object:

```text
<!-- coding-platform:pcp-light:v1 -->
{
  "version": 1,
  "key": "example-bounded-fix",
  "base_sha": "<the clean full 40-hex PCP main SHA>",
  "model": "gpt-6-luna",
  "reasoning": "medium",
  "goal": "Implement one bounded PCP-light feature with a focused regression test.",
  "allowed_paths": [
    "scripts/pcp-light-example.py",
    "tests/test_pcp_light_example.py"
  ]
}
```

No model is selected by the operator: PM/Owner pins the exact model and effort in the issue. An explicit local `--execute` and a separately pinned exact body SHA-256 are the two execution gates; no additional GitHub label needs provisioning. Accepted effort: `low`, `medium`, `high`, `xhigh`. Only 1–4 explicitly named `scripts/pcp-light-*.py`, `tests/test_pcp_light_*.py` and `docs/pcp-light/*.md` files are allowed. An explicit test path is required. The full issue body SHA-256 must also be pinned **independently** in the Owner's local invocation, e.g. from a checked PM handoff, so an edited/unapproved issue cannot change the task.

## Operator (WSL Ubuntu, with authenticated `gh` and Codex)

After reviewing the issue and its SHA-256:

```bash
cd /home/sonvh/personal-coding-platform-v1
python3 scripts/pcp-light-run.py \
  --issue ISSUE_NUMBER --body-sha256 FULL_64_HEX_SHA256 \
  --repo-root /home/sonvh/personal-coding-platform-v1
```

Default mode **only validates** GitHub issue identity/body digest and current clean exact `main`. It does not create a workspace, issue model tokens, connect to PCP services, or mutate git.

Only an explicit `--execute` on that same command authorizes a **one-shot**:
1. Ensure **only** `~/.pcp-light` and `~/.pcp-light/jobs` are privately owned directories (`0700`), then claim `~/.pcp-light/jobs/<key>/journal.json` exclusively before any new workspace/model action. A missing private parent is created with exact mode; an existing **user-owned `0755`** parent is narrowed to `0700` without recursion or changes to historical job contents. Unexpected permissions, foreign owners, symlinks and non-directories STOP before a model turn; no broad chmod/reset/cleanup.
2. Create a new **PCP-light-only** git worktree at exact pinned source and branch `ai/pcp-light/<key>`; do not touch existing G1/F2/Direct worktrees or Chợ Nhạc.
3. Fail fast with `codex --version` **before** reserving a journal or model turn if the native CLI is unavailable. Then make exactly **one Codex CLI** coding call with sandbox `workspace-write`, no workspace network, no approval prompts, no inherited GitHub/provider/internal token env.
4. Require Codex terminal `turn.completed`, actual changes only within the allowlist including tests, no deletions/symlinks, and **AST syntax parsing of changed Python source without executing it** on Owner WSL. The runner records an exact focused-test command for audit only. **No `pytest` package is required locally; do not install, import or execute agent-generated tests on Owner WSL.** No automatic model repair/retry.
5. Host operator stages exactly the approved changed files and **requires `git diff --cached --check` PASS**. Only if Git reports **one exact `new blank line at EOF.` warning on a changed allowlisted Python file** does the operator remove excess final LF bytes, after verifying unchanged Python AST and privately saving original bytes (mode `0600`) inside the same one-use job. It then restages the one file and **must revalidate Git quality PASS and exact scope**; all other whitespace warnings, extra warnings and unexpected paths STOP without a repair/retry. The journal and draft PR evidence distinguish `quality_checked` from Python tests and record which file was normalized. This avoids the exact real #734 Git blocker for future jobs without spending another model call.
6. Host operator commits exactly the validated changed files, pushes only the new AI branch and opens a **draft PR**. **Full repository pytest on isolated GitHub-hosted PR CI is mandatory**, then PM review exact HEAD and only afterwards an explicit merge decision. A source syntax/Git quality PASS or draft PR is **not** a test/CI pass. No auto-merge/deploy.

Any STOP, provider failure, timeout, dirty/mismatched git source or unexpected change preserves the journal/worktree for triage. **Never rerun a claimed key or cleanup/reset to bypass STOP.** In particular this tool must not be used to revive G1-T01. A draft PR is only a delivery artifact. Its hosted CI can fail; when it does, the original job remains preserved and **no blind Codex retry** is allowed. The separately accepted #725 result does not prove unattended generic PCP-light autonomy or G0 Direct/full-PCP parity.

## Context and token evidence (no extra model call)

Both the default read-only handoff and the eventual one-turn result now include
`context_footprint`: **raw file sizes only** for `AGENTS.md`, five required
authority documents and `README.md`; byte sizes for existing allowlisted
source files; and the task prompt's UTF-8 byte count. The runner uses file
metadata (`lstat`) rather than reading documents or following symlinks.
This is a **minimum documented authority footprint**, not proof of the bytes
Codex actually read, not a token estimator, and not a quota or STOP condition.
Other task-relevant documents can add to the actual context.

The Codex prompt explicitly keeps the mandatory `AGENTS.md` reading order.
After that first reading it encourages targeted searches, bounded line ranges
and avoiding repeated full-document output; **no authority, test or security
requirement is skipped**. Token savings are a hypothesis until measured on
comparable accepted tasks.

At `turn.completed`, validated `input_tokens`, `cached_input_tokens`
and `output_tokens` are reported alongside derived
`uncached_input_tokens = input - cached` and
`cached_input_share_percent`. Missing, inconsistent or malformed usage
produces `null` derived fields, never fabricated zero. Cached input tokens
are included in input totals and must **not** be added twice. These are
model-reported token counts, not billable USD or the total human-attention
cost. Token evidence is stored with the one-use job journal, and reporting
does **not** call the model again or contact the provider.

## PM handoff through the existing draft PR

A successful one-turn PCP-light coding operation now places a small
`pcp-light-pr-evidence-v1` JSON report **directly in the draft PR body**
(using the existing `gh pr create` operation, not an extra API request):
approved issue/body SHA-256, source/candidate SHA, model/effort, one model
call and elapsed seconds, reported input/cached/uncached/output token counts,
raw authority byte footprint, approved changed paths, AST-only source check,
local tests **0** and hosted full CI **PENDING**. If counters are missing or
malformed, their fields are `null`, not zero. Cash billing is
`UNAVAILABLE`, not guessed from quota or token counts.

### Host-operator elapsed time (no extra calls)

On future successful new-task runs, the existing PR-body evidence adds
`operator_pre_pr_elapsed_seconds`, measured from entering the one-use
operator through issue verification, Codex authentication/worktree setup,
model execution, AST/Git validation, commit and push, **immediately before**
`gh pr create`. This is not model elapsed time and intentionally excludes
PR creation network time, GitHub-hosted CI, PM review, Owner wait and
provider cash billing. It is verified finite, nonnegative and cannot be
shorter than the reported model elapsed time.

The private same-job journal and sanitized final operator JSON additionally
record `operator_elapsed_seconds` through successful draft PR creation,
including that `gh pr create` call. No additional provider call, API call,
new workspace, local pytest, prompts, logs or credentials are collected.
Legacy PRs and missing operator-duration evidence stay **unknown** rather
than being assigned fabricated zero. Compare these separate phases only on
naturally needed new tasks; do not claim end-to-end ROI from operator time.

The report is built from fixed allowlisted **numeric and identity metadata**.
No task prompt/goal, provider conversation, environment values, credentials,
paths beyond the approved changed files, or raw test logs are copied.
This helps the PM find the PR and assess the delivery from GitHub directly,
without requiring Owner to copy the same successful run's JSON back into chat.
The owner still invokes the operator once for any new approved task; the
existence of a PR does not create an automated watcher or merge permission.

**The PR body is informative, not an independent attestation:** anyone with
permission to edit a PR description can modify it. PM must still check the
real PR HEAD, one-parent diff/scope, **hosted full PR CI** and required review
before merging. For a STOP *before draft creation*, there is no PR to inspect;
the Owner should provide only the sanitized STOP code, preserving the
original worktree/journal with **no retries**.

### Read-only PR readiness report

`scripts/pcp-light-pr-review.py` is a report-only check; it never approves,
merges, retries or mutates GitHub. Its normal one-commit path remains
`READY_FOR_PM_REVIEW`. It also recognizes a bounded linear chain of 2–4 commits
from the immutable Owner issue `base_sha` to the explicitly pinned open PR HEAD,
reported as `READY_FOR_PM_REVIEW_WITH_REPAIRS`. For that result it records the
first candidate commit and chain length and sets
`repair_chain_needs_independent_review=true`.

The chain must be exactly ahead of its source with no behind commits, the exact
source merge base, matching ahead/total/list counts, unique SHAs, one exact
parent per commit in sequence and the pinned HEAD last. Each repair commit's
actual changed-file list is fetched through a fixed GitHub GET and must be
complete, bounded and entirely within the immutable issue allowlist; merge,
delete, rename, foreign intermediate edit, truncated list and chains longer
than four fail closed even if the final aggregate diff looks clean. The normal
final PR diff, changed-test requirement, owner issue marker/JSON/body digest,
PR author/repository/branch/base checks and all four hosted tests.yml jobs on
the exact current HEAD remain required. **The readiness gate inspects actual
GitHub-hosted runner identity and successful unconditional runner-attestation
steps, plus successful full pytest steps for all four named jobs.** A service
job can report `SUCCESS` when its `docs_only` no-op succeeds but pytest is
`skipped`; that is **NOT READY** for a PCP-light code PR. The real #740
docs-only workflow had this shape, and its postmerge Runtime suite later found
a regression. The new check reuses the same job-data GET without another
GitHub API request and preserves queued-run `PENDING` semantics. A green PR
never substitutes for full postmerge acceptance. The mutable PR body supplies
no proof.

The repaired-chain status is only a readiness report. A human must review each
commit's code and the exact final diff, and exact-head hosted CI must pass
before merge. It does not claim PM approval or autonomous first-pass success.

### Read-only postmerge CI attestation

After PM has already reviewed and merged a PCP PR, use the existing
authenticated `gh` CLI to independently verify the exact merged SHA and full
`push main` CI. The new PCP-light helper is strictly read-only and works for a
normal merged PCP source PR, **not** just a PCP-light one-shot issue:

```bash
python3 scripts/pcp-light-postmerge.py \
  --pr PR_NUMBER \
  --expected-merge-sha FULL_40_HEX_MERGE_SHA \
  --run-id EXACT_TESTS_WORKFLOW_RUN_ID
```

This checker pins the merged PR identity, Owner and repository, exact merge
commit, main target, the `tests` workflow path and **push** trigger on that
commit, then fetches all four required full-test jobs from the latest attempt.
It refuses pending/failed CI, missing or duplicate jobs, skipped tests, a
self-hosted or unverified runner, and forged success claims in mutable PR text.
Unlike the premerge `pcp-light-pr-review.py`, this is for a **completed**
merge, not draft PR approval.

The output is `POSTMERGE_CI_VERIFIED` on validated CI only; otherwise it
returns `PENDING` or `NOT_VERIFIED` with a sanitized STOP reason and
nonzero exit status. An accepted CI result does **not** approve a merge,
establish GitHub branch protection, deploy local PCP Runtime or measure
Direct-vs-full-PCP parity. All actions are fixed `gh api --method GET` calls
without a retry, model call, credential disclosure or host-service operation.

Where real job timestamps are available, the report includes separate full
workflow elapsed seconds, per-job elapsed seconds and
`estimated_rounded_runner_minutes` (sum of individually rounded hosted job
durations). Missing timestamps produce `null` instead of invented zero,
and **provider cash cost remains `UNAVAILABLE`**. Do not confuse this
estimate with GitHub's billed minutes or CI critical-path time. Historical
negative evidence includes PCP PR #740, whose PR-head checks passed but whose
original merged Runtime suite failed; later corrective PR #741 has its own
separate successful postmerge proof.

## Speed/quality decision

This operator deliberately reuses `gh`, existing Codex auth, Git worktrees and GitHub Actions. No new PostgreSQL, DDEV, Router, Executor, proxy, workflow scheduler, Python dependency installer or generic agent framework. The local `pytest` stop in the original #725 trial drove this **CI-first verification policy**: make source-scope/AST checks locally, run full tests in isolated hosted PR CI instead. This avoids executing unreviewed generated tests on the Owner host and prevents a post-model `No module named pytest` blocker. A genuine result should be compared to plain direct Codex using accepted PR, end-to-end elapsed time, model tokens and count of Owner interventions. Do not claim p50/p90 or savings from a single run. G0 #595 remains HOLD / NOT GO.
