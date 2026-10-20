"""Comprehensive unit and integration tests for Browserbase cloud automation service and models."""

from unittest.mock import MagicMock
from app.models.browser_schema import (
    BrowserbaseSession,
    FieldType,
    FillPlan,
    FillPlanItem,
    FillResult,
    FormField,
    FormSchema,
    SubmitButton,
)
from app.services.browserbase_service import BrowserbaseService


# ==============================================================================
# 1. Pydantic Browser Schema Model Tests
# ==============================================================================


def test_field_type_enum():
    """Verify all expected field types are supported."""
    assert FieldType.TEXT == "text"
    assert FieldType.EMAIL == "email"
    assert FieldType.TEL == "tel"
    assert FieldType.URL == "url"
    assert FieldType.NUMBER == "number"
    assert FieldType.DATE == "date"
    assert FieldType.TEXTAREA == "textarea"
    assert FieldType.SELECT == "select"
    assert FieldType.CHECKBOX == "checkbox"
    assert FieldType.RADIO == "radio"
    assert FieldType.FILE == "file"
    assert FieldType.COMBOBOX == "combobox"


def test_form_field_model():
    """Verify FormField model construction and default values."""
    field = FormField(
        field_id="first_name",
        selector="#first_name",
        field_type=FieldType.TEXT,
        label="First Name *",
        required=True,
        placeholder="Enter your first name",
    )
    assert field.field_id == "first_name"
    assert field.selector == "#first_name"
    assert field.field_type == FieldType.TEXT
    assert field.required is True
    assert field.options == []
    assert field.frame_index == 0


def test_form_schema_model():
    """Verify FormSchema aggregates fields and submit buttons."""
    schema = FormSchema(
        url="https://jobs.lever.co/example/123/apply",
        page_title="Apply for Senior Engineer",
        fields=[
            FormField(
                field_id="name",
                selector="input[name='name']",
                field_type=FieldType.TEXT,
                label="Full Name",
                required=True,
            )
        ],
        submit_buttons=[
            SubmitButton(
                selector="button.template-btn-submit",
                text="Submit Application",
                is_primary=True,
            )
        ],
        has_iframes=False,
        detected_platform="lever",
    )
    assert schema.detected_platform == "lever"
    assert len(schema.fields) == 1
    assert len(schema.submit_buttons) == 1
    assert schema.submit_buttons[0].text == "Submit Application"


def test_fill_plan_and_result_models():
    """Verify FillPlan and FillResult modeling."""
    plan = FillPlan(
        target_url="https://boards.greenhouse.io/embed/job_app",
        items=[
            FillPlanItem(
                field_id="email",
                selector="#email",
                field_type=FieldType.EMAIL,
                value="dev@example.com",
            )
        ],
        resume_path="/path/to/resume.pdf",
    )
    assert len(plan.items) == 1
    assert plan.items[0].value == "dev@example.com"

    res = FillResult(
        status="DRY_RUN_SUCCESS",
        session_id="sess_test_123",
        replay_url="https://browserbase.com/sessions/sess_test_123",
        screenshot_path="/artifacts/screenshots/dry_run.png",
        fields_filled_count=1,
        submit_button_detected="button[type='submit']",
        dry_run=True,
        submitted=False,
    )
    assert res.status == "DRY_RUN_SUCCESS"
    assert res.dry_run is True
    assert res.submitted is False


# ==============================================================================
# 2. Browserbase Service Offline / Mock Mode Tests
# ==============================================================================


def test_browserbase_service_offline_initialization():
    """Verify offline mode is activated when dummy keys or offline flag is passed."""
    service = BrowserbaseService(api_key="bb_live_dummy_key", project_id="dummy_proj")
    assert service.offline is True
    assert service.client is None


def test_create_session_offline():
    """Verify offline session creation returns deterministic mock session."""
    service = BrowserbaseService(offline=True)
    session = service.create_session(timeout=1800, proxies=True, solve_captchas=True)

    assert isinstance(session, BrowserbaseSession)
    assert session.id.startswith("sess_mock_")
    assert "wss://connect.browserbase.com" in session.connect_url
    assert session.status == "RUNNING"


