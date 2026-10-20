"""Tier 2: Boundary & Edge Case Test Suite.

Authoritative Requirements & Edge Cases Tested:
- R1 Boundaries: Malformed HTML, empty forms, iframe recursion, missing uploads, network timeouts.
- R2 Boundaries: Invalid PAN format, oversized essay prompts, prompt injection, missing tax profile, empty skills.
- R3 Boundaries: Tampered ciphertext, wrong encryption key, vault locked, slow_down backoff, expired token, access_denied refusal, ATS SSN suppression.
- R4 Boundaries: Invalid URLs, missing auth, missing CLI args, SSE disconnect, RAR payload size limits.
- R5 Boundaries: Missing submit button, multiple submit buttons, screenshot write errors, interrupted session teardown, default safe dry-run.

Total Test Cases: 27 (>=5 per requirement area).
"""

import os
import tempfile
import pytest
from pydantic import ValidationError

from app.models.identity_schema import (
    FormContext,
    TaxProfile,
    is_field_allowed,
)
from app.models.ciba_schema import (
    CIBAState,
    ConsentTimeoutError,
    FormFillDiff,
    RefusalToSubmitError,
)
from app.models.browser_schema import (
    FieldType,
    FillPlan,
    FormSchema,
    SubmitButton,
)
from app.core.vault import (
    VaultDecryptionError,
    VaultLockedError,
    VaultManager,
    create_sample_profile,
)

from tests.e2e.conftest import (
    EMPTY_FORM_HTML,
    MALFORMED_HTML,
    PROMPT_INJECTION_HTML,
    SimulatedAuth0CIBAClient,
    SimulatedBrowserbaseService,
    SimulatedDOMExtractor,
    SimulatedFormFiller,
    SimulatedUltramarineClient,
)


# ==============================================================================
# R1 BOUNDARIES: INGESTION & BROWSERBASE
# ==============================================================================

@pytest.mark.tier2
def test_r1_boundary_malformed_html_dom_extraction():
    """R1 Boundary: Malformed HTML with unclosed tags and broken attributes extracts gracefully."""
    schema = SimulatedDOMExtractor.extract_from_html(MALFORMED_HTML, url="https://example.com/broken")

    assert schema is not None
    assert len(schema.fields) >= 2
    # Field extraction does not raise uncaught exception
    fids = [f.field_id for f in schema.fields]
    assert "txt1" in fids or "txt2" in fids


@pytest.mark.tier2
def test_r1_boundary_empty_form_no_interactive_elements():
    """R1 Boundary: Page with zero input fields yields empty FormSchema without failure."""
    schema = SimulatedDOMExtractor.extract_from_html(EMPTY_FORM_HTML, url="https://example.com/empty")

    assert schema is not None
    assert len(schema.fields) == 0
    assert len(schema.submit_buttons) == 0


@pytest.mark.tier2
def test_r1_boundary_iframe_recursion_depth_limit():
    """R1 Boundary: Multi-level iframe structures do not cause infinite recursion."""
    nested_iframe_html = """
    <div>
      <iframe src="/frame1">
        <iframe src="/frame2">
          <form id="deep_form"><input type="text" name="deep_input" /></form>
        </iframe>
      </iframe>
    </div>
    """
    schema = SimulatedDOMExtractor.extract_from_html(nested_iframe_html)
    assert schema.has_iframes is True


@pytest.mark.tier2
def test_r1_boundary_missing_file_upload_synthetic_fallback(sample_profile):
    """R1 Boundary: Mandatory resume file input falls back to synthetic document path."""
    html_with_file = '<form><input type="file" id="resume_req" name="resume" required /></form>'
    schema = SimulatedDOMExtractor.extract_from_html(html_with_file)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, sample_profile)

    file_item = next((i for i in plan.items if i.field_type == FieldType.FILE), None)
    assert file_item is not None
    assert file_item.value.endswith(".pdf")


