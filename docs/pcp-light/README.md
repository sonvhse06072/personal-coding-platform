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
5. Host operator stages/commits exactly changed files, pushes only the new AI branch and opens a **draft PR**. **Full repository pytest on isolated GitHub-hosted PR CI is mandatory**, then PM review exact HEAD and only afterwards an explicit merge decision. A source syntax pass or draft PR is **not** a test/CI pass. No auto-merge/deploy.

Any STOP, provider failure, timeout, dirty/mismatched git source or unexpected change preserves the journal/worktree for triage. **Never rerun a claimed key or cleanup/reset to bypass STOP.** In particular this tool must not be used to revive G1-T01. A draft PR is only a delivery artifact. Its hosted CI can fail; when it does, the original job remains preserved and **no blind Codex retry** is allowed. The separately accepted #725 result does not prove unattended generic PCP-light autonomy or G0 Direct/full-PCP parity.

## Speed/quality decision

This operator deliberately reuses `gh`, existing Codex auth, Git worktrees and GitHub Actions. No new PostgreSQL, DDEV, Router, Executor, proxy, workflow scheduler, Python dependency installer or generic agent framework. The local `pytest` stop in the original #725 trial drove this **CI-first verification policy**: make source-scope/AST checks locally, run full tests in isolated hosted PR CI instead. This avoids executing unreviewed generated tests on the Owner host and prevents a post-model `No module named pytest` blocker. A genuine result should be compared to plain direct Codex using accepted PR, end-to-end elapsed time, model tokens and count of Owner interventions. Do not claim p50/p90 or savings from a single run. G0 #595 remains HOLD / NOT GO.
