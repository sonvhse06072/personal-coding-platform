# Draft successor baseline candidate for PM/Owner review

Prepared under the adoption WorkOrder; **not approved, not installed, not active**.
The [decision packet](../pcp-portable/local-operations.md#v4-successor-and-admission-decision-packet)
contains authority delta, unresolved reservation and all physical/LIVE gates.
This review artifact must not replace an existing approved registry revision.
The old V3 revision remains unchanged. New source pin is the accepted merge,
not the follow-up documentation PR. There is no new delegated design authority.

The YAML below has the same data as the privately retained, schema-validated JSON
candidate SHA256 `45fd1ad73f3bbdccab688cc337f3e8437e897bbaed5130ed1f8557fe1f150ce3`.
Every protected path comes from the accepted source's exact 50-path authority
checker list. This is an explicit proposal for review, not a claim that this
mutable document can itself approve or redefine those classes.

```yaml
version: 1
projects:
  pcp-local:
    active_revision: null
    revisions:
      pcp-local-successor-825-5adfd12-20261029:
        status: draft
        source_commit: 5adfd120dbd6aa4718cf9549ddc6fae0bab8f12d
        authority:
        - path: .github/workflows/guardian-static.yml
          authority: human_owner_protected
        - path: .github/workflows/pcp-guardian.yml
          authority: human_owner_protected
        - path: .github/workflows/pcp-local-inspect-image.yml
          authority: human_owner_protected
        - path: .github/workflows/tests.yml
          authority: human_owner_protected
        - path: AGENTS.md
          authority: human_owner_protected
        - path: config/models.yml
          authority: human_owner_protected
        - path: config/pm-bridge.yml
          authority: human_owner_protected
        - path: config/project-baselines.pcp-local.yml
          authority: human_owner_protected
        - path: config/project-baselines.yml
          authority: human_owner_protected
        - path: config/projects.pcp-local.yml
          authority: human_owner_protected
        - path: config/projects.yml
          authority: human_owner_protected
        - path: config/routing-policy.yml
          authority: human_owner_protected
        - path: docs/pcp-portable/h1b3-oci-evidence-plan.md
          authority: human_owner_protected
        - path: docs/pcp-portable/h1c-ddev-install-plan.md
          authority: human_owner_protected
        - path: docs/project/README.md
          authority: human_owner_protected
        - path: docs/project/architecture.md
          authority: human_owner_protected
        - path: docs/project/business-strategy.md
          authority: human_owner_protected
        - path: docs/project/constitution.md
          authority: human_owner_protected
        - path: docs/project/context-memory-architecture.md
          authority: human_owner_protected
        - path: docs/project/efficiency-model.md
          authority: human_owner_protected
        - path: docs/project/operating-model.md
          authority: human_owner_protected
        - path: docs/project/provider-policy.md
          authority: human_owner_protected
        - path: docs/project/provider-quota-telemetry.md
          authority: human_owner_protected
        - path: docs/project/roadmap.md
          authority: human_owner_protected
        - path: docs/project/service-secret-upgrades.md
          authority: human_owner_protected
        - path: docs/project/telegram-terminal-operations.md
          authority: human_owner_protected
        - path: profiles/pcp-local/.ddev/config.yaml
          authority: human_owner_protected
        - path: profiles/pcp-local/.ddev/docker-compose.platform.yaml
          authority: human_owner_protected
        - path: profiles/pcp-local/ddev-install-plan.example.yml
          authority: human_owner_protected
        - path: profiles/pcp-local/docker-compose.local.yaml
          authority: human_owner_protected
        - path: profiles/pcp-local/image-provenance.example.yml
          authority: human_owner_protected
        - path: profiles/pcp-local/oci-evidence-plan.example.yml
          authority: human_owner_protected
        - path: profiles/pcp-local/runtime/Dockerfile.inspect
          authority: human_owner_protected
        - path: profiles/pcp-local/runtime/Dockerfile.inspect.dockerignore
          authority: human_owner_protected
        - path: profiles/pcp-local/runtime/requirements-inspect.lock
          authority: human_owner_protected
        - path: scripts/check_project_doc_authority.py
          authority: human_owner_protected
        - path: scripts/pcp-local-ddev-install-plan.py
          authority: human_owner_protected
        - path: scripts/pcp-local-gate-a-inspect.sh
          authority: human_owner_protected
        - path: scripts/pcp-local-image-provenance-plan.py
          authority: human_owner_protected
        - path: scripts/pcp-local-oci-evidence-plan.py
          authority: human_owner_protected
        - path: scripts/pcp-local-trusted-bootstrap.sh
          authority: human_owner_protected
        - path: scripts/pcp-shared-docker-ownership-check.sh
          authority: human_owner_protected
        - path: services/ddev-executor/app/main.py
          authority: human_owner_protected
        - path: services/runtime/app/engine.py
          authority: human_owner_protected
        - path: services/runtime/app/engine_core.py
          authority: human_owner_protected
        - path: services/runtime/app/engine_delivery.py
          authority: human_owner_protected
        - path: services/runtime/app/main.py
          authority: human_owner_protected
        - path: services/runtime/app/pcp_local_trusted_readers.py
          authority: human_owner_protected
        - path: services/runtime/app/pcp_local_worker_loop.py
          authority: human_owner_protected
        - path: services/runtime/app/storage.py
          authority: human_owner_protected
        - path: README.md
          authority: mutable_execution
        - path: docs/project/current-state.md
          authority: mutable_execution
        - path: docs/project/history
          authority: evidence_history
        - path: docs/pcp-portable/consolidation.md
          authority: evidence_history
        - path: docs/pcp-portable/local-operations.md
          authority: mutable_execution
        references:
          goals:
          - path: docs/project/constitution.md
            section: 2. Project goals
          non_goals:
          - path: docs/project/constitution.md
            section: 3. Non-goals
          requirements:
          - path: docs/project/roadmap.md
            section: PCP Local execution priority — GH-815, 2026-10-27
          architecture_constraints:
          - path: docs/project/architecture.md
          quality_policy:
          - path: docs/project/operating-model.md
            section: 8. Deterministic verification
          security_policy:
          - path: docs/project/constitution.md
            section: 9. Trust and security invariants
          budget_policy:
          - path: docs/project/constitution.md
            section: 11. Budget principles
          roadmap_frame:
          - path: docs/project/roadmap.md
```
