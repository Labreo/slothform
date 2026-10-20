"""Integration tests for FillOrchestrator pipeline, CIBA consent gate, and dry-run safety."""

import os
import pytest
from playwright.async_api import async_playwright

from app.core.auth0_client import Auth0CIBAClient
from app.core.ultramarine_client import UltramarineClient
from app.core.vault import VaultManager, create_sample_profile
from app.models.ciba_schema import RefusalToSubmitError
from app.services.browserbase_service import BrowserbaseService
from app.services.dom_extractor import DOMExtractor
from app.services.fill_orchestrator import FillOrchestrator
from app.services.form_filler import FormFiller


@pytest.fixture
async def browser_page():
    """Provides a clean headless Chromium page fixture."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        yield page
        await browser.close()


@pytest.fixture
def temp_vault(tmp_path):
    """Provides an initialized, unlocked VaultManager with a sample profile."""
    vault_file = str(tmp_path / "test_vault.enc")
    mgr = VaultManager(vault_path=vault_file, vault_key="orchestrator_test_secret_key_32b!!")
    profile = create_sample_profile()
    mgr.save_profile(profile)
    return mgr


@pytest.fixture
def offline_ciba_client():
    """Provides an Auth0CIBAClient operating in offline simulation mode."""
    return Auth0CIBAClient(offline_mode=True)


TEST_JOB_HTML = """
<!DOCTYPE html>
<html>
<head><title>Staff Systems Engineer Application</title></head>
<body>
  <h1>Apply for Staff Systems Engineer</h1>
  <form id="job_application" onsubmit="window.__form_submitted = true; return false;">
    <div>
      <label for="first_name">First Name *</label>
      <input type="text" id="first_name" name="first_name" required />
    </div>
    <div>
      <label for="last_name">Last Name *</label>
      <input type="text" id="last_name" name="last_name" required />
    </div>
    <div>
      <label for="email">Email *</label>
      <input type="email" id="email" name="email" required />
    </div>
    <div>
      <label for="phone">Phone *</label>
      <input type="tel" id="phone" name="phone" required />
    </div>
    <div>
      <label for="essay_reason">Why are you interested in this position? *</label>
      <textarea id="essay_reason" name="essay_reason" required></textarea>
    </div>
    <div>
      <label for="resume_file">Attach Resume</label>
      <input type="file" id="resume_file" name="resume" />
    </div>
    <div>
      <button type="submit" id="submit_btn">Submit Application</button>
    </div>
  </form>
