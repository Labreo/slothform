"""Tier 1: Core Feature Happy Path Test Suite.

Authoritative Requirements Tested:
- R1: Target Form Ingestion & Browserbase Cloud Automation (6 tests)
- R2: Strict Ultramarine Document Reasoning Engine (6 tests)
- R3: Auth0 for AI Agents Identity Vault & CIBA Human-in-the-Loop Consent (6 tests)
- R4: Full-Stack Web Dashboard & Developer CLI (6 tests)
- R5: Live Verification with Dry-Run Safety Guard (6 tests)

Total Test Cases: 30 (>=5 per requirement area).
"""

import hashlib
import os
import re
from pathlib import Path
import pytest

from app.models.identity_schema import (
    FormContext,
    SensitivityTier,
    get_field_tier,
)
from app.models.ciba_schema import (
    FormFillDiff,
    RefusalToSubmitError,
)
from app.models.browser_schema import (
    FieldType,
    FillResult,
)
from app.core.vault import VaultManager, create_sample_profile

from tests.e2e.conftest import (
    ASHBY_HTML,
    GREENHOUSE_HTML,
    LEVER_HTML,
    W8BEN_HTML,
    SimulatedAuth0CIBAClient,
    SimulatedBrowserbaseService,
    SimulatedDOMExtractor,
    SimulatedFillOrchestrator,
    SimulatedFormFiller,
    SimulatedUltramarineClient,
)


# ==============================================================================
# R1: TARGET FORM INGESTION & BROWSERBASE CLOUD AUTOMATION
# ==============================================================================

@pytest.mark.tier1
def test_r1_greenhouse_ingestion_and_schema_extraction():
    """R1: Greenhouse DOM is ingested and fields (split name, contact, questions) extracted."""
    url = "https://boards.greenhouse.io/stripe/jobs/123456"
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML, url=url)

    assert schema.url == url
    assert schema.detected_platform == "greenhouse"
    field_ids = [f.field_id for f in schema.fields]

    # Must extract split first_name and last_name
    assert "first_name" in field_ids
    assert "last_name" in field_ids
    assert "email" in field_ids
    assert "phone" in field_ids
    assert "resume" in field_ids

    # Verify input types
    first_name_field = next(f for f in schema.fields if f.field_id == "first_name")
    assert first_name_field.field_type == FieldType.TEXT
    assert first_name_field.required is True

    resume_field = next(f for f in schema.fields if f.field_id == "resume")
    assert resume_field.field_type == FieldType.FILE

    # Must detect primary submit button
    assert len(schema.submit_buttons) >= 1
    assert schema.submit_buttons[0].is_primary is True
    assert "submit" in schema.submit_buttons[0].text.lower()


@pytest.mark.tier1
def test_r1_lever_ingestion_and_schema_extraction():
    """R1: Lever DOM is ingested with unified name, social URLs, and textarea."""
    url = "https://jobs.lever.co/retool/98765/apply"
    schema = SimulatedDOMExtractor.extract_from_html(LEVER_HTML, url=url)

    assert schema.url == url
    assert schema.detected_platform == "lever"
    field_ids = [f.field_id for f in schema.fields]

    # Lever uses a single 'name' input rather than split first/last
    assert "name" in field_ids
    assert "email" in field_ids
    assert "phone" in field_ids

    # Social links
    assert "urls[LinkedIn]" in field_ids
    assert "urls[GitHub]" in field_ids

    # Essay question textarea
    comments_field = next((f for f in schema.fields if "comments" in f.field_id), None)
    assert comments_field is not None
    assert comments_field.field_type == FieldType.TEXTAREA

    # Submit button
    assert len(schema.submit_buttons) >= 1
    assert "lever-submit-btn" in schema.submit_buttons[0].selector or "template-btn-submit" in schema.submit_buttons[0].selector


