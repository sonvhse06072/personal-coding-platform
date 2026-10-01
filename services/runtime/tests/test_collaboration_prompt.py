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


def test_pm_handoff_prompt_forbids_third_round_and_allows_runtime_verification():
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
    context = {
        "thread_id": "ct-handoff",
        "role": "test_engineer",
        "status": "pm_handoff",
        "round": 2,
        "recommendation": "No remaining code-side repair identified; run deterministic verification.",
        "risks": ["PHP is unavailable in the collaborator sandbox."],
        "suggested_tests": ["Run the exact Kernel target."],
        "unresolved": True,
        "previous_failure": None,
    }
    failure = "PCP_COLLABORATION_CONTEXT: " + __import__("json").dumps(context)

    prompt = execution_prompt(
        task=task,
        route=route,
        repo_analysis={"estimated_files": 2},
        collaboration_context=context,
        failure=failure,
    )

    assert "Do not create another collaboration request or recheck for this thread." in prompt
    assert "Do not request another recheck or create a replacement thread" in prompt
    assert "do not invent a code change" in prompt
    assert "Runtime verification" in prompt
