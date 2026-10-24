"""Test suite for FastAPI REST endpoints, SSE telemetry, and Jinja2 templates (app/main.py)."""

import asyncio
import json
import os
from fastapi.testclient import TestClient
import pytest

from app.core.vault import create_sample_profile
from app.main import app, set_fill_orchestrator
from app.models.browser_schema import FillResult
from app.models.ciba_schema import RefusalToSubmitError


class MockAPIOrchestrator:
    """Mock orchestrator simulating pipeline execution for fast, deterministic API tests."""

    def __init__(self, should_fail: bool = False, refusal: bool = False):
        self.should_fail = should_fail
        self.refusal = refusal

    async def run(self, target_url: str, dry_run: bool = True, progress_callback=None, **kwargs):
        if progress_callback:
            progress_callback("SESSION_INIT", 10)
            await asyncio.sleep(0.01)
            progress_callback("DOM_EXTRACTION", 30)
            await asyncio.sleep(0.01)
            progress_callback("AI_REASONING", 50)
            await asyncio.sleep(0.01)
            progress_callback("CIBA_CONSENT", 70)
            await asyncio.sleep(0.01)
            progress_callback("FORM_FILLING", 90)
            await asyncio.sleep(0.01)

        if self.refusal:
            raise RefusalToSubmitError("Simulated CIBA user consent denial")

        if self.should_fail:
            raise RuntimeError("Simulated pipeline failure")

        return FillResult(
            status="DRY_RUN_SUCCESS" if dry_run else "SUBMITTED",
            session_id="api_test_sess_001",
            replay_url="https://browserbase.com/sessions/api_test_sess_001",
            live_view_url="https://browserbase.com/sessions/api_test_sess_001/live",
            screenshot_path="artifacts/screenshots/api_test_sess_001_dry_run.png",
            fields_filled_count=7,
            submit_button_detected="button#submit",
            dry_run=dry_run,
            submitted=not dry_run,
            diff=[
                {
                    "field": "Full Name",
                    "selector": "input#full_name",
                    "field_type": "text",
                    "value": "Arjun Sharma",
                    "tier": "PUBLIC",
                    "status": "Filled",
                },
                {
                    "field": "Email",
                    "selector": "input#email",
                    "field_type": "email",
                    "value": "arjun.sharma@example.com",
                    "tier": "PUBLIC",
                    "status": "Filled",
                },
                {
                    "field": "Phone",
                    "selector": "input#phone",
                    "field_type": "tel",
                    "value": "******3210",
                    "tier": "SEMI_SENSITIVE",
                    "status": "Filled",
                },
            ],
        )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Provides FastAPI TestClient with isolated temporary vault storage."""
    from app.config import get_settings
    settings = get_settings()
    isolated_vault = str(tmp_path / "test_api_vault.enc")
    monkeypatch.setattr(settings, "VAULT_FILE_PATH", isolated_vault)
    set_fill_orchestrator(lambda **kwargs: MockAPIOrchestrator())
    with TestClient(app) as test_client:
        yield test_client
    set_fill_orchestrator(None)


def test_health_endpoint(client):
    """Verify /health returns HTTP 200, healthy status, service name, and subsystems."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == "slothform"
    assert data["version"] == "1.0.0"
    assert "timestamp" in data
    assert "uptime_seconds" in data
    assert "subsystems" in data
    assert "vault" in data["subsystems"]
    assert "browserbase" in data["subsystems"]
    assert "ultramarine" in data["subsystems"]