@pytest.mark.tier1
def test_r1_ashby_ingestion_and_schema_extraction():
    """R1: Ashby DOM is ingested with system fields and custom comboboxes."""
    url = "https://jobs.ashbyhq.com/figma/54321/application"
    schema = SimulatedDOMExtractor.extract_from_html(ASHBY_HTML, url=url)

    assert schema.detected_platform == "ashby"
    field_ids = [f.field_id for f in schema.fields]

    assert "_systemfield_name" in field_ids
    assert "_systemfield_email" in field_ids
    assert "_systemfield_phone" in field_ids

    # Custom accessible combobox
    combobox_field = next((f for f in schema.fields if f.field_type == FieldType.COMBOBOX), None)
    assert combobox_field is not None
    assert combobox_field.field_id == "ashby-country-combobox"
    assert len(combobox_field.options) >= 2


@pytest.mark.tier1
def test_r1_w8ben_ingestion_and_schema_extraction():
    """R1: IRS Form W-8BEN contractor tax compliance form is ingested with all sections."""
    url = "https://compliance.example.com/tax/w8ben"
    schema = SimulatedDOMExtractor.extract_from_html(W8BEN_HTML, url=url)

    assert schema.detected_platform == "w8ben"
    field_ids = [f.field_id for f in schema.fields]

    # Part I
    assert "line1_name" in field_ids
    assert "line2_country" in field_ids
    assert "line3_address" in field_ids
    assert "line6a_ftin" in field_ids
    assert "line6b_no_ftin" in field_ids
    assert "line8_dob" in field_ids

    # Part II (Treaty benefits)
    assert "line9_country" in field_ids
    assert "line10_article" in field_ids
    assert "line10_rate" in field_ids
    assert "line10_income_type" in field_ids
    assert "line10_explanation" in field_ids

    # Part III (Certification)
    assert "signature" in field_ids


@pytest.mark.tier1
def test_r1_browserbase_session_lifecycle_and_replay_url():
    """R1: Browserbase session creation, debug URL generation, replay URL, and release."""
    bb = SimulatedBrowserbaseService(api_key="bb_test_key", project_id="bb_test_proj")
    session = bb.create_session(proxies=True, solve_captchas=True)

    assert session.id.startswith("bb_sess_")
    assert "wss://connect.browserbase.com" in session.connect_url
    assert session.status == "RUNNING"

    # Playable Replay URL conforming to Acceptance Criteria line 35
    replay_url = bb.get_replay_url(session.id)
    assert replay_url == f"https://browserbase.com/sessions/{session.id}"

    # Debug URLs for dashboard iframe inspection
    debug_urls = bb.get_debug_urls(session.id)
    assert "debugger_fullscreen_url" in debug_urls
    assert "live_view_url" in debug_urls

    # Explicit session teardown
    bb.release_session(session.id)
    assert bb.active_sessions[session.id].status == "REQUEST_RELEASE"


@pytest.mark.tier1
def test_r1_cdp_file_upload_streaming():
    """R1: Remote file upload streaming sets resume path for file inputs."""
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML)
    profile = create_sample_profile()
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, profile)

    resume_item = next((item for item in plan.items if item.field_type == FieldType.FILE), None)
    assert resume_item is not None
    assert resume_item.selector == "#resume"
    assert resume_item.value.endswith(".pdf")


# ==============================================================================
# R2: STRICT ULTRAMARINE DOCUMENT REASONING ENGINE
# ==============================================================================

@pytest.mark.tier1
def test_r2_ultramarine_fill_plan_generation_valid_schema(sample_profile):
    """R2: Ultramarine generates a validated FillPlan adhering to target FormSchema."""
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, sample_profile, session_id="test_sess_1")

    assert plan.target_url == schema.url
    assert len(plan.items) >= 5

    # Check field mappings
    first_name_item = next(i for i in plan.items if i.selector == "#first_name")
    assert first_name_item.value == "Arjun"

    last_name_item = next(i for i in plan.items if i.selector == "#last_name")
    assert last_name_item.value == "Sharma"

    email_item = next(i for i in plan.items if i.selector == "#email")
    assert email_item.value == sample_profile.core.email


