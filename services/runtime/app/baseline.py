from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .config import project_baselines_doc


RevisionStatus = Literal["draft", "approved", "superseded"]
_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_COMMIT_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


class SourceReference(BaseModel):
    """Repository-relative pointer to authoritative project documentation."""

    path: str = Field(min_length=1, max_length=1000)
    section: str | None = Field(default=None, max_length=500)

    @field_validator("path")
    @classmethod
    def validate_repository_relative_path(cls, value: str) -> str:
        raw = value.strip()
        if not raw:
            raise ValueError("Source-of-truth path must not be blank")
        if "\\" in raw:
            raise ValueError("Source-of-truth path must use repository POSIX separators")
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or path.as_posix() in {"", "."}:
            raise ValueError("Source-of-truth path must be repository-relative without traversal")
        return path.as_posix()

    @field_validator("section")
    @classmethod
    def normalize_section(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class BaselineReferences(BaseModel):
    goals: list[SourceReference] = Field(min_length=1)
    non_goals: list[SourceReference] = Field(min_length=1)
    requirements: list[SourceReference] = Field(min_length=1)
    architecture_constraints: list[SourceReference] = Field(min_length=1)
    quality_policy: list[SourceReference] = Field(min_length=1)
    security_policy: list[SourceReference] = Field(min_length=1)
    budget_policy: list[SourceReference] = Field(min_length=1)
    roadmap_frame: list[SourceReference] = Field(min_length=1)


class ProjectRevisionDefinition(BaseModel):
    status: RevisionStatus
    source_commit: str = Field(min_length=40, max_length=64)
    references: BaselineReferences

    @field_validator("source_commit")
    @classmethod
    def validate_source_commit(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _COMMIT_RE.fullmatch(normalized):
            raise ValueError("ProjectBaseline source_commit must be a full Git commit id")
        return normalized


class ProjectBaselineConfig(BaseModel):
    active_revision: str | None = Field(default=None, max_length=100)
    revisions: dict[str, ProjectRevisionDefinition] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_revisions(self) -> "ProjectBaselineConfig":
        for revision in self.revisions:
            if not _REVISION_RE.fullmatch(revision):
                raise ValueError(f"Invalid ProjectBaseline revision name: {revision}")

        if self.active_revision is not None:
            if not _REVISION_RE.fullmatch(self.active_revision):
                raise ValueError(f"Invalid active ProjectBaseline revision: {self.active_revision}")
            active = self.revisions.get(self.active_revision)
            if active is None:
                raise ValueError(
                    f"Active ProjectBaseline revision {self.active_revision!r} is not defined"
                )
            if active.status != "approved":
                raise ValueError(
                    f"Active ProjectBaseline revision {self.active_revision!r} must be approved"
                )
        return self


class ProjectBaselineRegistry(BaseModel):
    version: int = 1
    projects: dict[str, ProjectBaselineConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_version(self) -> "ProjectBaselineRegistry":
        if self.version != 1:
            raise ValueError(f"Unsupported ProjectBaseline registry version: {self.version}")
        return self


class ProjectBaseline(BaseModel):
    """Resolved immutable metadata snapshot governing one unit of work."""

    project_id: str
    revision: str
    status: Literal["approved"] = "approved"
    source_commit: str
    references: BaselineReferences


def resolve_project_baseline(
    project_id: str,
    requested_revision: str | None = None,
) -> ProjectBaseline | None:
    """Resolve the approved baseline governing new work.

    A project without baseline metadata remains valid during Phase 2 for backward
    compatibility. An explicit revision request always fails closed when the
    project/revision is unknown or is not currently approved.
    """

    registry = ProjectBaselineRegistry.model_validate(project_baselines_doc())
    project = registry.projects.get(project_id)

    if project is None:
        if requested_revision:
            raise ValueError(
                f"Project {project_id!r} has no ProjectBaseline revision {requested_revision!r}"
            )
        return None

    revision = requested_revision.strip() if requested_revision else project.active_revision
    if not revision:
        return None
    if not _REVISION_RE.fullmatch(revision):
        raise ValueError(f"Invalid ProjectBaseline revision: {revision}")

    definition = project.revisions.get(revision)
    if definition is None:
        raise ValueError(f"Unknown ProjectBaseline revision {revision!r} for project {project_id!r}")
    if definition.status != "approved":
        raise ValueError(
            f"ProjectBaseline revision {revision!r} for project {project_id!r} is not approved"
        )

    return ProjectBaseline(
        project_id=project_id,
        revision=revision,
        status="approved",
        source_commit=definition.source_commit,
        references=definition.references,
    )
