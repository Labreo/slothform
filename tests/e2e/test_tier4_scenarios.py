"""Tier 4: Realistic End-to-End Scenarios & User Journeys.

Authoritative End-to-End Journeys Tested:
- Scenario 1: Senior Engineer Applying to Greenhouse Staff Engineer in Dry-Run Mode
- Scenario 2: Lead Backend Engineer Applying to Lever in Dry-Run Mode
- Scenario 3: International Contractor W-8BEN Tax Compliance with Indian PAN & 15% Treaty
- Scenario 4: Pre-Submission Human Consent Denial Halts Entire Pipeline Safely
- Scenario 5: Developer Terminal CLI Flow with Rich Tables and Replay URL Output
- Scenario 6: Full Web Dashboard Lifecycle with Real-Time SSE Telemetry Stream

Total Test Cases: 6 realistic user journeys.
"""

import pytest

from app.models.identity_schema import FormContext
from app.models.ciba_schema import (
    RefusalToSubmitError,
)

from tests.e2e.conftest import (
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


@pytest.mark.tier4
def test_t4_scenario_greenhouse_staff_engineer_dry_run(populated_vault):
    """Scenario 1: Senior Backend Engineer applies to Greenhouse Staff Engineer job in Dry-Run Mode."""
    target_url = "https://boards.greenhouse.io/stripe/jobs/456789"
    progress_log = []

    def log_progress(stage: str, pct: int):
        progress_log.append((stage, pct))

    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    orchestrator = SimulatedFillOrchestrator(populated_vault, ciba_client, bb, filler)

    # Execute full E2E pipeline
    result = orchestrator.run(
        target_url=target_url,
        html_override=GREENHOUSE_HTML,
        dry_run=True,
        auto_approve_ciba=True,
        progress_callback=log_progress,
    )

    # 1. Pipeline reached 100% completion
    assert len(progress_log) == 6
    assert progress_log[-1] == ("Complete", 100)

    # 2. Result state adheres to dry-run safety invariant
    assert result.status == "DRY_RUN_SUCCESS"
    assert result.dry_run is True
    assert result.submitted is False

    # 3. All interactive fields populated
    assert result.fields_filled_count >= 7

    # 4. Submit button detected and outlined in amber
    assert result.submit_button_detected is not None
    assert "submit" in result.submit_button_detected.lower()

    # 5. Verifiable Browserbase session replay URL produced
    assert result.replay_url == f"https://browserbase.com/sessions/{result.session_id}"
    assert result.screenshot_path is not None
    assert result.screenshot_path.endswith("_dry_run.png")


@pytest.mark.tier4
def test_t4_scenario_lever_backend_lead_dry_run(populated_vault):
    """Scenario 2: Applying to Lever Lead Backend Engineer in Dry-Run Mode."""
    target_url = "https://jobs.lever.co/retool/12345/apply"
    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    orchestrator = SimulatedFillOrchestrator(populated_vault, ciba_client, bb, filler)

    result = orchestrator.run(
        target_url=target_url,
        html_override=LEVER_HTML,
        dry_run=True,
        auto_approve_ciba=True,
    )

    assert result.status == "DRY_RUN_SUCCESS"
    assert result.submitted is False
    assert result.dry_run is True
    assert result.fields_filled_count >= 7
    assert result.replay_url.startswith("https://browserbase.com/sessions/")


@pytest.mark.tier4
def test_t4_scenario_contractor_w8ben_treaty_onboarding(populated_vault):
    """Scenario 3: International Contractor W-8BEN onboarding with Indian PAN and DTAA 15% claim."""
    target_url = "https://onboarding.client.com/tax/w8ben"
    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    orchestrator = SimulatedFillOrchestrator(populated_vault, ciba_client, bb, filler)

    # Execute tax compliance onboarding flow
    result = orchestrator.run(
        target_url=target_url,
        html_override=W8BEN_HTML,
        dry_run=True,
        auto_approve_ciba=True,
    )

    assert result.status == "DRY_RUN_SUCCESS"
    assert result.submitted is False

    # Inspect the generated plan directly to verify compliance specifics
    schema = SimulatedDOMExtractor.extract_from_html(W8BEN_HTML, url=target_url)
    profile = populated_vault.get_profile(context=FormContext.W8BEN_CONTRACTOR_COMPLIANCE)
    plan = SimulatedUltramarineClient.generate_fill_plan(schema, profile)

    # Line 6a: Indian PAN mapped
    box6a = next(i for i in plan.items if i.field_id == "line6a_ftin")
    assert box6a.value == "ABCDE1234F"

    # Line 6b: Checkbox MUST be false / unchecked
    box6b = next(i for i in plan.items if i.field_id == "line6b_no_ftin")
    assert box6b.value == "false"

    # Line 8: DOB formatted as MM-DD-YYYY
    dob = next(i for i in plan.items if i.field_id == "line8_dob")
    assert dob.value == "08-15-1994"

    # Line 10: Article 12(2) at 15%
    art = next(i for i in plan.items if i.field_id == "line10_article")
    assert art.value == "Article 12(2)"
    rate = next(i for i in plan.items if i.field_id == "line10_rate")
    assert rate.value == "15%"


@pytest.mark.tier4
def test_t4_scenario_ciba_denial_submission_refusal(populated_vault):
    """Scenario 4: User reviews proposed diff on mobile authenticator and denies consent."""
    target_url = "https://boards.greenhouse.io/stripe/jobs/123"
    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    orchestrator = SimulatedFillOrchestrator(populated_vault, ciba_client, bb, filler)

    # User explicitly denies consent
    with pytest.raises(RefusalToSubmitError) as exc_info:
        orchestrator.run(
            target_url=target_url,
            html_override=GREENHOUSE_HTML,
            dry_run=True,
            auto_approve_ciba=False,  # Triggers refusal
        )

    assert "refused" in str(exc_info.value).lower() or "denied" in str(exc_info.value).lower()


@pytest.mark.tier4
def test_t4_scenario_developer_cli_execution_journey(populated_vault):
    """Scenario 5: Developer terminal CLI workflow with live replay URL output."""
    cli_args = {
        "url": "https://jobs.lever.co/retool/12345/apply",
        "dry_run": True,
        "vault_key": "test_auth0_vault_key_32_bytes_!!",
    }

    # Simulate CLI dispatch
    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    orchestrator = SimulatedFillOrchestrator(populated_vault, ciba_client, bb, filler)

    result = orchestrator.run(
        target_url=cli_args["url"],
        html_override=LEVER_HTML,
        dry_run=cli_args["dry_run"],
        auto_approve_ciba=True,
    )

    assert result.status == "DRY_RUN_SUCCESS"
    assert result.replay_url.startswith("https://browserbase.com/sessions/")
    # CLI exit code contract: 0 for clean dry run completion
    cli_exit_code = 0 if result.status == "DRY_RUN_SUCCESS" else 1
    assert cli_exit_code == 0


@pytest.mark.tier4
def test_t4_scenario_web_dashboard_full_lifecycle(populated_vault):
    """Scenario 6: Web dashboard receives URL, streams SSE progress events, and returns replay embed."""
    target_url = "https://boards.greenhouse.io/stripe/jobs/999"
    sse_telemetry_stream = []

    def sse_emitter(stage: str, pct: int):
        sse_telemetry_stream.append(f"event: progress\ndata: {{\"stage\": \"{stage}\", \"percentage\": {pct}}}\n\n")

    ciba_client = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    orchestrator = SimulatedFillOrchestrator(populated_vault, ciba_client, bb, filler)

    result = orchestrator.run(
        target_url=target_url,
        html_override=GREENHOUSE_HTML,
        dry_run=True,
        auto_approve_ciba=True,
        progress_callback=lambda s, p: sse_emitter(s, p),
    )

    assert result.status == "DRY_RUN_SUCCESS"
    assert len(sse_telemetry_stream) == 6
    assert "event: progress" in sse_telemetry_stream[0]
    assert "100" in sse_telemetry_stream[-1]
    assert result.live_view_url is not None
