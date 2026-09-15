from app.prompts import execution_prompt


def test_work_order_prompt_exposes_bounded_control_artifact_without_model_identity():
    task = {
        "title": "Implement bounded collaboration",
        "description": "AUTHORITATIVE WORKORDER / TASK CONTRACT. Do not reinterpret, broaden, or override this contract.",
    }
    route = {
        "strategy": {
            "profile": "standard",
            "definition_of_done": {"required": ["targeted_tests_pass"]},
        }
    }

    prompt = execution_prompt(
        task=task,
        route=route,
        repo_analysis={"estimated_files": 2},
    )

    assert ".pcp-collaboration-request.json" in prompt
    assert '"role":"test_engineer"' in prompt
    assert '"action":"recheck"' in prompt
    assert "Never name or choose a provider/model" in prompt
    assert "raw transcripts" in prompt
    assert "PCP_COLLABORATION_REQUEST:" not in prompt


def test_legacy_task_does_not_gain_collaboration_control_surface():
    task = {"title": "Legacy task", "description": "Make a small change."}
    route = {
        "strategy": {
            "profile": "standard",
            "definition_of_done": {"required": ["targeted_tests_pass"]},
        }
    }

    prompt = execution_prompt(
        task=task,
        route=route,
        repo_analysis={"estimated_files": 1},
    )

    assert ".pcp-collaboration-request.json" not in prompt