</body>
</html>
"""

TEST_W8BEN_HTML = """
<!DOCTYPE html>
<html>
<head><title>Form W-8BEN Tax Compliance</title></head>
<body>
  <h1>Certificate of Foreign Status of Beneficial Owner</h1>
  <form id="w8ben_form">
    <div>
      <label for="line1_name">1. Name of individual who is the beneficial owner</label>
      <input type="text" id="line1_name" name="line1_name" />
    </div>
    <div>
      <label for="line2_citizenship">2. Country of citizenship</label>
      <input type="text" id="line2_citizenship" name="line2_citizenship" />
    </div>
    <div>
      <label for="line3_address">3. Permanent residence address</label>
      <input type="text" id="line3_address" name="line3_address" />
    </div>
    <div>
      <label for="line3_city_state_zip">City or town, state or province, postal code</label>
      <input type="text" id="line3_city_state_zip" name="line3_city_state_zip" />
    </div>
    <div>
      <label for="line6a_ftin">6a. Foreign tax identifying number</label>
      <input type="text" id="line6a_ftin" name="line6a_ftin" />
    </div>
    <div>
      <label for="line6b_no_ftin">6b. Check if FTIN not legally required</label>
      <input type="checkbox" id="line6b_no_ftin" name="line6b_no_ftin" checked />
    </div>
    <div>
      <label for="line8_dob">8. Date of birth (MM-DD-YYYY)</label>
      <input type="text" id="line8_dob" name="line8_dob" />
    </div>
    <div>
      <label for="line9_country">9. Resident of country</label>
      <input type="text" id="line9_country" name="line9_country" />
    </div>
    <div>
      <label for="line10_article">10. Special rates and conditions: Article</label>
      <input type="text" id="line10_article" name="line10_article" />
    </div>
    <div>
      <label for="line10_rate">Rate of withholding claimed (%)</label>
      <input type="text" id="line10_rate" name="line10_rate" />
    </div>
    <div>
      <button type="submit" id="submit_tax">Complete Application</button>
    </div>
  </form>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_orchestrator_e2e_dry_run_with_progress_telemetry(
    browser_page, temp_vault, offline_ciba_client
):
    """Verify full 6-stage pipeline execution with progress callbacks in dry-run mode."""
    await browser_page.set_content(TEST_JOB_HTML)

    orchestrator = FillOrchestrator(
        vault_manager=temp_vault,
        ciba_client=offline_ciba_client,
        browserbase_service=BrowserbaseService(offline=True),
        form_filler=FormFiller(),
        dom_extractor=DOMExtractor(),
        ultramarine_client=UltramarineClient(offline_mode=True),
        auto_approve_ciba=True,
    )

    recorded_stages = []

    def progress_callback(stage: str, percentage: int):
        recorded_stages.append((stage, percentage))

    target_url = "https://boards.greenhouse.io/stripe/jobs/4012"
    result = await orchestrator.run(
        target_url=target_url,
        dry_run=True,
        progress_callback=progress_callback,
        page=browser_page,
    )

    # 1. Verify progress telemetry sequence
    expected_stages = [
        ("SESSION_INIT", 10),
        ("DOM_EXTRACTION", 30),
        ("AI_REASONING", 50),
        ("CIBA_CONSENT", 70),
        ("FORM_FILLING", 90),
        ("COMPLETED", 100),
    ]
    assert recorded_stages == expected_stages

    # 2. Verify dry-run outcome
    assert result.status == "DRY_RUN_SUCCESS"
    assert result.dry_run is True
    assert result.submitted is False
    assert result.fields_filled_count >= 5
    assert result.submit_button_detected is not None
    assert result.screenshot_path is not None
    assert os.path.exists(result.screenshot_path)

    # 3. Verify DOM fields were actually populated in the page
    first_name_val = await browser_page.input_value("#first_name")
    assert first_name_val == "Arjun"

    last_name_val = await browser_page.input_value("#last_name")
    assert last_name_val == "Sharma"

    email_val = await browser_page.input_value("#email")
    assert email_val == "arjun.sharma@example.com"

    essay_val = await browser_page.input_value("#essay_reason")
    assert len(essay_val.split()) >= 100

    # 4. Verify submit was NOT triggered in dry-run mode
    was_submitted = await browser_page.evaluate("() => Boolean(window.__form_submitted)")
    assert was_submitted is False


