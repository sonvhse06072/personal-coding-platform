# CI Runner Modernization — 2026-10-12

**Authority:** Owner approved the CI optimization recommendation in the PM conversation. Canonical issue [#665](https://github.com/sonvhse06072/personal-coding-platform/issues/665). This is an approved protected-workflow source change, not an operational deployment.

## Live baseline

PCP main before the change: `f516c92413d8f9b9a3726839a2972cad59070d04`. [Run #38220824480](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38220824480) used persistent self-hosted runner `SonVH` version 2.337.0. Four CI jobs ran sequentially for about 150 seconds. Test bodies: root 637 (~7s), Executor 273 (~22s), Router 127 (~4s), Runtime 1546 (~29s). Checkout v4 and setup-python v5 produced deprecated Node20 warnings.

## Changes and retained guarantees

- Pull-request CI moves to ephemeral GitHub-hosted Ubuntu 24.04. Trusted `main` push keeps full regression on the existing self-hosted runner to conserve hosted minutes.
- Checkout and setup-python move to immutable, verified v7 commit SHAs. Checkout credentials are not persisted. Keep the original four job identities.
- Only PRs entirely changing `docs/project/current-state.md` or `docs/project/history/*.md` skip the service dependency/install/test steps. Root structure and documentation authority still run. All empty, ambiguous, mixed, renamed, deleted, security, workflow or code diffs run full tests. Main pushes always run the full suite.
- Guardian static checks retain their path trigger and move to pinned v7. Guardian issue-comment operation and historical G0D-01 hosted proof remain unchanged.
- All historical Runtime, Router, Executor, G0, Guardian and Antigravity tests stay available. No proof supports deleting them on filename alone.

## Evidence and remaining gates

The protected CI PR must pass all four suites on GitHub-hosted infrastructure, and Guardian static where triggered. After merge, a small T1/T3-only PR should prove the fast path without any production change. Branch-protection metadata is unavailable through the integration; do not rename or omit old checks. GitHub-hosted minutes on this private repository may be billable. Confirm actual runner identity and workflow conclusions before reporting completion. No PCP legacy Runtime, Codex, fixture or Chợ Nhạc operation is part of this change.
