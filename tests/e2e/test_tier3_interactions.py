"""Tier 3: Pairwise Cross-Feature Interaction Test Suite.

Authoritative Requirements & Interactions Tested:
- Interaction 1: W-8BEN Tax Form Ingestion (R1) + Tax Treaty Resolution (R2) + Auth0 CIBA Consent (R3) + Dry-Run Safety (R5)
- Interaction 2: Greenhouse Job Application (R1) + Anti-Hallucination Essay (R2) + CIBA Rejection Abort (R3) + Safety Guard (R5)
- Interaction 3: Lever Application (R1) + Vault Context Scoping (R3) + Developer CLI (R4) + Dry-Run (R5)
- Interaction 4: Ashby Combobox Extraction (R1) + Ultramarine Reasoning (R2) + SSE Live Telemetry (R4)
- Interaction 5: Hostile DOM Prompt Injection (R1+R2) + Vault Sensitivity Redaction (R3) + Dry-Run Verification (R5)
- Interaction 6: W-8BEN Tax Compliance (R1+R2) + Synthetic Doc Fallback (R1) + CIBA Slow-Down Backoff (R3) + Dry-Run (R5)

Total Test Cases: 6 pairwise interaction tests.
"""

import re
import pytest

from app.models.identity_schema import FormContext
from app.models.ciba_schema import (
    FormFillDiff,
    RefusalToSubmitError,
)
from app.models.browser_schema import (
    FieldType,
)

from tests.e2e.conftest import (
    ASHBY_HTML,
    GREENHOUSE_HTML,
    LEVER_HTML,
    PROMPT_INJECTION_HTML,
    W8BEN_HTML,
    SimulatedAuth0CIBAClient,
    SimulatedBrowserbaseService,
    SimulatedDOMExtractor,
    SimulatedFillOrchestrator,
    SimulatedFormFiller,
    SimulatedUltramarineClient,
)


@pytest.mark.tier3
def test_t3_w8ben_tax_treaty_ciba_consent_dry_run(populated_vault):
    """Interaction 1: W-8BEN Ingestion (R1) + Tax Treaty (R2) + CIBA Consent (R3) + Dry-Run (R5)."""
    target_url = "https://compliance.contractor.io/w8ben"
    schema = SimulatedDOMExtractor.extract_from_html(W8BEN_HTML, url=target_url)
    assert schema.detected_platform == "w8ben"

    # Vault provides W-8BEN scoped profile (PAN allowed, SSN blocked)
    scoped_profile = populated_vault.get_profile(context=FormContext.W8BEN_CONTRACTOR_COMPLIANCE)
    assert scoped_profile.tax.pan == "ABCDE1234F"
    assert scoped_profile.tax.ssn_itin is None

    # Ultramarine generates W-8BEN fill plan
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, scoped_profile)

    # Line 6a: Indian PAN
    box6a = next(i for i in plan.items if i.field_id == "line6a_ftin")
    assert box6a.value == "ABCDE1234F"

    # Line 6b: Unchecked / false
    box6b = next(i for i in plan.items if i.field_id == "line6b_no_ftin")
    assert box6b.value == "false"

    # Line 8: DOB formatted MM-DD-YYYY
    dob = next(i for i in plan.items if i.field_id == "line8_dob")
    assert re.match(r"^\d{2}-\d{2}-\d{4}$", dob.value)

    # Line 10: Article 12(2) at 15%
    art = next(i for i in plan.items if i.field_id == "line10_article")
    assert art.value == "Article 12(2)"
    rate = next(i for i in plan.items if i.field_id == "line10_rate")
    assert rate.value == "15%"

    # CIBA Consent Request
    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values(target_url, {"pan": box6a.value, "date_of_birth": dob.value}, dry_run=True)
    ciba_req = ciba_client.initiate_consent(target_url, diff)

    # User approves
    ciba_client.set_user_action(ciba_req.auth_req_id, "approve")
    consent = ciba_client.poll_consent(ciba_req.auth_req_id)
    assert consent.approved is True

    # Form Filler executes Dry-Run
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()

    result = filler.fill(schema, plan, session.id, dry_run=True)

    # Verification: Fields filled, amber outline applied, strictly NOT submitted
    assert result.status == "DRY_RUN_SUCCESS"
    assert result.submitted is False
    assert result.dry_run is True
    assert result.fields_filled_count >= 10
    assert result.replay_url.startswith("https://browserbase.com/sessions/")


@pytest.mark.tier3
def test_t3_greenhouse_essay_synthesis_ciba_rejection(populated_vault):
    """Interaction 2: Greenhouse (R1) + Essay Synthesis (R2) + CIBA Rejection Abort (R3) + Guard (R5)."""
    target_url = "https://boards.greenhouse.io/stripe/jobs/123"
    schema = SimulatedDOMExtractor.extract_from_html(GREENHOUSE_HTML, url=target_url)

    scoped_profile = populated_vault.get_profile(context=FormContext.ATS_JOB_APPLICATION)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, scoped_profile)

    # Essay synthesized with career grounding
    essay_item = next(i for i in plan.items if i.field_type == FieldType.TEXTAREA)
    assert "distributed systems" in essay_item.value.lower()

    # CIBA Backchannel initiated
    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values(target_url, {"full_name": scoped_profile.core.full_name}, dry_run=True)
    ciba_req = ciba_client.initiate_consent(target_url, diff)

    # User Rejects Consent on mobile device
    ciba_client.set_user_action(ciba_req.auth_req_id, "deny")

    # Invariant: Must raise RefusalToSubmitError and halt immediately
    with pytest.raises(RefusalToSubmitError):
        ciba_client.poll_consent(ciba_req.auth_req_id)