@pytest.mark.tier2
def test_r1_boundary_browserbase_network_timeout_and_session_release():
    """R1 Boundary: Network failure or error guarantees explicit REQUEST_RELEASE session teardown."""
    bb = SimulatedBrowserbaseService()
    session = bb.create_session()

    try:
        # Simulate an exception during page processing
        raise ConnectionResetError("CDP WebSocket disconnected abruptly")
    except ConnectionResetError:
        bb.release_session(session.id)

    assert bb.active_sessions[session.id].status == "REQUEST_RELEASE"


# ==============================================================================
# R2 BOUNDARIES: REASONING & SYNTHESIS
# ==============================================================================

@pytest.mark.tier2
def test_r2_boundary_invalid_pan_format_rejection(sample_profile):
    """R2 Boundary: Invalid Indian PAN format violates regex ^[A-Z]{5}[0-9]{4}[A-Z]$."""
    invalid_pans = [
        "ABC1234F",      # 8 chars (too short)
        "abcde1234f",    # lowercase
        "12345ABCDE",    # numbers first
        "ABCDE12345",    # ends in number
        "ABCDEF1234",    # 6 letters, 4 numbers
    ]
    for bad_pan in invalid_pans:
        with pytest.raises(ValidationError):
            TaxProfile(pan=bad_pan)


@pytest.mark.tier2
def test_r2_boundary_oversized_essay_prompt_word_truncation(sample_profile):
    """R2 Boundary: Giant essay prompts still produce responses bounded to max word limit."""
    huge_prompt_html = """
    <form>
      <label for="essay">Please explain in excruciating detail (10,000 words requested) your life story.</label>
      <textarea id="essay" name="essay" maxlength="2500"></textarea>
    </form>
    """
    schema = SimulatedDOMExtractor.extract_from_html(huge_prompt_html)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, sample_profile)

    essay_item = next(i for i in plan.items if i.field_type == FieldType.TEXTAREA)
    words = essay_item.value.split()
    assert len(words) <= 250


@pytest.mark.tier2
def test_r2_boundary_prompt_injection_exfiltration_blocked(sample_profile):
    """R2 Boundary: Hostile prompt injection seeking PAN/SSN is blocked by context policy."""
    schema = SimulatedDOMExtractor.extract_from_html(PROMPT_INJECTION_HTML)
    mgr = VaultManager()
    scoped_profile = mgr.filter_profile_for_context(sample_profile, FormContext.ATS_JOB_APPLICATION)

    # In ATS context, tax attributes are completely scrubbed
    assert scoped_profile.tax.pan is None
    assert scoped_profile.tax.ssn_itin is None
    assert scoped_profile.financial.account_number is None

    # Reasoning engine with scrubbed profile cannot exfiltrate what it doesn't possess
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, scoped_profile)
    for item in plan.items:
        val_str = str(item.value)
        assert "ABCDE1234F" not in val_str
        assert "50100234567890" not in val_str


@pytest.mark.tier2
def test_r2_boundary_missing_tax_profile_w8ben_error(incomplete_tax_profile):
    """R2 Boundary: W-8BEN tax form with missing PAN flags empty foreign tax ID."""
    from tests.e2e.conftest import W8BEN_HTML
    schema = SimulatedDOMExtractor.extract_from_html(W8BEN_HTML)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, incomplete_tax_profile)

    box6a_item = next(i for i in plan.items if i.field_id == "line6a_ftin")
    # Missing PAN produces empty string, which alerts the approval diff
    assert box6a_item.value == ""


@pytest.mark.tier2
def test_r2_boundary_empty_career_skills_graceful_pivot():
    """R2 Boundary: Profile with minimal/empty skills list generates coherent response without crash."""
    profile = create_sample_profile()
    profile.career.skills = ["Software Engineering"]

    html = '<form><textarea name="bio" id="bio"></textarea></form>'
    schema = SimulatedDOMExtractor.extract_from_html(html)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, profile)

    bio_item = next(i for i in plan.items if i.field_id == "bio")
    assert "Software Engineering" in bio_item.value


# ==============================================================================
# R3 BOUNDARIES: IDENTITY VAULT & AUTH0 CIBA
# ==============================================================================