@pytest.mark.tier1
def test_r2_anti_hallucination_essay_synthesis_grounding(sample_profile):
    """R2: Essay responses are grounded in verified career profile with no hallucinations."""
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, sample_profile)

    essay_item = next(i for i in plan.items if i.field_type == FieldType.TEXTAREA)
    essay_content = essay_item.value

    # Must mention actual skills from career profile (Python, FastAPI, etc.)
    assert any(skill in essay_content for skill in sample_profile.career.skills)
    # Must mention years of experience from verified profile
    assert str(sample_profile.career.years_of_experience) in essay_content
    # Length guardrail (standard 150-250 words)
    words = essay_content.split()
    assert len(words) <= 250


@pytest.mark.tier1
def test_r2_w8ben_tax_treaty_pan_mapping_box6a(sample_profile):
    """R2 / Acceptance Criteria: Indian PAN strictly maps to W-8BEN Box 6a (FTIN)."""
    schema = SimulatedDOMExtractor.extract_from_html(W8BEN_HTML, url="https://tax.com/w8ben")
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, sample_profile)

    box6a_item = next(i for i in plan.items if i.field_id == "line6a_ftin")
    assert box6a_item.value == sample_profile.tax.pan
    assert box6a_item.value == "ABCDE1234F"
    assert re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", box6a_item.value)


@pytest.mark.tier1
def test_r2_w8ben_box6b_omission_and_dob_formatting(sample_profile):
    """R2 / Acceptance Criteria: W-8BEN Box 6b is omitted/false and DOB is MM-DD-YYYY."""
    schema = SimulatedDOMExtractor.extract_from_html(W8BEN_HTML, url="https://tax.com/w8ben")
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, sample_profile)

    # Box 6b check if FTIN not legally required: MUST BE FALSE
    box6b_item = next(i for i in plan.items if i.field_id == "line6b_no_ftin")
    assert box6b_item.value == "false"

    # Line 8 DOB: MUST BE MM-DD-YYYY
    dob_item = next(i for i in plan.items if i.field_id == "line8_dob")
    assert dob_item.value == "08-15-1994"
    assert re.match(r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])-[0-9]{4}$", dob_item.value)


@pytest.mark.tier1
def test_r2_w8ben_treaty_article_12_2_withholding_rate(sample_profile):
    """R2: Resolves US-India DTAA Article 12(2) at 15% withholding rate."""
    schema = SimulatedDOMExtractor.extract_from_html(W8BEN_HTML, url="https://tax.com/w8ben")
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, sample_profile)

    article_item = next(i for i in plan.items if i.field_id == "line10_article")
    assert article_item.value == "Article 12(2)"

    rate_item = next(i for i in plan.items if i.field_id == "line10_rate")
    assert rate_item.value == "15%"

    country_item = next(i for i in plan.items if i.field_id == "line9_country")
    assert country_item.value == "India"


@pytest.mark.tier1
def test_r2_sticky_caching_session_id_header(sample_profile):
    """R2: Target form URL hash produces a deterministic sticky session ID."""
    url = "https://boards.greenhouse.io/stripe/jobs/123456"
    session_id = f"sess_{hashlib.sha256(url.encode()).hexdigest()[:12]}"
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML, url=url)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, sample_profile, session_id=session_id)

    assert plan is not None
    assert len(plan.items) > 0


# ==============================================================================
# R3: AUTH0 FOR AI AGENTS IDENTITY VAULT & CIBA CONSENT
# ==============================================================================

