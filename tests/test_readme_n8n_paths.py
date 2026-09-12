from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

STATUS_WEBHOOK_ID = "f94fd841-0da8-42af-a06a-17b78d5a1ea7"
DECISION_WEBHOOK_ID = "a0db357c-167e-43c4-a692-e049aa21ef63"


def test_readme_documents_stable_dynamic_n8n_production_paths() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "POST /webhook/coding-platform/jobs" in readme
    assert f"GET  /webhook/{STATUS_WEBHOOK_ID}/coding-platform/jobs/<job_id>" in readme
    assert (
        f"POST /webhook/{DECISION_WEBHOOK_ID}/coding-platform/jobs/<job_id>/decision"
        in readme
    )

    assert (
        f"https://personal-coding-platform.ddev.site:5679/webhook/{STATUS_WEBHOOK_ID}/"
        "coding-platform/jobs/<job_id>"
        in readme
    )
    assert (
        f"https://personal-coding-platform.ddev.site:5679/webhook/{DECISION_WEBHOOK_ID}/"
        "coding-platform/jobs/<job_id>/decision"
        in readme
    )

    assert "GET  /webhook/coding-platform/jobs/<job_id>" not in readme
    assert "POST /webhook/coding-platform/jobs/<job_id>/decision" not in readme
