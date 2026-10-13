"""C3B OCI overlays reuse cached base layers; CI never invokes Docker."""
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLES = {"router": ("router", "8090"), "executor": ("ddev-executor", "8790"),
         "runtime": ("runtime", "8787")}

@pytest.mark.parametrize("role", ROLES)
def test_f2_offline_overlay_is_minimal_and_scope_bound(role):
    source, port = ROLES[role]
    path = ROOT / f"deploy/fullpath/Dockerfile.c3b-{role}-overlay"
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    assert lines[:3] == ["ARG PCP_F2_BASE_IMAGE", "FROM ${PCP_F2_BASE_IMAGE}",
                         "ARG PCP_F2_SOURCE_SHA"]
    assert "ARG PCP_F2_BASE_ID" in lines
    assert 'org.opencontainers.image.revision="${PCP_F2_SOURCE_SHA}"' in "\n".join(lines)
    assert 'org.opencontainers.image.pcp.f2.base-id="${PCP_F2_BASE_ID}"' in "\n".join(lines)
    assert f'org.opencontainers.image.pcp.f2.role="{role}"' in "\n".join(lines)
    assert f"COPY services/{source}/app/ /opt/pcp-f2/app/" in lines
    assert "WORKDIR /opt/pcp-f2" in lines
    assert "ENV PYTHONPATH=/opt/pcp-f2" in lines
    assert f'"--port", "{port}"' in "\n".join(lines)
    assert not any(x.startswith(("RUN ", "ADD ", "ENTRYPOINT ", "ONBUILD ")) for x in lines)
    assert len([x for x in lines if x.startswith("COPY ")]) == 1
    assert (ROOT / "services" / source / "app").is_dir()

def test_parked_compose_and_accepted_db_unchanged():
    parked = yaml.safe_load((ROOT / "deploy/fullpath/compose.source-only.yml").read_text(encoding="utf-8"))
    for service in ("fullpath-router", "fullpath-executor", "fullpath-runtime"):
        assert parked["services"][service]["entrypoint"] == ["/bin/false"]
    c2 = yaml.safe_load((ROOT / "deploy/fullpath/compose.c2-db-only.yml").read_text(encoding="utf-8"))
    assert set(c2["services"]) == {"fullpath-db"}