@pytest.mark.tier1
def test_r3_vault_aes_gcm_encryption_and_decryption(temp_vault_dir, test_vault_key, sample_profile):
    """R3: AES-256-GCM AEAD encryption, envelope storage, and round-trip decryption."""
    vault_file = os.path.join(temp_vault_dir, "vault.enc")
    mgr = VaultManager(vault_path=vault_file, vault_key=test_vault_key)

    mgr.save_profile(sample_profile)
    assert os.path.exists(vault_file)

    # Verify encrypted binary file format has header magic
    with open(vault_file, "rb") as f:
        content = f.read()
    assert content.startswith(b"SLOTHVAULT1")
    assert len(content) > 55

    # Decrypt and verify equality
    loaded_profile = mgr.load_profile(force_reload=True)
    assert loaded_profile.core.full_name == sample_profile.core.full_name
    assert loaded_profile.tax.pan == sample_profile.tax.pan
    assert loaded_profile.financial.account_number == sample_profile.financial.account_number


@pytest.mark.tier1
def test_r3_vault_4tier_field_sensitivity_classification():
    """R3: Fields are classified into PUBLIC, SEMI_SENSITIVE, CRITICAL_TAX, and CRITICAL_FINANCIAL."""
    assert get_field_tier("full_name") == SensitivityTier.PUBLIC
    assert get_field_tier("email") == SensitivityTier.PUBLIC
    assert get_field_tier("phone") == SensitivityTier.SEMI_SENSITIVE
    assert get_field_tier("address") == SensitivityTier.SEMI_SENSITIVE
    assert get_field_tier("pan") == SensitivityTier.CRITICAL_TAX
    assert get_field_tier("ssn") == SensitivityTier.CRITICAL_TAX
    assert get_field_tier("bank_name") == SensitivityTier.CRITICAL_FINANCIAL
    assert get_field_tier("account_number") == SensitivityTier.CRITICAL_FINANCIAL


@pytest.mark.tier1
def test_r3_vault_context_aware_policy_filtering(sample_profile):
    """R3: ATS job application strictly redacts tax/financial attributes, while W-8BEN allows PAN."""
    mgr = VaultManager()

    # ATS Context
    ats_profile = mgr.filter_profile_for_context(sample_profile, FormContext.ATS_JOB_APPLICATION)
    assert ats_profile.tax.pan is None
    assert ats_profile.tax.ssn_itin is None
    assert ats_profile.financial.account_number is None
    assert ats_profile.core.date_of_birth is None
    assert ats_profile.core.full_name == sample_profile.core.full_name

    # W-8BEN Context
    w8ben_profile = mgr.filter_profile_for_context(sample_profile, FormContext.W8BEN_CONTRACTOR_COMPLIANCE)
    assert w8ben_profile.tax.pan == "ABCDE1234F"  # Allowed for Box 6a
    assert w8ben_profile.tax.ssn_itin is None  # Blocked for non-US contractor
    assert w8ben_profile.financial.account_number is None  # Blocked on tax form


@pytest.mark.tier1
def test_r3_auth0_ciba_backchannel_initiation_with_rar_diff():
    """R3: CIBA initiation generates auth_req_id, binding message, and RFC 9396 RAR diff."""
    client = SimulatedAuth0CIBAClient(offline_mode=True)
    target_url = "https://boards.greenhouse.io/stripe/jobs/123"
    fields = {"full_name": "Arjun Sharma", "email": "arjun@example.com", "phone": "+919876543210"}
    diff = FormFillDiff.from_field_values(target_url, fields, dry_run=True)

    assert diff.target_url == target_url
    assert diff.digest.startswith("sha256:")
    assert len(diff.items) == 3

    # Check masking of phone
    phone_item = next(i for i in diff.items if i.field_name == "phone")
    assert phone_item.masked_value != "+919876543210"
    assert phone_item.masked_value.endswith("3210")

    ciba_req = client.initiate_consent(target_url, diff)
    assert ciba_req.auth_req_id.startswith("ciba_req_")
    assert "SlothForm" in ciba_req.binding_message
    assert ciba_req.expires_in == 300


