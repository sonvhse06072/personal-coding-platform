from app.repo import task_requires_material_change, tokenize


def test_tokenize_removes_common_words():
    result = tokenize("Fix the intermittent payment synchronization bug with Salesforce API")
    assert "fix" not in result
    assert "payment" in result
    assert "salesforce" in result


def test_material_change_intent_is_inferred():
    assert task_requires_material_change({"title": "Add a small automated test", "task_type": "unknown"}) is True
    assert task_requires_material_change({"title": "Explain how this service works", "task_type": "analysis"}) is False
