from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

import app.main as main
from app.main import OrphanResourcesRequest, orphan_resources


JOB_ID = "0123456789abcdef0123456789abcdef"
SITE = "cp-0123456789"
WORKSPACE = "/workspaces/" + JOB_ID


def configure(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "projects.yml"
    config.write_text(
        yaml.safe_dump(
            {
                "projects": {
                    "demo": {
                        "path": str(tmp_path / "unused"),
                        "base_branch": "main",
                        "runtime": {"branch_prefix": "ai"},
                        "ddev": {"enabled": True},
                    }
                }
            }
        )
    )
    monkeypatch.setenv("PROJECTS_FILE", str(config))
    monkeypatch.setattr(main, "_job_has_active_process", lambda value: False)


class DockerFixture:
    def __init__(self):
        self.present = True
        self.running = False
        self.foreign_volume_reference = False
        self.foreign_image_reference = False
        self.calls = []

    def __call__(self, argv, *, timeout=60):
        args = list(argv)
        self.calls.append(args)

        if args[:2] == ["ps", "-a"] and "label=com.ddev.site-name=" + SITE in args:
            return "container-1\n" if self.present else ""

        if args[:2] == ["inspect", "--format"] and args[-1] == "container-1":
            running = "true" if self.running else "false"
            return (
                f"container-1|/{SITE}-web|{running}|{SITE}|ddev\n"
            )

        if args[:2] == ["volume", "ls"]:
            if not self.present:
                return "unrelated-postgres\n"
            return f"{SITE}-postgres\nunrelated-postgres\n"

        if args[:2] == ["volume", "inspect"]:
            return f"{SITE}-postgres|{SITE}\n"

        if args[:2] == ["ps", "-a"] and any(
            item == f"volume={SITE}-postgres" for item in args
        ):
            if self.foreign_volume_reference:
                return "foreign-container\n"
            return "container-1\n" if self.present else ""

        if args[:2] == ["image", "ls"]:
            if not self.present:
                return "postgres|17|sha256:base\n"
            return (
                f"postgres|17-{SITE}-built|sha256:image-1\n"
                "postgres|17|sha256:base\n"
            )

        if args[:2] == ["image", "inspect"]:
            return (
                f"sha256:image-1|{SITE}|ddev|{WORKSPACE}\n"
            )

        if args[:2] == ["ps", "-a"] and any(
            item == "ancestor=sha256:image-1" for item in args
        ):
            if self.foreign_image_reference:
                return "foreign-container\n"
            return "container-1\n" if self.present else ""

        if args and args[0] == "rm":
            assert args[1:] == ["container-1"]
            return ""

        if args[:2] == ["volume", "rm"]:
            assert args[2:] == [f"{SITE}-postgres"]
            return ""

        if args[:2] == ["image", "rm"]:
            assert args[2:] == [f"postgres:17-{SITE}-built"]
            self.present = False
            return ""

        raise AssertionError(f"Unexpected docker argv: {args}")


def request(*, execute: bool) -> OrphanResourcesRequest:
    return OrphanResourcesRequest(
        job_id=JOB_ID,
        project_id="demo",
        workspace=WORKSPACE,
        execute=execute,
    )


def test_orphan_resources_inspect_is_read_only_and_exact(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path)
    docker = DockerFixture()
    monkeypatch.setattr(main, "_docker_output", docker)

    result = orphan_resources(request(execute=False))

    assert result["mode"] == "inspect"
    assert result["released"] is False
    before = result["before"]
    assert before["site"] == SITE
    assert before["resource_count"] == 3
    assert [item["name"] for item in before["containers"]] == [f"{SITE}-web"]
    assert [item["name"] for item in before["volumes"]] == [f"{SITE}-postgres"]
    assert [item["ref"] for item in before["images"]] == [
        f"postgres:17-{SITE}-built"
    ]
    assert not any(call and call[0] == "rm" for call in docker.calls)
    assert not any(call[:2] == ["volume", "rm"] for call in docker.calls)
    assert not any(call[:2] == ["image", "rm"] for call in docker.calls)


def test_orphan_resources_execute_removes_only_exact_resources_and_is_idempotent(
    tmp_path,
    monkeypatch,
):
    configure(monkeypatch, tmp_path)
    docker = DockerFixture()
    monkeypatch.setattr(main, "_docker_output", docker)

    first = orphan_resources(request(execute=True))

    assert first["mode"] == "execute"
    assert first["released"] is True
    assert first["before"]["resource_count"] == 3
    assert first["after"]["resource_count"] == 0
    assert ["rm", "container-1"] in docker.calls
    assert ["volume", "rm", f"{SITE}-postgres"] in docker.calls
    assert ["image", "rm", f"postgres:17-{SITE}-built"] in docker.calls

    second = orphan_resources(request(execute=True))

    assert second["released"] is False
    assert second["before"]["resource_count"] == 0
    assert second["after"]["resource_count"] == 0


def test_orphan_resources_refuses_running_exact_container(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path)
    docker = DockerFixture()
    docker.running = True
    monkeypatch.setattr(main, "_docker_output", docker)

    with pytest.raises(HTTPException) as exc:
        orphan_resources(request(execute=True))

    assert exc.value.status_code == 409
    assert "running container" in str(exc.value.detail)
    assert not any(call and call[0] == "rm" for call in docker.calls)


def test_orphan_resources_refuses_foreign_volume_reference(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path)
    docker = DockerFixture()
    docker.foreign_volume_reference = True
    monkeypatch.setattr(main, "_docker_output", docker)

    with pytest.raises(HTTPException) as exc:
        orphan_resources(request(execute=False))

    assert exc.value.status_code == 409
    assert "unrelated container" in str(exc.value.detail)


def test_orphan_resources_refuses_foreign_image_reference(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path)
    docker = DockerFixture()
    docker.foreign_image_reference = True
    monkeypatch.setattr(main, "_docker_output", docker)

    with pytest.raises(HTTPException) as exc:
        orphan_resources(request(execute=False))

    assert exc.value.status_code == 409
    assert "unrelated container" in str(exc.value.detail)


def test_orphan_resources_refuses_active_executor_process(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "_job_has_active_process", lambda value: True)
    docker = DockerFixture()
    monkeypatch.setattr(main, "_docker_output", docker)

    with pytest.raises(HTTPException) as exc:
        orphan_resources(request(execute=False))

    assert exc.value.status_code == 409
    assert docker.calls == []


def test_orphan_resources_requires_full_runtime_job_id(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path)

    with pytest.raises(Exception):
        OrphanResourcesRequest(
            job_id="0123456789",
            project_id="demo",
            workspace=WORKSPACE,
            execute=False,
        )
