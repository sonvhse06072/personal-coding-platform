# G0 Drupal 11 Fixture — ProjectBaseline Candidate

Status: CANDIDATE / NON-PRODUCTION. This file by itself is not a PCP-approved or activated ProjectBaseline.
Owner scope: https://github.com/sonvhse06072/personal-coding-platform/issues/595#issuecomment-6094931078

## Purpose
Provide reproducible, empty-data, independent Drupal 11 Unit and Kernel test acceptance for a small, bounded PCP-vs-direct experiment. Keep one code writer per isolated arm; preserve the same source commit and task contract for each arm.

## Constraints
No production, no external user data, no Chợ Nhạc, no reuse of existing DDEV databases/workspaces, no privileged PCP/Executor/Guardian credentials, no production deployment, no authentication/authorization changes, and no autonomous merge without required review/CI.

## Starter source and quality policy
Official `drupal/recommended-project:^11` with locked Composer dependencies, PHP 8.4 and DDEV `pcp-g0-drupal-fixture` only. Tests must execute real Drupal Unit and Kernel suites and PHPCS (Drupal standard) with zero skips/failures, plus PHP syntax, Composer validate, and equivalent PR CI on both experiment arms.

## First independent engineering task — G0D-T01 (NOT part of bootstrap)
Implement internal ASCII whitespace normalization for `EventLabelNormalizer::normalize`: collapse any consecutive U+0020, tab, CR or LF into exactly one space; preserve outer trim semantics. Add Unit and Kernel tests to prove this behavior and unchanged initial cases. Keep task to this module and its tests. Final acceptance must use exactly the same checks, model/effort and source SHA on isolated `benchmark/direct` and `benchmark/pcp` delivery arms.

## Change and measurement gates
This CANDIDATE baseline must be explicitly pinned to the exact fixture seed source commit through a separate Owner-reviewed protected PCP registration PR before any PCP WorkOrder. Current host Codex 0.162.0 versus Runtime Codex 0.160.0 is not a normalized comparison. Gather real source/CLI/toolchain/workspace/CI/review/time/usage evidence. No synthetic acceptance claim, no p90 under the required sample size, and no G1 activation from this document.
