# Successor observer / admission decision packet — 2026-10-29

Preparation under execution6489438739 and the later Owner-requested
[local observer decision6489495501](https://github.com/sonvhse06072/personal-coding-platform/issues/815#issuecomment-6489495501).
No source/image/registry installation or new admission. V3 was retired incomplete;
its assisted result remains historical evidence, never this next task's result.

## Frozen draft and exact registry diff

This is a **draft at accepted827 source**, not the next activation target. Its
source is known; it deliberately does not pretend to include the pending auth
change. Schema validates,50 protected authority paths preserved, active_revision
null. Neither V3 nor V4 installed registry was modified. Prior825 candidate stays
historical. After this follow-up merges, create a NEW immutable revision keyed to
that actual accepted SHA; never rewrite this snapshot or an approved revision.
A future main/head must not silently replace baseline authority.

Baseline YAML bytes SHA256: `02d7a9d8acff908b1eb094f688236696ec8cfa7935d91664e5bd106160b1eda6`.
Exact diff bytes SHA256: `3e3953e67cf87f50e4947a12a4418749a2eb5cf982010199f93cc23a8992e2a9`.
The diff applies to the accepted repository's empty draft registry. On adoption,
compare the actual destination preimage first; retain any existing revisions and
reject a mismatch instead of overwriting them. Project registry/config activation
remains a separate PM checkpoint; all current autonomy flags stay off.

```diff
--- accepted/config/project-baselines.pcp-local.yml
+++ PROPOSED-NOT-INSTALLED/project-baselines.pcp-local.yml
@@ -1,10 +1,142 @@
-# GH-815 PR-A: preparation is not ProjectBaseline approval or activation.
-# The schema requires a concrete source_commit even for a draft revision. Do not
-# invent a future merge SHA: leave revisions empty until the reviewed authority
-# commit is known. Later add an explicitly approved immutable revision, then
-# separately activate it; never rewrite an approved revision in place.
 version: 1
 projects:
   pcp-local:
     active_revision: null
-    revisions: {}
+    revisions:
+      pcp-local-successor-827-ea6fc0a-20261029:
+        status: draft
+        source_commit: ea6fc0ac5dd101068bf4fe6f8f8813495cc529bf
+        authority:
+        - path: .github/workflows/guardian-static.yml
+          authority: human_owner_protected
+        - path: .github/workflows/pcp-guardian.yml
+          authority: human_owner_protected
+        - path: .github/workflows/pcp-local-inspect-image.yml
+          authority: human_owner_protected
+        - path: .github/workflows/tests.yml
+          authority: human_owner_protected
+        - path: AGENTS.md
+          authority: human_owner_protected
+        - path: config/models.yml
+          authority: human_owner_protected
+        - path: config/pm-bridge.yml
+          authority: human_owner_protected
+        - path: config/project-baselines.pcp-local.yml
+          authority: human_owner_protected
+        - path: config/project-baselines.yml
+          authority: human_owner_protected
+        - path: config/projects.pcp-local.yml
+          authority: human_owner_protected
+        - path: config/projects.yml
+          authority: human_owner_protected
+        - path: config/routing-policy.yml
+          authority: human_owner_protected
+        - path: docs/pcp-portable/h1b3-oci-evidence-plan.md
+          authority: human_owner_protected
+        - path: docs/pcp-portable/h1c-ddev-install-plan.md
+          authority: human_owner_protected
+        - path: docs/project/README.md
+          authority: human_owner_protected
+        - path: docs/project/architecture.md
+          authority: human_owner_protected
+        - path: docs/project/business-strategy.md
+          authority: human_owner_protected
+        - path: docs/project/constitution.md
+          authority: human_owner_protected
+        - path: docs/project/context-memory-architecture.md
+          authority: human_owner_protected
+        - path: docs/project/efficiency-model.md
+          authority: human_owner_protected
+        - path: docs/project/operating-model.md
+          authority: human_owner_protected
+        - path: docs/project/provider-policy.md
+          authority: human_owner_protected
+        - path: docs/project/provider-quota-telemetry.md
+          authority: human_owner_protected
+        - path: docs/project/roadmap.md
+          authority: human_owner_protected
+        - path: docs/project/service-secret-upgrades.md
+          authority: human_owner_protected
+        - path: docs/project/telegram-terminal-operations.md
+          authority: human_owner_protected
+        - path: profiles/pcp-local/.ddev/config.yaml
+          authority: human_owner_protected
+        - path: profiles/pcp-local/.ddev/docker-compose.platform.yaml
+          authority: human_owner_protected
+        - path: profiles/pcp-local/ddev-install-plan.example.yml
+          authority: human_owner_protected
+        - path: profiles/pcp-local/docker-compose.local.yaml
+          authority: human_owner_protected
+        - path: profiles/pcp-local/image-provenance.example.yml
+          authority: human_owner_protected
+        - path: profiles/pcp-local/oci-evidence-plan.example.yml
+          authority: human_owner_protected
+        - path: profiles/pcp-local/runtime/Dockerfile.inspect
+          authority: human_owner_protected
+        - path: profiles/pcp-local/runtime/Dockerfile.inspect.dockerignore
+          authority: human_owner_protected
+        - path: profiles/pcp-local/runtime/requirements-inspect.lock
+          authority: human_owner_protected
+        - path: scripts/check_project_doc_authority.py
+          authority: human_owner_protected
+        - path: scripts/pcp-local-ddev-install-plan.py
+          authority: human_owner_protected
+        - path: scripts/pcp-local-gate-a-inspect.sh
+          authority: human_owner_protected
+        - path: scripts/pcp-local-image-provenance-plan.py
+          authority: human_owner_protected
+        - path: scripts/pcp-local-oci-evidence-plan.py
+          authority: human_owner_protected
+        - path: scripts/pcp-local-trusted-bootstrap.sh
+          authority: human_owner_protected
+        - path: scripts/pcp-shared-docker-ownership-check.sh
+          authority: human_owner_protected
+        - path: services/ddev-executor/app/main.py
+          authority: human_owner_protected
+        - path: services/runtime/app/engine.py
+          authority: human_owner_protected
+        - path: services/runtime/app/engine_core.py
+          authority: human_owner_protected
+        - path: services/runtime/app/engine_delivery.py
+          authority: human_owner_protected
+        - path: services/runtime/app/main.py
+          authority: human_owner_protected
+        - path: services/runtime/app/pcp_local_trusted_readers.py
+          authority: human_owner_protected
+        - path: services/runtime/app/pcp_local_worker_loop.py
+          authority: human_owner_protected
+        - path: services/runtime/app/storage.py
+          authority: human_owner_protected
+        - path: README.md
+          authority: mutable_execution
+        - path: docs/project/current-state.md
+          authority: mutable_execution
+        - path: docs/project/history
+          authority: evidence_history
+        - path: docs/pcp-portable/consolidation.md
+          authority: evidence_history
+        - path: docs/pcp-portable/local-operations.md
+          authority: mutable_execution
+        references:
+          goals:
+          - path: docs/project/constitution.md
+            section: 2. Project goals
+          non_goals:
+          - path: docs/project/constitution.md
+            section: 3. Non-goals
+          requirements:
+          - path: docs/project/roadmap.md
+            section: "PCP Local execution priority \u2014 GH-815, 2026-10-27"
+          architecture_constraints:
+          - path: docs/project/architecture.md
+          quality_policy:
+          - path: docs/project/operating-model.md
+            section: 8. Deterministic verification
+          security_policy:
+          - path: docs/project/constitution.md
+            section: 9. Trust and security invariants
+          budget_policy:
+          - path: docs/project/constitution.md
+            section: 11. Budget principles
+          roadmap_frame:
+          - path: docs/project/roadmap.md
```

## Next task body, not an issue or admission

Existing verify_issue accepts this three-path shape using a synthetic issue888
fixture; this is not a real GitHub author/approval observation. Body SHA256
`eb3304cfcd1b6318bf744316783f141d4685acfad7fc1dae6fe3636befb3ce54`, goal SHA256 `b3d8bbf7a58da8d15605d23670e02f4b3af9d2c966cdfdf8f45d424a41e47640`. After final source/baseline acceptance, PM
prepares a NEW pinned body/goal record and a fresh actual issue, reads its exact
identity/current main through the trusted reader, and authorizes one admission.
The recorded shape must not be used to register an ea6 task after main advances.

```text
<!-- coding-platform:pcp-remote-source:v1 -->
{
  "version": 1,
  "key": "pcp-local-evidence-summary-v1",
  "base_sha": "ea6fc0ac5dd101068bf4fe6f8f8813495cc529bf",
  "mode": "github_source_pr_only",
  "goal": "Implement a pure standard-library JSON evidence-summary CLI. Validate explicit SOURCE/FIXTURE/PHYSICAL/LIVE classes and PASS/FAIL/NOT_TESTED outcomes, required field types, duplicate IDs and one common full source SHA. Produce deterministic counts without promoting fixture evidence to LIVE. Accept empty lists; reject invalid inputs with nonzero exit. Add focused good/invalid/empty/duplicate/order tests and CLI examples. No network, subprocess, credentials, database, Runtime mutation or authority decisions.",
  "allowed_paths": [
    "scripts/pcp-light-evidence-summary.py",
    "tests/test_pcp_light_evidence_summary.py",
    "docs/pcp-light/evidence-summary.md"
  ]
}
```

Acceptance: deterministic output; empty/good/invalid/duplicate/order/source-mix
cases; required targeted/full verification; exact tree/modes/single parent; no
model replay in delivery recovery; reconciled branch/Draft PR before publication
retry; exact-head hosted suites and independent PM review. Preserve usage and
ownership. The 2–4-path rule including a test file is unchanged. No one-Markdown
replacement or implementation of this future task occurred here.

## Service inputs and adoption decisions

The [maintenance WorkReport](2026-10-29-retire824-execution.md) records actual Git
input trees and existing immutable image IDs. Runtime differs between5ad andea6
and will differ again for tokenless reads. Router/Executor/config inputs match
between5ad andea6; recheck at the actual accepted successor SHA. Their existing
image revision labels remain5ad, never relabeled as a new build.

The reviewed bootstrap binds every service image to one source; the current
Compose assigns one PCP_LOCAL_SOURCE_COMMIT revision label to all services. There
is no accepted mixed-source release record/override in this session. Therefore
reusing old images under a new blanket source label is **HOLD**. PM should review
an explicit per-service identical-input/provenance mapping and truthful container
labels (Router/Executor5ad, Runtime accepted successor); if the supported adoption
path cannot represent it, obtain the exact additional build/config scope. Do not
weaken the checker or improvise image labels. No need to rebuild unchanged inputs
merely because a documentation PR advanced main.

The later auth decision says to incorporate the change into the next reviewed
Runtime image to avoid two builds. Accordingly, no intermediate ea6 Runtime build
was performed. Build exactly once from the final accepted merge, full-SHA new tag,
with the reviewed V4 pins and archive procedure in local-operations. Record archive,
Dockerfile/requirements/app tree, build log, immutable image ID, labels, toolchain,
non-root/read-only/nonrecursive/tmpfs/noexec/askpass evidence before adoption.

PM next decisions form one packet: accept this source; authorize reviewed observer
rollout after postmerge CI; bind mixed service provenance or define its supported
alternative; approve a NEW immutable baseline/registry; then a separate fresh
three-path task/admission permit with scoped credentials only when ready. No old
activation, provider/publisher credentials, run-once or baseline activation here.