@pytest.mark.asyncio
async def test_orchestrator_ciba_denial_refusal_invariant(
    browser_page, temp_vault, offline_ciba_client
):
    """Verify that CIBA consent rejection strictly raises RefusalToSubmitError and halts."""
    await browser_page.set_content(TEST_JOB_HTML)

    orchestrator = FillOrchestrator(
        vault_manager=temp_vault,
        ciba_client=offline_ciba_client,
        browserbase_service=BrowserbaseService(offline=True),
        form_filler=FormFiller(),
        dom_extractor=DOMExtractor(),
        ultramarine_client=UltramarineClient(offline_mode=True),
        auto_approve_ciba=False,  # Do not auto approve
    )

    # Intercept initiation to simulate denial
    orig_initiate = offline_ciba_client.initiate_consent

    async def _initiate_and_deny(*args, **kwargs):
        ciba_req = await orig_initiate(*args, **kwargs)
        offline_ciba_client.simulate_denial(ciba_req.auth_req_id)
        return ciba_req

    offline_ciba_client.initiate_consent = _initiate_and_deny

    with pytest.raises(RefusalToSubmitError) as exc_info:
        await orchestrator.run(
            target_url="https://boards.greenhouse.io/stripe/jobs/4012",
            dry_run=True,
            page=browser_page,
            auto_approve_ciba=False,
        )

    assert "access_denied" in str(exc_info.value) or "refused" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_orchestrator_ciba_timeout_refusal(
    browser_page, temp_vault, offline_ciba_client
):
    """Verify that CIBA expiration/timeout triggers RefusalToSubmitError."""
    await browser_page.set_content(TEST_JOB_HTML)

    orchestrator = FillOrchestrator(
        vault_manager=temp_vault,
        ciba_client=offline_ciba_client,
        browserbase_service=BrowserbaseService(offline=True),
        form_filler=FormFiller(),
        dom_extractor=DOMExtractor(),
        ultramarine_client=UltramarineClient(offline_mode=True),
        auto_approve_ciba=False,
    )

    orig_initiate = offline_ciba_client.initiate_consent

    async def _initiate_and_expire(*args, **kwargs):
        ciba_req = await orig_initiate(*args, **kwargs)
        offline_ciba_client.simulate_expiration(ciba_req.auth_req_id)
        return ciba_req

    offline_ciba_client.initiate_consent = _initiate_and_expire

    with pytest.raises(RefusalToSubmitError) as exc_info:
        await orchestrator.run(
            target_url="https://boards.greenhouse.io/stripe/jobs/4012",
            dry_run=True,
            page=browser_page,
            auto_approve_ciba=False,
        )

    assert "expired" in str(exc_info.value).lower() or "refused" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_orchestrator_w8ben_tax_compliance(
    browser_page, temp_vault, offline_ciba_client
):
    """Verify end-to-end W-8BEN form filling with Indian PAN, Box 6b uncheck, and DOB."""
    await browser_page.set_content(TEST_W8BEN_HTML)

    orchestrator = FillOrchestrator(
        vault_manager=temp_vault,
        ciba_client=offline_ciba_client,
        browserbase_service=BrowserbaseService(offline=True),
        form_filler=FormFiller(),
        dom_extractor=DOMExtractor(),
        ultramarine_client=UltramarineClient(offline_mode=True),
        auto_approve_ciba=True,
    )

    target_url = "https://compliance.contractor.io/w8ben"
    result = await orchestrator.run(
        target_url=target_url,
        dry_run=True,
        page=browser_page,
    )

    assert result.status == "DRY_RUN_SUCCESS"

    # Box 6a should contain Indian PAN
    pan_val = await browser_page.input_value("#line6a_ftin")
    assert pan_val == "ABCDE1234F"

    # Box 6b should have been UNCHECKED (since it started checked in HTML)
    is_6b_checked = await browser_page.is_checked("#line6b_no_ftin")
    assert is_6b_checked is False

    # Line 8 DOB formatted as MM-DD-YYYY
    dob_val = await browser_page.input_value("#line8_dob")
    assert dob_val == "08-15-1994"

    # Line 10 Article 12(2)
    article_val = await browser_page.input_value("#line10_article")
    assert article_val == "Article 12(2)"


@pytest.mark.asyncio
async def test_orchestrator_browserbase_session_release_in_finally():
    """Verify that Browserbase session is always released in finally block even on errors."""
    bb_service = BrowserbaseService(offline=True)
    released_sessions = []

    orig_release = bb_service.release_session

    def _spy_release(sess_id):
        released_sessions.append(sess_id)
        return orig_release(sess_id)

    bb_service.release_session = _spy_release

    ciba_client = Auth0CIBAClient(offline_mode=True)
    orchestrator = FillOrchestrator(
        browserbase_service=bb_service,
        ciba_client=ciba_client,
        auto_approve_ciba=True,
    )

    # Run against a dummy URL; DOM extraction will succeed with 0 fields
    result = await orchestrator.run(
        target_url="https://example.com/mock",
        dry_run=True,
        html_override="<html><body><p>No fields</p></body></html>",
    )

    assert result is not None
    assert len(released_sessions) == 1
    assert released_sessions[0] == result.session_id


@pytest.mark.asyncio
async def test_orchestrator_live_submission_when_dry_run_false(
    browser_page, temp_vault, offline_ciba_client
):
    """Verify that dry_run=False triggers real form submission when consent is approved."""
    await browser_page.set_content(TEST_JOB_HTML)

    orchestrator = FillOrchestrator(
        vault_manager=temp_vault,
        ciba_client=offline_ciba_client,
        browserbase_service=BrowserbaseService(offline=True),
        form_filler=FormFiller(),
        dom_extractor=DOMExtractor(),
        ultramarine_client=UltramarineClient(offline_mode=True),
        auto_approve_ciba=True,
    )

    result = await orchestrator.run(
        target_url="https://boards.greenhouse.io/stripe/jobs/4012",
        dry_run=False,
        page=browser_page,
    )

    assert result.status == "SUBMITTED"
    assert result.submitted is True
    assert result.dry_run is False

    # Check that in-page onsubmit fired
    was_submitted = await browser_page.evaluate("() => Boolean(window.__form_submitted)")
    assert was_submitted is True
