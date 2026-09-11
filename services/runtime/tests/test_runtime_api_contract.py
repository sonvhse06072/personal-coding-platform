from app.schemas import HumanDecisionRequest, JobRunRequest


def test_run_request_defaults_to_preserving_provider_failures():
    assert JobRunRequest().reset_transient_provider_failures is False


def test_human_decision_request_is_explicit():
    assert HumanDecisionRequest(action="approve", note="ok").action == "approve"
