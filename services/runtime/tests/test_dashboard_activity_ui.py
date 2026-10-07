from app.dashboard_ui import DASHBOARD_HTML


def test_dashboard_uses_provider_neutral_live_activity_labels_and_filters():
    assert ">Live Developer Activity<" in DASHBOARD_HTML
    assert ">Developer activity<" in DASHBOARD_HTML
    assert "model/tool/verification activity across providers" in DASHBOARD_HTML
    assert "runtime_activity" in DASHBOARD_HTML
    assert "activityIdentity" in DASHBOARD_HTML
    assert "d.provider" in DASHBOARD_HTML
    assert "d.model" in DASHBOARD_HTML
    assert "d.adapter" in DASHBOARD_HTML
    assert "raw chain-of-thought and secrets are never exposed" in DASHBOARD_HTML



def test_dashboard_activity_renders_estimated_job_progress_bar():
    assert 'id="jobProgress"' in DASHBOARD_HTML
    assert "Estimated workflow progress · not ETA or budget usage" in DASHBOARD_HTML
    assert "renderWorkflowProgress" in DASHBOARD_HTML
    assert 'role="progressbar"' in DASHBOARD_HTML
    assert 'aria-label="Estimated workflow progress"' in DASHBOARD_HTML
    assert "j.workflow_progress" in DASHBOARD_HTML
    assert "p.paused===true" in DASHBOARD_HTML


def test_dashboard_exposes_direct_preview_controls_without_internal_runtime_credentials():
    assert 'id="previewCard"' in DASHBOARD_HTML
    assert "j.workspace_mode!=='direct'" in DASHBOARD_HTML
    assert '<option value="frontend">Frontend</option>' in DASHBOARD_HTML
    assert '<option value="backend">Backend</option>' in DASHBOARD_HTML
    assert '<option value="both">Both</option>' in DASHBOARD_HTML
    assert "Start Preview" in DASHBOARD_HTML
    assert "Rebuild" in DASHBOARD_HTML
    assert "Stop" in DASHBOARD_HTML
    assert "Unlock controls" in DASHBOARD_HTML
    assert 'target="_blank" rel="noopener noreferrer"' in DASHBOARD_HTML
    assert "/v1/dashboard/control-session" in DASHBOARD_HTML
    assert "/v1/dashboard/jobs/" in DASHBOARD_HTML
    assert "localStorage" not in DASHBOARD_HTML
    assert "sessionStorage" not in DASHBOARD_HTML
    assert "RUNTIME_API_TOKEN" not in DASHBOARD_HTML
    assert "PLATFORM_INTERNAL_TOKEN" not in DASHBOARD_HTML
    assert "GITHUB_DELIVERY_TOKEN" not in DASHBOARD_HTML
    assert "reconcilePreviewMutation" in DASHBOARD_HTML
    assert "Preview connection was interrupted and status reconciliation timed out." in DASHBOARD_HTML
    assert "expectedGeneration" in DASHBOARD_HTML


def test_dashboard_preview_keeps_existing_activity_quota_and_stream_surfaces():
    assert ">Live Developer Activity<" in DASHBOARD_HTML
    assert "quotaSnapshot" in DASHBOARD_HTML
    assert "/v1/dashboard/quota" in DASHBOARD_HTML
    assert "new EventSource(" in DASHBOARD_HTML
    assert "/stream?after=" in DASHBOARD_HTML


def test_dashboard_exposes_project_level_current_site_preview():
    assert 'id="projectPreviewCard"' in DASHBOARD_HTML
    assert ">Current site<" in DASHBOARD_HTML
    assert "available even when no WorkOrder is active" in DASHBOARD_HTML
    assert 'id="projectPreviewProject"' in DASHBOARD_HTML
    assert 'id="projectPreviewTarget"' in DASHBOARD_HTML
    assert "Stop Frontend" in DASHBOARD_HTML
    assert "/v1/dashboard/project-previews" in DASHBOARD_HTML
    assert "/v1/dashboard/projects/" in DASHBOARD_HTML
    assert "refreshProjectPreview" in DASHBOARD_HTML
    assert "reconcileProjectPreviewMutation" in DASHBOARD_HTML
    assert "Active direct job owns this project" in DASHBOARD_HTML
    assert "uncommitted changes" in DASHBOARD_HTML
    assert "localStorage" not in DASHBOARD_HTML
    assert "sessionStorage" not in DASHBOARD_HTML
    assert "/home/sonvh/chonhac" not in DASHBOARD_HTML


def test_dashboard_exposes_standalone_job_observability_without_synthetic_work_orders():
    assert ">Standalone jobs<" in DASHBOARD_HTML
    assert 'id="standaloneCard"' in DASHBOARD_HTML
    assert 'id="standaloneSelect"' in DASHBOARD_HTML
    assert "snapshot.standalone_jobs" in DASHBOARD_HTML
    assert "currentStandalone" in DASHBOARD_HTML
    assert "selectedStandalone" in DASHBOARD_HTML
    assert "/v1/dashboard/jobs/" in DASHBOARD_HTML


def test_dashboard_clears_stale_activity_when_no_current_job():
    assert (
        "if(!j){$('#jobMeta').textContent='No active job';"
        "$('#jobStatus').innerHTML='';renderWorkflowProgress(null);"
        "$('#metrics').innerHTML='';"
        "$('#models').innerHTML='';consoleEvents=[];lastSeq=0;"
        "renderConsole();connectStream(null);return}"
        in DASHBOARD_HTML
    )