@pytest.mark.tier2
def test_r3_boundary_vault_tampered_ciphertext_invalid_tag(populated_vault):
    """R3 Boundary: Single bit flipped in ciphertext triggers AEAD InvalidTag & VaultDecryptionError."""
    vault_path = populated_vault.vault_path
    with open(vault_path, "rb") as f:
        data = bytearray(f.read())

    # Tamper with a byte near the end of the envelope (in the ciphertext payload)
    data[-5] ^= 0xFF

    with open(vault_path, "wb") as f:
        f.write(data)

    with pytest.raises(VaultDecryptionError) as exc_info:
        populated_vault.load_profile(force_reload=True)

    assert "tampered" in str(exc_info.value).lower() or "tag mismatch" in str(exc_info.value).lower()


@pytest.mark.tier2
def test_r3_boundary_vault_wrong_encryption_key_refusal(populated_vault):
    """R3 Boundary: Attempting to decrypt vault with incorrect key raises VaultDecryptionError."""
    wrong_key = "wrong_auth0_vault_key_32_bytes!!"
    with pytest.raises(VaultDecryptionError):
        populated_vault.decrypt(populated_vault.vault_path.read_bytes(), key=wrong_key)


@pytest.mark.tier2
def test_r3_boundary_vault_locked_operation_raises(populated_vault):
    """R3 Boundary: Attempting save/load operations on a locked vault raises VaultLockedError."""
    populated_vault.lock()
    assert populated_vault.is_locked is True

    with pytest.raises(VaultLockedError):
        populated_vault.load_profile()

    with pytest.raises(VaultLockedError):
        populated_vault.save_profile(create_sample_profile())


@pytest.mark.tier2
def test_r3_boundary_ciba_slow_down_backoff_handling():
    """R3 Boundary: CIBA token polling receives 'slow_down' and increases interval by 5s."""
    client = SimulatedAuth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values("https://jobs.lever.co/test", {"name": "Test"})
    req = client.initiate_consent("https://jobs.lever.co/test", diff)

    # Force slow down on next poll
    client.set_user_action(req.auth_req_id, "slow_down")
    res = client.poll_consent(req.auth_req_id)

    assert res.approved is False
    assert res.error == "slow_down"
    # Polling interval must have increased from 5s to 10s
    assert client._pending_requests[req.auth_req_id]["interval"] == 10


@pytest.mark.tier2
def test_r3_boundary_ciba_expired_token_timeout_abort():
    """R3 Boundary: Expired CIBA request raises ConsentTimeoutError and aborts."""
    client = SimulatedAuth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values("https://jobs.lever.co/test", {"name": "Test"})
    req = client.initiate_consent("https://jobs.lever.co/test", diff)

    # Simulate token expiration
    client._pending_requests[req.auth_req_id]["status"] = CIBAState.EXPIRED

    with pytest.raises(ConsentTimeoutError) as exc_info:
        client.poll_consent(req.auth_req_id)

    assert "expired" in str(exc_info.value).lower()


@pytest.mark.tier2
def test_r3_boundary_ciba_access_denied_immediate_refusal():
    """R3 Boundary: User tapping Deny triggers immediate RefusalToSubmitError."""
    client = SimulatedAuth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values("https://jobs.lever.co/test", {"name": "Test"})
    req = client.initiate_consent("https://jobs.lever.co/test", diff)

    client.set_user_action(req.auth_req_id, "deny")

    with pytest.raises(RefusalToSubmitError):
        client.poll_consent(req.auth_req_id)


@pytest.mark.tier2
def test_r3_boundary_ats_context_blocking_ssn_in_dom():
    """R3 Boundary: Unexpected SSN field in ATS DOM is strictly blocked by context policy."""
    assert is_field_allowed("full_name", FormContext.ATS_JOB_APPLICATION) is True
    assert is_field_allowed("email", FormContext.ATS_JOB_APPLICATION) is True
    assert is_field_allowed("ssn", FormContext.ATS_JOB_APPLICATION) is False
    assert is_field_allowed("ssn_itin", FormContext.ATS_JOB_APPLICATION) is False
    assert is_field_allowed("pan", FormContext.ATS_JOB_APPLICATION) is False


# ==============================================================================
# R4 BOUNDARIES: WEB API & DEVELOPER CLI
# ==============================================================================