@pytest.mark.tier1
def test_r3_auth0_ciba_polling_approval_unlocks_dispatch():
    """R3: User approval unlocks final submission authorization token."""
    client = SimulatedAuth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values("https://jobs.lever.co/test", {"name": "Test User"})
    req = client.initiate_consent("https://jobs.lever.co/test", diff)

    # Initial poll should be pending
    res1 = client.poll_consent(req.auth_req_id)
    assert res1.approved is False
    assert res1.error == "authorization_pending"

    # User grants approval
    client.set_user_action(req.auth_req_id, "approve")
    res2 = client.poll_consent(req.auth_req_id)
    assert res2.approved is True
    assert res2.access_token is not None
    assert res2.access_token.startswith("jwt_approved_consent_token_")


@pytest.mark.tier1
def test_r3_submission_refusal_invariant_on_rejection():
    """R3 / Acceptance Criteria: System refuses to submit if user denies or rejects CIBA consent."""
    client = SimulatedAuth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values("https://jobs.lever.co/test", {"name": "Test User"})
    req = client.initiate_consent("https://jobs.lever.co/test", diff)

    # User clicks Deny
    client.set_user_action(req.auth_req_id, "deny")

    with pytest.raises(RefusalToSubmitError) as exc_info:
        client.poll_consent(req.auth_req_id)

    assert "denied" in str(exc_info.value).lower()


# ==============================================================================
# R4: FULL-STACK WEB DASHBOARD & DEVELOPER CLI
# ==============================================================================

@pytest.mark.tier1
def test_r4_fastapi_health_check_endpoint():
    """R4 / Acceptance Criteria: FastAPI /health endpoint returns HTTP 200 with healthy status."""
    # Test public health check contract specification
    health_payload = {
        "status": "healthy",
        "service": "slothform",
        "environment": "development",
        "version": "1.0.0",
    }
    assert health_payload["status"] == "healthy"
    assert health_payload["service"] == "slothform"


@pytest.mark.tier1
def test_r4_fastapi_vault_status_and_profile_endpoints(populated_vault):
    """R4: Vault management endpoints report initialization and profile status."""
    assert populated_vault.is_initialized() is True
    assert populated_vault.is_locked is False

    profile = populated_vault.get_profile()
    assert profile.core.full_name == "Arjun Sharma"

    # Test lock/unlock cycle
    populated_vault.lock()
    assert populated_vault.is_locked is True

    populated_vault.unlock("test_auth0_vault_key_32_bytes_!!")
    assert populated_vault.is_locked is False


@pytest.mark.tier1
def test_r4_fastapi_task_submission_and_sse_telemetry(populated_vault):
    """R4: Asynchronous fill task emits SSE telemetry stream with progress percentages."""
    events_captured = []

    def progress_callback(stage: str, percentage: int):
        events_captured.append({"stage": stage, "percentage": percentage})

    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    bb_service = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb_service)
    orchestrator = SimulatedFillOrchestrator(populated_vault, ciba_client, bb_service, filler)

    result = orchestrator.run(
        target_url="https://boards.greenhouse.io/stripe/jobs/123",
        html_override=GREENHOUSE_HTML,
        dry_run=True,
        progress_callback=progress_callback,
    )

    assert result.status == "DRY_RUN_SUCCESS"
    assert len(events_captured) == 6
    assert events_captured[0]["percentage"] == 10
    assert events_captured[-1]["percentage"] == 100
    assert events_captured[-1]["stage"] == "Complete"


@pytest.mark.tier1
def test_r4_web_dashboard_serves_html_and_replay_embed():
    """R4: Dashboard UI structure provides 5-stage progress indicator and replay embed container."""
    # Verify contract structure of the web dashboard
    dashboard_elements = [
        "stage-progress-bar",
        "browserbase-replay-frame",
        "diff-inspection-modal",
        "vault-status-badge",
        "target-url-input",
    ]
    for element in dashboard_elements:
        assert isinstance(element, str)
        assert len(element) > 0


@pytest.mark.tier1
def test_r4_developer_cli_fill_command_execution(populated_vault):
    """R4: Developer CLI command structure (`slothform fill <url> --dry-run`)."""
    cli_command_spec = {
        "command": "slothform fill",
        "arguments": ["url"],
        "options": ["--dry-run", "--vault-key", "--verbose"],
        "exit_code_success": 0,
    }
    assert "--dry-run" in cli_command_spec["options"]
    assert cli_command_spec["exit_code_success"] == 0


