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

## Verified protected workflow migration

[PR #666](https://github.com/sonvhse06072/personal-coding-platform/pull/666) merged at `06854fc2f46d06778c1de0dc950330eb86de24f3` after [exact-head CI #38227358222](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38227358222) **4/4 SUCCESS** and [Guardian static #38227357690](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38227357690) SUCCESS. Actual four PR runner IDs were distinct `GitHub Actions` instances labeled `ubuntu-24.04`; Runtime 1546, Executor 273, Router 127 and root 661 tests passed.

Initial hosted root suite caught a pre-existing test mock that assumed UID 1000. Its fixture now reads the owner of pytest's own temporary directory; production fixture-staging ownership checks were not weakened. The test-only correction remained in the same reviewed PR.

**Fast-path proof:** This T1/T3-only PR intentionally changes no code, config or workflow. An absent pull_request workflow run is an Actions event-delivery blocker, never evidence that all checks passed. It must yield root structure/doc-authority PASS and three named service job SUCCESS statuses via explicit docs-only no-op steps; if any service runs actual tests or root is skipped, the scope policy has NOT been validated.

## Evidence and remaining gates

The protected CI PR must pass all four suites on GitHub-hosted infrastructure, and Guardian static where triggered. After merge, a small T1/T3-only PR should prove the fast path without any production change. Branch-protection metadata is unavailable through the integration; do not rename or omit old checks. GitHub-hosted minutes on this private repository may be billable. Confirm actual runner identity and workflow conclusions before reporting completion. No PCP legacy Runtime, Codex, fixture or Chợ Nhạc operation is part of this change.

## Post-rollout integrity correction — trusted base checkers

[PR #667](https://github.com/sonvhse06072/personal-coding-platform/pull/667) was independently validated on an ephemeral hosted PR runner and merged to `main@a046af354a6dee2f0728460233b646aed2d6b8c4`. Its exact-head [CI #38228350120](https://github.com/sonvhse06072/personal-coding-platform/actions/runs/38228350120) confirmed `docs_only` in all three service jobs, no dependency installation or service test execution, while the unchanged four check contexts all returned SUCCESS; structure and document authority still ran (661 root tests).

Security review then identified a **CI self-classification trust gap** in #666: the new PR scope classifier and the pre-existing document-authority script were executed from the *PR checkout*. A PR could rewrite either script in the same changeset it wanted to classify, gaining control of skip/authority results. The approved [#665](https://github.com/sonvhse06072/personal-coding-platform/issues/665) isolation/security workstream includes this corrective bound.

[Corrective PR #668](https://github.com/sonvhse06072/personal-coding-platform/pull/668) requires both checks to execute the scripts taken from the exact `pull_request.base.sha` on the owner repository's `main` (not from PR head). Unknown base or classifier failure conservatively runs FULL service checks; the document authority gate fails closed if it cannot load its trusted base script. The workflow still runs PR test code only on ephemeral hosted Ubuntu, full regression on trusted main, preserves all four check contexts and uses no new credentials. Protected workflow changes use Owner-approved #665 scope and exact-head CI/review. Branch/ruleset enforcement could not be independently read through the integration and remains a separate policy limitation.

This check is about *trusting CI decisions*, not marking historical tests obsolete; no runtime, provider, G0 job, fixture or Chợ Nhạc operations.