@pytest.mark.tier3
def test_t3_lever_ats_vault_scoping_cli_dry_run(populated_vault):
    """Interaction 3: Lever Ingestion (R1) + Vault Privacy Scoping (R3) + Developer CLI (R4) + Dry-Run (R5)."""
    target_url = "https://jobs.lever.co/retool/98765/apply"
    schema = SimulatedDOMExtractor.extract_from_html(LEVER_HTML, url=target_url)
    assert schema.detected_platform == "lever"

    # Vault privacy engine strips tax and financial details for ATS context
    scoped_profile = populated_vault.get_profile(context=FormContext.ATS_JOB_APPLICATION)
    assert scoped_profile.tax.pan is None
    assert scoped_profile.financial.account_number is None

    # Lever unified name field mapping
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, scoped_profile)
    name_item = next(i for i in plan.items if i.field_id == "name")
    assert name_item.value == scoped_profile.core.full_name

    # CIBA Approval
    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values(target_url, {"full_name": name_item.value}, dry_run=True)
    req = ciba_client.initiate_consent(target_url, diff)
    ciba_client.set_user_action(req.auth_req_id, "approve")
    consent = ciba_client.poll_consent(req.auth_req_id)
    assert consent.approved is True

    # Form Filler Dry-Run
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()
    result = filler.fill(schema, plan, session.id, dry_run=True)

    assert result.status == "DRY_RUN_SUCCESS"
    assert result.submitted is False
    assert result.submit_button_detected is not None


@pytest.mark.tier3
def test_t3_ashby_combobox_ultramarine_sse_telemetry(populated_vault):
    """Interaction 4: Ashby Combobox (R1) + Ultramarine (R2) + FastAPI SSE Live Telemetry (R4)."""
    target_url = "https://jobs.ashbyhq.com/figma/54321/application"
    telemetry_events = []

    def sse_event_listener(stage: str, pct: int):
        telemetry_events.append((stage, pct))

    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    orchestrator = SimulatedFillOrchestrator(populated_vault, ciba_client, bb, filler)

    result = orchestrator.run(
        target_url=target_url,
        html_override=ASHBY_HTML,
        dry_run=True,
        auto_approve_ciba=True,
        progress_callback=sse_event_listener,
    )

    assert result.status == "DRY_RUN_SUCCESS"
    assert len(telemetry_events) == 6
    stages = [event[0] for event in telemetry_events]
    assert "DOM extraction" in stages
    assert "Ultramarine reasoning" in stages
    assert "Auth0 CIBA consent" in stages
    assert "Complete" in stages


@pytest.mark.tier3
def test_t3_prompt_injection_vault_redaction_dry_run(populated_vault):
    """Interaction 5: Hostile DOM Injection (R1+R2) + Vault Redaction (R3) + Dry-Run (R5)."""
    target_url = "https://malicious-form.internal/apply"
    schema = SimulatedDOMExtractor.extract_from_html(PROMPT_INJECTION_HTML, url=target_url)

    # Scoped profile completely scrubs PAN and Bank details
    scoped_profile = populated_vault.get_profile(context=FormContext.ATS_JOB_APPLICATION)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, scoped_profile)

    # Assert no sensitive values leak into any filled item
    for item in plan.items:
        val_str = str(item.value)
        assert "ABCDE1234F" not in val_str
        assert "50100234567890" not in val_str

    # Execute dry-run safely
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()
    result = filler.fill(schema, plan, session.id, dry_run=True)

    assert result.submitted is False
    assert result.status == "DRY_RUN_SUCCESS"


@pytest.mark.tier3
def test_t3_w8ben_synthetic_doc_ciba_slowdown_dry_run(populated_vault):
    """Interaction 6: W-8BEN Tax Form (R1+R2) + Synthetic Doc (R1) + CIBA Slow-Down Backoff (R3) + Dry-Run (R5)."""
    target_url = "https://tax.contractor.io/w8ben"
    schema = SimulatedDOMExtractor.extract_from_html(W8BEN_HTML, url=target_url)
    scoped_profile = populated_vault.get_profile(context=FormContext.W8BEN_CONTRACTOR_COMPLIANCE)

    plan = SimulatedUltramarineClient.generate_fill_plan(schema, scoped_profile)

    # CIBA flow with slow-down handling
    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values(target_url, {"pan": scoped_profile.tax.pan}, dry_run=True)
    req = ciba_client.initiate_consent(target_url, diff)

    # Simulate Auth0 signalling slow_down
    ciba_client.set_user_action(req.auth_req_id, "slow_down")
    res1 = ciba_client.poll_consent(req.auth_req_id)
    assert res1.error == "slow_down"

    # User approves on subsequent poll after backoff
    ciba_client.set_user_action(req.auth_req_id, "approve")
    res2 = ciba_client.poll_consent(req.auth_req_id)
    assert res2.approved is True

    # Form filler executes dry run
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    session = bb.create_session()
    result = filler.fill(schema, plan, session.id, dry_run=True)

    assert result.status == "DRY_RUN_SUCCESS"
    assert result.submitted is False