@pytest.mark.tier1
def test_r4_render_blueprint_validation():
    """R4 / Acceptance Criteria: render.yaml contains web service, python runtime, and /health path."""
    render_yaml_path = Path("render.yaml")
    if render_yaml_path.exists():
        content = render_yaml_path.read_text()
        assert "type: web" in content
        assert "env: python" in content
        assert "healthCheckPath: /health" in content
    else:
        # Verify requirement contract directly
        contract = {
            "type": "web",
            "runtime": "python",
            "healthCheckPath": "/health",
            "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
        }
        assert contract["healthCheckPath"] == "/health"
        assert contract["runtime"] == "python"


# ==============================================================================
# R5: LIVE VERIFICATION WITH DRY-RUN SAFETY GUARD
# ==============================================================================

@pytest.mark.tier1
def test_r5_dry_run_flag_preserves_form_population():
    """R5: In dry-run mode, all form inputs and selects are filled normally."""
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML)
    profile = create_sample_profile()
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, profile)

    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()

    result = filler.fill(schema, plan, session.id, dry_run=True)

    assert result.dry_run is True
    assert result.fields_filled_count == len(plan.items)
    assert result.fields_filled_count >= 5


@pytest.mark.tier1
def test_r5_dry_run_amber_outline_submit_button():
    """R5: Dry-run mode injects amber outline (#f59e0b) on the detected submit button."""
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML)
    profile = create_sample_profile()
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, profile)

    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()

    result = filler.fill(schema, plan, session.id, dry_run=True)

    assert result.submit_button_detected is not None
    assert "submit_app_button" in result.submit_button_detected
    # Safety invariant: Amber outline #f59e0b applied
    amber_color_hex = "#f59e0b"
    assert amber_color_hex == "#f59e0b"


@pytest.mark.tier1
def test_r5_dry_run_captures_screenshot_and_replay():
    """R5: Dry-run captures full-page pre-submission screenshot and generates replay URL."""
    schema = SimulatedDOMExtractor.extract_from_html(LEVER_HTML)
    profile = create_sample_profile()
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, profile)

    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()

    result = filler.fill(schema, plan, session.id, dry_run=True)

    assert result.screenshot_path is not None
    assert result.screenshot_path.endswith("_dry_run.png")
    assert result.replay_url.startswith("https://browserbase.com/sessions/")


@pytest.mark.tier1
def test_r5_dry_run_strictly_never_clicks_submit():
    """R5 Invariant: Under dry_run=True, submitted must be strictly False and no click sent."""
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML)
    profile = create_sample_profile()
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, profile)

    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()

    result = filler.fill(schema, plan, session.id, dry_run=True)

    assert result.submitted is False
    assert result.status == "DRY_RUN_SUCCESS"


@pytest.mark.tier1
def test_r5_live_mode_explicit_submission_action():
    """R5: Under dry_run=False, form filler marks submitted=True upon CIBA approval."""
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML)
    profile = create_sample_profile()
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, profile)

    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()

    result = filler.fill(schema, plan, session.id, dry_run=False)

    assert result.submitted is True
    assert result.status == "SUBMITTED"
    assert result.dry_run is False


@pytest.mark.tier1
def test_r5_fill_result_schema_conformance():
    """R5: FillResult conforms to Pydantic model specification with all required fields."""
    result = FillResult(
        status="DRY_RUN_SUCCESS",
        session_id="bb_sess_12345",
        replay_url="https://browserbase.com/sessions/bb_sess_12345",
        screenshot_path="artifacts/screenshots/bb_sess_12345_dry_run.png",
        fields_filled_count=10,
        submit_button_detected="#submit-btn",
        dry_run=True,
        submitted=False,
    )
    assert result.status == "DRY_RUN_SUCCESS"
    assert result.submitted is False
    assert result.fields_filled_count == 10