def test_submit_fill_task_valid_url(client):
    """Verify POST /api/fill with valid URL creates background task and returns pending status."""
    payload = {
        "url": "https://boards.greenhouse.io/stripe/jobs/101",
        "dry_run": True,
    }
    response = client.post("/api/fill", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "task_id" in data
    assert data["status"] == "pending"
    assert data["dry_run"] is True


def test_submit_fill_task_invalid_url(client):
    """Verify POST /api/fill rejects malformed non-HTTP URLs with 422."""
    payload = {
        "url": "ftp://not-supported.org",
        "dry_run": True,
    }
    response = client.post("/api/fill", json=payload)
    assert response.status_code == 422

    empty_payload = {"url": "", "dry_run": True}
    response_empty = client.post("/api/fill", json=empty_payload)
    assert response_empty.status_code == 422


def test_get_task_status_found_and_not_found(client):
    """Verify GET /api/tasks/{task_id} returns task status or 404 for unknown task."""
    # 404 for unknown
    res_404 = client.get("/api/tasks/non_existent_uuid_12345")
    assert res_404.status_code == 404

    # 200 for existing
    post_res = client.post("/api/fill", json={"url": "https://jobs.lever.co/postman/dev", "dry_run": True})
    task_id = post_res.json()["task_id"]

    res_found = client.get(f"/api/tasks/{task_id}")
    assert res_found.status_code == 200
    task_data = res_found.json()
    assert task_data["task_id"] == task_id
    assert task_data["url"] == "https://jobs.lever.co/postman/dev"
    assert task_data["dry_run"] is True
    assert task_data["status"] in ("pending", "running", "completed")


def test_sse_events_endpoint(client):
    """Verify GET /api/tasks/{task_id}/events streams SSE with text/event-stream content type."""
    # Create task
    post_res = client.post("/api/fill", json={"url": "https://jobs.ashbyhq.com/openai/swe", "dry_run": True})
    task_id = post_res.json()["task_id"]

    # Request SSE stream
    with client.stream("GET", f"/api/tasks/{task_id}/events") as stream_res:
        assert stream_res.status_code == 200
        content_type = stream_res.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        # Read first chunk
        for line in stream_res.iter_lines():
            if line.startswith("data:"):
                event_data = json.loads(line.replace("data:", "").strip())
                assert "stage" in event_data
                assert "percentage" in event_data
                assert "message" in event_data
                break


def test_sse_events_unknown_task_404(client):
    """Verify GET /api/tasks/{task_id}/events returns 404 for unknown task."""
    res = client.get("/api/tasks/unknown_uuid/events")
    assert res.status_code == 404


def test_vault_get_masked_profile(client):
    """Verify GET /api/vault returns masked MasterIdentityProfile."""
    response = client.get("/api/vault")
    assert response.status_code == 200
    data = response.json()

    assert "core" in data
    assert "tax" in data
    assert "financial" in data
    assert "career" in data

    # Verify sensitive data masking
    assert "ABCDE****F" in str(data["tax"]["pan"])
    assert "****" in str(data["financial"]["account_number"])
    assert "*" in str(data["core"]["phone"])


def test_vault_post_update_profile(client, tmp_path, monkeypatch):
    """Verify POST /api/vault updates identity profile with isolated storage."""
    from app.config import get_settings

    settings = get_settings()
    custom_vault = str(tmp_path / "isolated_vault_post.enc")
    monkeypatch.setattr(settings, "VAULT_FILE_PATH", custom_vault)

    profile = create_sample_profile()
    profile.core.full_name = "Arjun Sharma Updated"

    response = client.post("/api/vault", json=profile.model_dump())
    assert response.status_code == 200
    assert response.json()["status"] == "saved"
    assert os.path.exists(custom_vault)


def test_web_dashboard_html_routes(client):
    """Verify GET / and GET /tasks/{task_id} render Jinja2 HTML with required UI elements."""
    # Root dashboard
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "text/html" in root_res.headers.get("content-type", "")
    html = root_res.text

    # Assert required element IDs
    assert 'id="stage-progress-bar"' in html
    assert 'id="browserbase-replay-frame"' in html
    assert 'id="diff-inspection-modal"' in html
    assert 'style="display: none;"' in html
    assert 'id="vault-status-badge"' in html
    assert 'id="target-url-input"' in html
    assert 'id="ciba-consent-card"' in html
    assert 'id="ciba-approve-btn"' in html
    assert 'id="ciba-reject-btn"' in html
    assert "SlothForm" in html

    # Verify no emojis in HTML
    for forbidden_emoji in ["🦥", "🛡️", "⚡", "📋", "↗", "✓", "✗", "⏳", "⚠️"]:
        assert forbidden_emoji not in html

    # Task detail view
    task_res = client.get("/tasks/task_abc_123")
    assert task_res.status_code == 200
    assert "text/html" in task_res.headers.get("content-type", "")
    task_html = task_res.text
    assert "task_abc_123" in task_html
    assert 'id="stage-progress-bar"' in task_html
    assert 'id="browserbase-replay-frame"' in task_html
    assert 'id="ciba-consent-card"' in task_html
    assert 'id="target-url-link"' in task_html
    assert 'id="diff-inspection-modal"' in task_html
    assert 'style="display: none;"' in task_html

    for forbidden_emoji in ["🦥", "🛡️", "⚡", "📋", "↗", "✓", "✗", "⏳", "⚠️"]:
        assert forbidden_emoji not in task_html


def test_post_task_consent_approval(client):
    """Verify POST /api/tasks/{task_id}/consent approves a task."""
    post_res = client.post("/api/fill", json={"url": "https://boards.greenhouse.io/stripe/jobs/101", "dry_run": True})
    task_id = post_res.json()["task_id"]

    consent_res = client.post(f"/api/tasks/{task_id}/consent", json={"approved": True})
    assert consent_res.status_code == 200
    data = consent_res.json()
    assert data["task_id"] == task_id
    assert data["approved"] is True
    assert data["status"] == "approved"


def test_post_task_consent_rejection(client):
    """Verify POST /api/tasks/{task_id}/consent rejects a task."""
    post_res = client.post("/api/fill", json={"url": "https://boards.greenhouse.io/stripe/jobs/102", "dry_run": True})
    task_id = post_res.json()["task_id"]

    consent_res = client.post(f"/api/tasks/{task_id}/consent", json={"approved": False})
    assert consent_res.status_code == 200
    data = consent_res.json()
    assert data["task_id"] == task_id
    assert data["approved"] is False
    assert data["status"] == "rejected"


def test_post_task_consent_unknown_404(client):
    """Verify POST /api/tasks/{task_id}/consent returns 404 for unknown task."""
    consent_res = client.post("/api/tasks/nonexistent_task_123/consent", json={"approved": True})
    assert consent_res.status_code == 404


def test_pipeline_refusal_terminal_status(client):
    """Verify pipeline RefusalToSubmitError sets task status to 'refused'."""
    set_fill_orchestrator(lambda **kwargs: MockAPIOrchestrator(refusal=True))
    post_res = client.post("/api/fill", json={"url": "https://boards.greenhouse.io/stripe/jobs/103", "dry_run": True})
    task_id = post_res.json()["task_id"]

    import time
    time.sleep(0.1)

    status_res = client.get(f"/api/tasks/{task_id}")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "refused"


def test_pipeline_failure_terminal_status(client):
    """Verify pipeline error sets task status to 'failed'."""
    set_fill_orchestrator(lambda **kwargs: MockAPIOrchestrator(should_fail=True))
    post_res = client.post("/api/fill", json={"url": "https://boards.greenhouse.io/stripe/jobs/104", "dry_run": True})
    task_id = post_res.json()["task_id"]

    import time
    time.sleep(0.1)

    status_res = client.get(f"/api/tasks/{task_id}")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "failed"


def test_task_diff_in_get_status(client):
    """Verify GET /api/tasks/{task_id} contains diff and result details upon completion."""
    set_fill_orchestrator(lambda **kwargs: MockAPIOrchestrator())
    post_res = client.post("/api/fill", json={"url": "https://boards.greenhouse.io/stripe/jobs/105", "dry_run": True})
    task_id = post_res.json()["task_id"]

    import time
    time.sleep(0.15)

    status_res = client.get(f"/api/tasks/{task_id}")
    assert status_res.status_code == 200
    task_data = status_res.json()
    assert task_data["status"] == "completed"
    assert "diff" in task_data
    assert len(task_data["diff"]) > 0
    assert task_data["diff"][0]["field"] == "Full Name"
    assert task_data["diff"][0]["tier"] == "PUBLIC"


def test_vault_raw_profile_endpoint(client):
    """Verify GET /api/vault/profile returns unmasked MasterIdentityProfile for setup UI."""
    response = client.get("/api/vault/profile")
    assert response.status_code == 200
    data = response.json()

    assert "core" in data
    assert "career" in data
    assert "tax" in data
    assert "financial" in data

    # Core checks
    assert data["core"]["full_name"] == "Arjun Sharma"
    assert data["core"]["email"] == "arjun.sharma@example.com"
    # Unmasked raw phone in raw profile endpoint
    assert "+919876543210" in data["core"]["phone"]

    # Tax checks
    assert data["tax"]["pan"] == "ABCDE1234F"
    assert data["tax"]["tax_residence_country"] == "India"


def test_vault_status_endpoint(client):
    """Verify GET /api/vault/status reports initialization and active profile."""
    response = client.get("/api/vault/status")
    assert response.status_code == 200
    data = response.json()

    assert "initialized" in data
    assert "locked" in data
    assert "active_profile" in data
    assert data["active_profile"] == "Arjun Sharma"


def test_post_vault_profile_endpoint(client, tmp_path, monkeypatch):
    """Verify POST /api/vault/profile saves updated profile and returns confirmation."""
    from app.config import get_settings

    settings = get_settings()
    custom_vault = str(tmp_path / "custom_profile_vault.enc")
    monkeypatch.setattr(settings, "VAULT_FILE_PATH", custom_vault)

    profile = create_sample_profile()
    profile.core.full_name = "Priya Patel"
    profile.core.email = "priya.patel@example.com"
    profile.career.headline = "Lead Cloud Security Architect"
    profile.career.education_degree = "M.S. in Cybersecurity"
    profile.career.education_university = "IIT Delhi"

    response = client.post("/api/vault/profile", json=profile.model_dump())
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "saved"
    assert "Priya Patel" in data["message"]
    assert "profile" in data
    assert data["profile"]["core"]["full_name"] == "Priya Patel"

    # Verify GET /api/vault/profile now returns updated profile
    get_res = client.get("/api/vault/profile")
    assert get_res.status_code == 200
    assert get_res.json()["core"]["full_name"] == "Priya Patel"
    assert get_res.json()["career"]["headline"] == "Lead Cloud Security Architect"
    assert get_res.json()["career"]["education_degree"] == "M.S. in Cybersecurity"


def test_dashboard_contains_profile_setup_ui_elements(client):
    """Verify dashboard contains Identity Vault Setup and runner identity elements."""
    root_res = client.get("/")
    assert root_res.status_code == 200
    html = root_res.text

    assert 'id="tab-btn-runner"' in html
    assert 'id="tab-btn-setup"' in html
    assert 'id="runner-view"' in html
    assert 'id="setup-view"' in html
    assert 'id="runner-profile-name"' in html
    assert 'id="runner-profile-email"' in html
    assert 'id="header-profile-name"' in html
    assert 'id="profile-setup-form"' in html
    assert 'id="core-full-name"' in html
    assert 'id="core-email"' in html
    assert 'id="core-phone"' in html
    assert 'id="career-skills"' in html
    assert 'id="career-resume-markdown"' in html
    assert 'id="save-profile-btn"' in html
    assert 'id="load-sample-btn"' in html
    assert 'id="clear-profile-btn"' in html
    assert 'id="vault-save-toast"' in html
    assert 'id="go-runner-btn"' in html
    assert 'id="resume-dropzone"' in html


def test_upload_resume_file_txt_and_md(client):
    """Verify POST /api/vault/resume successfully parses plaintext and markdown resumes."""
    sample_md = b"# Jane Doe\n\nExperienced Cloud Architect with 10+ years designing distributed systems."
    response = client.post(
        "/api/vault/resume",
        files={"file": ("resume.md", sample_md, "text/markdown")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["filename"] == "resume.md"
    assert "Jane Doe" in data["text"]
    assert "Experienced Cloud Architect" in data["text"]


def test_upload_resume_file_pdf(client):
    """Verify POST /api/vault/resume extracts text from real PDF documents."""
    from app.services.document_generator import SyntheticDocumentGenerator

    gen = SyntheticDocumentGenerator()
    pdf_path = gen.generate_resume(
        profile={"name": "Vikram Sethi", "email": "vikram@example.com", "summary": "Senior SRE specialized in Kubernetes."}
    )

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    response = client.post(
        "/api/vault/resume",
        files={"file": ("vikram_resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["filename"] == "vikram_resume.pdf"
    assert data["pages"] >= 1
    assert "Vikram Sethi" in data["text"] or "Kubernetes" in data["text"]


def test_upload_resume_file_unsupported_format(client):
    """Verify POST /api/vault/resume rejects unsupported file extensions."""
    response = client.post(
        "/api/vault/resume",
        files={"file": ("malicious.exe", b"binary_data", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]

