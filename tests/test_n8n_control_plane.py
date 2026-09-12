from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / ".ddev" / "docker-compose.platform.yaml"
WORKFLOW_DIR = ROOT / "n8n" / "workflows"
SYNC_SCRIPT = ROOT / "scripts" / "n8n-control-plane.sh"
GLOBAL_ENV_EXAMPLE = ROOT / ".ddev" / ".env.example"
N8N_ENV_EXAMPLE = ROOT / ".ddev" / ".env.n8n.local.example"

EXPECTED_WORKFLOWS = {
    "job-intake.json": {
        "id": "pcpJobIntakeV001",
        "method": "POST",
        "path": "coding-platform/jobs",
    },
    "job-status.json": {
        "id": "pcpJobStatusV001",
        "method": "GET",
        "path": "coding-platform/jobs/:job_id",
        "webhook_id": "f94fd841-0da8-42af-a06a-17b78d5a1ea7",
    },
    "human-decision.json": {
        "id": "pcpHumanDecision1",
        "method": "POST",
        "path": "coding-platform/jobs/:job_id/decision",
        "webhook_id": "a0db357c-167e-43c4-a692-e049aa21ef63",
    },
}

FORBIDDEN_N8N_SECRETS = {
    "ROUTER_API_TOKEN",
    "PLATFORM_INTERNAL_TOKEN",
    "ANTIGRAVITY_BRIDGE_TOKEN",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "GITHUB_DELIVERY_TOKEN",
}


def load_compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_n8n_is_runtime_only_and_pinned() -> None:
    n8n = load_compose()["services"]["n8n"]
    env = n8n["environment"]

    assert "2.38.6" in n8n["image"]
    assert "latest" not in n8n["image"]
    assert env["RUNTIME_INTERNAL_URL"] == "http://coding-runtime:8787"
    assert env["N8N_BLOCK_ENV_ACCESS_IN_NODE"] == "false"

    # Credentials are injected through .ddev/.env.n8n.local, never interpolated
    # through the global DDEV Compose environment.
    assert "RUNTIME_API_TOKEN" not in env
    assert "N8N_CONTROL_PLANE_TOKEN" not in env
    assert "N8N_ENCRYPTION_KEY" not in env
    for key in FORBIDDEN_N8N_SECRETS:
        assert key not in env

    assert "ROUTER_INTERNAL_URL" not in env
    assert any(str(volume).endswith("/n8n/workflows:/opt/pcp-workflows:ro") for volume in n8n["volumes"])

    excluded = json.loads(env["NODES_EXCLUDE"])
    assert "n8n-nodes-base.executeCommand" in excluded
    assert "n8n-nodes-base.readWriteFile" in excluded
    assert "n8n-nodes-base.localFileTrigger" in excluded


def test_workflows_are_versioned_runtime_proxies_only() -> None:
    files = {path.name: path for path in WORKFLOW_DIR.glob("*.json")}
    assert set(files) == set(EXPECTED_WORKFLOWS)

    seen_routes: set[tuple[str, str]] = set()
    for name, expected in EXPECTED_WORKFLOWS.items():
        workflow = json.loads(files[name].read_text(encoding="utf-8"))
        assert workflow["id"] == expected["id"]
        assert workflow["active"] is False
        assert workflow.get("credentials") in (None, {})

        webhook_nodes = [node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.webhook"]
        assert len(webhook_nodes) == 1
        webhook = webhook_nodes[0]
        params = webhook["parameters"]
        method = params.get("httpMethod", "GET")
        route = (method, params["path"])
        assert route == (expected["method"], expected["path"])
        assert route not in seen_routes
        seen_routes.add(route)

        # n8n 2.38.x requires webhookId as the leading production URL segment
        # for paths containing dynamic parameters such as :job_id. Keep these
        # identifiers stable in version control so callers get deterministic URLs.
        if ":job_id" in params["path"]:
            assert webhook.get("webhookId") == expected["webhook_id"]

        http_nodes = [node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.httpRequest"]
        assert len(http_nodes) == 1
        url = http_nodes[0]["parameters"]["url"]
        assert "RUNTIME_INTERNAL_URL" in url
        assert "ROUTER" not in url.upper()

        serialized = json.dumps(workflow)
        assert "N8N_CONTROL_PLANE_TOKEN" in serialized
        assert "RUNTIME_API_TOKEN" in serialized
        assert "ROUTER_API_TOKEN" not in serialized
        assert '"credentials"' not in serialized


def test_human_decision_workflow_preserves_runtime_contract() -> None:
    workflow = json.loads((WORKFLOW_DIR / "human-decision.json").read_text(encoding="utf-8"))
    nodes = {node["name"]: node for node in workflow["nodes"]}

    request = nodes["Resolve Human Decision"]["parameters"]
    assert request["method"] == "POST"
    assert request["url"] == (
        "={{ $env.RUNTIME_INTERNAL_URL + '/v1/jobs/' + $json.params.job_id + '/decision' }}"
    )
    assert request["sendBody"] is True
    assert request["specifyBody"] == "json"
    assert request["jsonBody"] == "={{ JSON.stringify($json.body) }}"

    headers = {
        item["name"]: item["value"]
        for item in request["headerParameters"]["parameters"]
    }
    assert headers["Authorization"] == "={{ 'Bearer ' + $env.RUNTIME_API_TOKEN }}"
    assert headers["Accept"] == "application/json"

    response = request["options"]["response"]["response"]
    assert response["fullResponse"] is True
    assert response["neverError"] is True

    reject = nodes["Reject Unauthorized"]["parameters"]
    assert reject["options"]["responseCode"] == 401
    assert "unauthorized" in reject["responseBody"]

    authorize = workflow["connections"]["Authorize Control Plane"]["main"]
    assert authorize[0][0]["node"] == "Resolve Human Decision"
    assert authorize[1][0]["node"] == "Reject Unauthorized"


def test_sync_is_bounded_and_fail_closed() -> None:
    script = SYNC_SCRIPT.read_text(encoding="utf-8")

    assert "import:workflow --separate" in script
    assert 'publish:workflow --id="$workflow_id"' in script
    assert "publish:workflow --all" not in script
    assert "update:workflow --all" not in script
    assert "assert_runtime_only_secret_boundary" in script
    assert '"GITHUB_DELIVERY_TOKEN"' in script
    assert "Expected unauthenticated control-plane request to return 401" in script
    assert "Expected authenticated status proxy to preserve Runtime 404" in script
    assert "f94fd841-0da8-42af-a06a-17b78d5a1ea7" in script
    assert "a0db357c-167e-43c4-a692-e049aa21ef63" in script
    assert "N8N_ENCRYPTION_KEY" in script
    assert "Refusing n8n secret migration" in script


def test_n8n_secrets_are_documented_service_scoped() -> None:
    global_env = GLOBAL_ENV_EXAMPLE.read_text(encoding="utf-8")
    n8n_env = N8N_ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "N8N_ENCRYPTION_KEY=" not in global_env
    assert "N8N_CONTROL_PLANE_TOKEN=" not in global_env
    assert "RUNTIME_API_TOKEN=" not in global_env
    assert "N8N_IMAGE=n8nio/n8n:2.38.6" in global_env

    keys = {
        line.split("=", 1)[0]
        for line in n8n_env.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    assert keys == {"RUNTIME_API_TOKEN", "N8N_ENCRYPTION_KEY", "N8N_CONTROL_PLANE_TOKEN"}