def test_get_debug_urls_offline():
    """Verify debug URLs in offline mode."""
    service = BrowserbaseService(offline=True)
    session_id = "sess_mock_xyz"
    debug_urls = service.get_debug_urls(session_id)

    assert "debugger_fullscreen_url" in debug_urls
    assert debug_urls["debugger_fullscreen_url"] == f"https://browserbase.com/sessions/{session_id}/debug"
    assert debug_urls["debugger_url"] == f"https://browserbase.com/sessions/{session_id}/devtools"


def test_get_replay_url():
    """Verify session replay URL formatting."""
    service = BrowserbaseService(offline=True)
    session_id = "sess_abc12345"
    replay = service.get_replay_url(session_id)
    assert replay == f"https://browserbase.com/sessions/{session_id}"


def test_release_session_offline():
    """Verify session release in offline mode updates internal status."""
    service = BrowserbaseService(offline=True)
    session = service.create_session()
    assert service._active_sessions[session.id]["status"] == "RUNNING"

    service.release_session(session.id)
    assert service._active_sessions[session.id]["status"] == "REQUEST_RELEASE"


# ==============================================================================
# 3. Browserbase Service Live Client Integration / Mocked SDK Tests
# ==============================================================================


def test_create_session_with_live_client():
    """Verify live client interaction with Browserbase Python SDK."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.id = "sess_live_998877"
    mock_resp.connect_url = "wss://connect.browserbase.com?apiKey=real&sessionId=sess_live_998877"
    mock_resp.status = "RUNNING"
    mock_resp.proxy_bytes = 1024
    mock_client.sessions.create.return_value = mock_resp

    service = BrowserbaseService(
        api_key="bb_live_real_key",
        project_id="proj_12345",
        client=mock_client,
    )
    assert service.offline is False

    session = service.create_session(timeout=1200, proxies=True, solve_captchas=True, keep_alive=True)

    assert session.id == "sess_live_998877"
    assert session.connect_url == mock_resp.connect_url
    assert session.proxy_bytes == 1024

    mock_client.sessions.create.assert_called_once()
    call_kwargs = mock_client.sessions.create.call_args[1]
    assert call_kwargs["project_id"] == "proj_12345"
    assert call_kwargs["proxies"] is True
    assert call_kwargs["keep_alive"] is True
    assert call_kwargs["api_timeout"] == 1200
    bs = call_kwargs["browser_settings"]
    solve_captchas = bs["solve_captchas"] if isinstance(bs, dict) else bs.solve_captchas
    block_ads = bs["block_ads"] if isinstance(bs, dict) else bs.block_ads
    assert solve_captchas is True
    assert block_ads is True


def test_get_debug_urls_with_live_client():
    """Verify debug URLs extraction using live SDK client."""
    mock_client = MagicMock()
    mock_debug = MagicMock()
    mock_debug.debugger_fullscreen_url = "https://browserbase.com/sessions/sess_99/debug"
    mock_debug.debugger_url = "https://browserbase.com/sessions/sess_99/devtools"
    mock_debug.ws_url = "wss://connect.browserbase.com/debug?sessionId=sess_99"
    mock_client.sessions.debug.return_value = mock_debug

    service = BrowserbaseService(client=mock_client)
    urls = service.get_debug_urls("sess_99")

    mock_client.sessions.debug.assert_called_once_with("sess_99")
    assert urls["debugger_fullscreen_url"] == "https://browserbase.com/sessions/sess_99/debug"


def test_release_session_with_live_client():
    """Verify release_session issues REQUEST_RELEASE update to Browserbase SDK."""
    mock_client = MagicMock()
    service = BrowserbaseService(client=mock_client)

    service.release_session("sess_live_456")

    mock_client.sessions.update.assert_called_once_with(
        "sess_live_456",
        status="REQUEST_RELEASE",
    )