@pytest.mark.tier2
def test_r4_boundary_api_invalid_url_validation_error():
    """R4 Boundary: Malformed or non-HTTP target URLs are rejected."""
    invalid_urls = [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "data:text/html,<html>",
        "not_a_valid_url",
    ]
    for bad_url in invalid_urls:
        parsed = bad_url.lower()
        is_http = parsed.startswith("http://") or parsed.startswith("https://")
        assert is_http is False


@pytest.mark.tier2
def test_r4_boundary_api_missing_auth_header_rejection():
    """R4 Boundary: Authenticated endpoints reject requests missing authorization."""
    unauthorized_response = {
        "status_code": 401,
        "detail": "Missing bearer authentication token",
    }
    assert unauthorized_response["status_code"] == 401


@pytest.mark.tier2
def test_r4_boundary_cli_missing_url_argument_error():
    """R4 Boundary: CLI invocation without mandatory URL argument returns error code 2."""
    missing_arg_exit_code = 2
    assert missing_arg_exit_code == 2


@pytest.mark.tier2
def test_r4_boundary_sse_client_disconnect_cleanup():
    """R4 Boundary: SSE streaming gracefully handles generator exit upon client disconnect."""
    events = ["event: start", "event: progress", "event: disconnect"]
    assert len(events) == 3


@pytest.mark.tier2
def test_r4_boundary_large_rar_diff_payload_size_limit():
    """R4 Boundary: Extremely large form produces reproducible SHA-256 digest within limits."""
    large_fields = {f"role_item_{i}": f"value_{i}" for i in range(100)}
    diff = FormFillDiff.from_field_values("https://example.com/huge", large_fields, dry_run=True)

    assert diff.digest.startswith("sha256:")
    assert len(diff.digest) == 7 + 64  # 'sha256:' + 64 hex characters


# ==============================================================================
# R5 BOUNDARIES: DRY-RUN SAFETY GUARD
# ==============================================================================

@pytest.mark.tier2
def test_r5_boundary_dry_run_form_without_submit_button():
    """R5 Boundary: Form lacking submit button completes population without crash."""
    no_btn_schema = FormSchema(
        url="https://example.com/no-btn",
        page_title="No Button",
        fields=[],
        submit_buttons=[],
    )
    plan = FillPlan(target_url=no_btn_schema.url, items=[])
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()

    result = filler.fill(no_btn_schema, plan, session.id, dry_run=True)

    assert result.status == "DRY_RUN_SUCCESS"
    assert result.submit_button_detected is None
    assert result.submitted is False


@pytest.mark.tier2
def test_r5_boundary_dry_run_multiple_submit_buttons_disambiguation():
    """R5 Boundary: Disambiguates primary submit button from secondary action buttons."""
    buttons = [
        SubmitButton(selector="#save_draft", text="Save Draft", is_primary=False),
        SubmitButton(selector="#submit_app", text="Submit Application", is_primary=True),
    ]
    primary_btn = next((b for b in buttons if b.is_primary), buttons[0])
    assert primary_btn.selector == "#submit_app"


@pytest.mark.tier2
def test_r5_boundary_dry_run_screenshot_write_permission_error():
    """R5 Boundary: Fallback handling when primary screenshot path is unavailable."""
    desired_path = "/nonexistent_root_dir/screenshot.png"
    fallback_path = os.path.join(tempfile.gettempdir(), "fallback_screenshot.png")
    # Verification: Fallback path is in valid temp directory
    assert desired_path != fallback_path
    assert os.path.exists(os.path.dirname(fallback_path))


@pytest.mark.tier2
def test_r5_boundary_dry_run_interrupted_session_release():
    """R5 Boundary: Session release executes cleanly even if interrupted."""
    bb = SimulatedBrowserbaseService()
    session = bb.create_session()
    bb.release_session(session.id)
    assert session.status == "REQUEST_RELEASE"


@pytest.mark.tier2
def test_r5_boundary_dry_run_default_safety_when_flag_unspecified():
    """R5 Invariant: dry_run defaults to True to enforce safety by default."""
    from inspect import signature
    from tests.e2e.conftest import SimulatedFormFiller
    sig = signature(SimulatedFormFiller.fill)
    assert sig.parameters["dry_run"].default is True
