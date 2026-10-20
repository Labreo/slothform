"""Comprehensive integration tests for FormFiller, CDP file streaming, and pre-submission dry-run guard."""

import os
import pytest
from playwright.async_api import async_playwright
from app.models.browser_schema import (
    FieldType,
    FillPlan,
    FillPlanItem,
)
from app.services.document_generator import (
    SyntheticDocumentGenerator,
)
from app.services.form_filler import FormFiller


@pytest.fixture
async def browser_page(tmp_path):
    """Provides an isolated Playwright page in a headless Chromium sandbox."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        yield page
        await browser.close()


@pytest.fixture
def test_screenshot_dir(tmp_path):
    """Provides an isolated temporary screenshot directory."""
    s_dir = str(tmp_path / "screenshots")
    os.makedirs(s_dir, exist_ok=True)
    return s_dir


TEST_FORM_HTML = """
<!DOCTYPE html>
<html>
<head><title>Senior Systems Engineer Application</title></head>
<body>
  <h1>Apply for Position</h1>
  <form id="test_job_form" onsubmit="window.__form_submitted = true; return false;">
    <div>
      <label for="applicant_name">Full Name</label>
      <input type="text" id="applicant_name" name="name" />
    </div>
    <div>
      <label for="applicant_email">Email</label>
      <input type="email" id="applicant_email" name="email" />
    </div>
    <div>
      <label for="role_select">Target Role</label>
      <select id="role_select" name="role">
        <option value="">-- Choose Role --</option>
        <option value="frontend">Frontend Specialist</option>
        <option value="backend">Backend Architect</option>
      </select>
    </div>
    <div>
      <label for="relocate">Willing to relocate</label>
      <input type="checkbox" id="relocate" name="relocate" />
    </div>
    <div>
      <label for="resume_upload">Resume Document</label>
      <input type="file" id="resume_upload" name="resume" />
    </div>
    <div>
      <label for="notes">Notes</label>
      <textarea id="notes" name="notes"></textarea>
    </div>
    <button type="submit" id="submit_button">Submit Application</button>
  </form>
</body>
</html>
"""


# ==============================================================================
# 1. Pre-Submission Dry-Run Safety Guard Tests
# ==============================================================================


async def test_dry_run_populates_fields_and_strictly_halts(browser_page, test_screenshot_dir):
    """
    Verify that dry_run=True:
    1. Populates all fields
    2. Injects amber outline (#f59e0b) on submit button
    3. Saves full-page screenshot
    4. NEVER clicks submit (window.__form_submitted remains undefined)
    5. Returns status DRY_RUN_SUCCESS with submitted=False
    """
    await browser_page.set_content(TEST_FORM_HTML)

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/apply",
        items=[
            FillPlanItem(field_id="applicant_name", selector="#applicant_name", field_type=FieldType.TEXT, value="Sanjay Waradkar"),
            FillPlanItem(field_id="applicant_email", selector="#applicant_email", field_type=FieldType.EMAIL, value="sanjay@example.com"),
            FillPlanItem(field_id="role_select", selector="#role_select", field_type=FieldType.SELECT, value="backend"),
            FillPlanItem(field_id="relocate", selector="#relocate", field_type=FieldType.CHECKBOX, value=True),
            FillPlanItem(field_id="notes", selector="#notes", field_type=FieldType.TEXTAREA, value="Extensive cloud automation background."),
        ],
    )

    result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
        session_id="sess_test_dryrun",
    )

    # 1. Verification of FillResult contract
    assert result.status == "DRY_RUN_SUCCESS"
    assert result.dry_run is True
    assert result.submitted is False
    assert result.error is None
    assert result.fields_filled_count >= 5
    assert result.submit_button_detected is not None
    assert "https://browserbase.com/sessions/sess_test_dryrun" in result.replay_url

    # 2. Verification of In-Page Populated Data
    name_val = await browser_page.input_value("#applicant_name")
    assert name_val == "Sanjay Waradkar"

    email_val = await browser_page.input_value("#applicant_email")
    assert email_val == "sanjay@example.com"

    select_val = await browser_page.input_value("#role_select")
    assert select_val == "backend"

    checkbox_val = await browser_page.is_checked("#relocate")
    assert checkbox_val is True

    notes_val = await browser_page.input_value("#notes")
    assert notes_val == "Extensive cloud automation background."

    # 3. CRITICAL SAFETY INVARIANT: Form was NOT submitted
    is_submitted = await browser_page.evaluate("() => window.__form_submitted")
    assert is_submitted is None or is_submitted is False

    # 4. Verification of Amber Glow Outline (#f59e0b) on submit button
    btn_style = await browser_page.evaluate("() => document.getElementById('submit_button').style.outline")
    btn_guarded = await browser_page.evaluate("() => document.getElementById('submit_button').getAttribute('data-slothform-dry-run')")
    assert "f59e0b" in btn_style or "245, 158, 11" in btn_style
    assert btn_guarded == "guarded"

    # 5. Verification of Screenshot Generation
    assert result.screenshot_path is not None
    assert os.path.isfile(result.screenshot_path)
    assert os.path.getsize(result.screenshot_path) > 1000  # Valid non-empty PNG


# ==============================================================================
# 2. Live Dispatch (dry_run=False) Execution Tests
# ==============================================================================


async def test_live_dispatch_triggers_submit_click(browser_page, test_screenshot_dir):
    """
    Verify that dry_run=False:
    1. Clicks submit button
    2. Successfully fires onsubmit event (window.__form_submitted = True)
    3. Returns status SUBMITTED with submitted=True
    """
    await browser_page.set_content(TEST_FORM_HTML)

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/apply",
        items=[
            FillPlanItem(field_id="applicant_name", selector="#applicant_name", field_type=FieldType.TEXT, value="Live Candidate"),
        ],
    )

    result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=False,
        session_id="sess_test_live",
    )

    assert result.status == "SUBMITTED"
    assert result.dry_run is False
    assert result.submitted is True
    assert result.error is None

    # Verify submit button was genuinely clicked
    is_submitted = await browser_page.evaluate("() => window.__form_submitted")
    assert is_submitted is True


# ==============================================================================
# 3. CDP File Streaming & Synthetic Fallback Tests
# ==============================================================================


async def test_file_upload_synthetic_fallback(browser_page, test_screenshot_dir):
    """
    Verify that if no pre-existing file path is given, FormFiller generates
    a synthetic fallback PDF and attaches it to the remote input.
    """
    await browser_page.set_content(TEST_FORM_HTML)

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/apply",
        items=[
            FillPlanItem(field_id="resume_upload", selector="#resume_upload", field_type=FieldType.FILE, value=None),
        ],
    )

    result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
    )

    assert result.status == "DRY_RUN_SUCCESS"

    # Verify a file was genuinely attached to input[type="file"]
    attached_files_count = await browser_page.evaluate("() => document.getElementById('resume_upload').files.length")
    assert attached_files_count == 1

    file_name = await browser_page.evaluate("() => document.getElementById('resume_upload').files[0].name")
    assert file_name.endswith(".pdf")


# ==============================================================================
# 4. W-8BEN Box 6b Uncheck Invariant Tests
# ==============================================================================


async def test_w8ben_uncheck_box6b_invariant(browser_page, test_screenshot_dir):
    """
    Verify that Box 6b ('Check if FTIN not legally required') is explicitly
    unchecked when instructed, ensuring tax treaty compliance.
    """
    w8_html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="w8_form">
        <label for="pan">6a. Foreign Tax Identifying Number (PAN)</label>
        <input type="text" id="pan" name="pan" />
        <label for="not_req">6b. Check if FTIN not legally required</label>
        <input type="checkbox" id="not_req" name="not_req" checked />
        <button type="submit">Submit</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(w8_html)

    # Initial state: checkbox is checked
    assert await browser_page.is_checked("#not_req") is True

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/w8",
        items=[
            FillPlanItem(field_id="pan", selector="#pan", field_type=FieldType.TEXT, value="ABCDE1234F"),
            FillPlanItem(field_id="not_req", selector="#not_req", field_type=FieldType.CHECKBOX, value="uncheck"),
        ],
    )

    result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
    )

    assert result.status == "DRY_RUN_SUCCESS"
    assert await browser_page.input_value("#pan") == "ABCDE1234F"
    # Checkbox must now be unchecked
    assert await browser_page.is_checked("#not_req") is False


# ==============================================================================
# 5. Synthetic Document Generator Tests
# ==============================================================================


def test_synthetic_resume_generation(tmp_path):
    """Verify synthetic resume generation creates a valid PDF document."""
    gen = SyntheticDocumentGenerator(output_dir=str(tmp_path))
    pdf_path = gen.generate_resume({"full_name": "Priya Patel", "email": "priya@example.com"})

    assert os.path.isfile(pdf_path)
    assert os.path.getsize(pdf_path) > 1000
    with open(pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_synthetic_w8ben_generation(tmp_path):
    """Verify synthetic W-8BEN generation creates a valid PDF document with Article 12(2)."""
    gen = SyntheticDocumentGenerator(output_dir=str(tmp_path))
    pdf_path = gen.generate_tax_document({"full_name": "Priya Patel", "pan": "ABCDE9999Z"})

    assert os.path.isfile(pdf_path)
    assert os.path.getsize(pdf_path) > 1000
    with open(pdf_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_synthetic_document_generator_unique_concurrency_filenames(tmp_path):
    """Verify that multiple concurrent generations produce unique filenames with UUID suffixes."""
    gen = SyntheticDocumentGenerator(output_dir=str(tmp_path))
    resume_path_1 = gen.generate_resume({"full_name": "Dev User"})
    resume_path_2 = gen.generate_resume({"full_name": "Dev User"})
    tax_path_1 = gen.generate_tax_document({"full_name": "Dev User"})
    tax_path_2 = gen.generate_tax_document({"full_name": "Dev User"})

    assert resume_path_1 != resume_path_2
    assert tax_path_1 != tax_path_2
    assert os.path.basename(resume_path_1).startswith("resume_dev_user_")
    assert os.path.basename(tax_path_1).startswith("w8ben_dev_user_")
    assert os.path.isfile(resume_path_1) and os.path.isfile(resume_path_2)
    assert os.path.isfile(tax_path_1) and os.path.isfile(tax_path_2)


async def test_file_upload_tax_w8ben_fallback(browser_page, test_screenshot_dir):
    """Verify that when field context indicates tax/W-8BEN, FormFiller generates a synthetic tax document."""
    tax_form_html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="onboarding_tax_form">
        <label for="w8_tax_upload">IRS Form W-8BEN Tax Certificate</label>
        <input type="file" id="w8_tax_upload" name="w8ben_file" />
        <button type="submit" id="submit_btn">Submit Application</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(tax_form_html)

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/contractor_tax_onboarding",
        items=[
            FillPlanItem(
                field_id="w8_tax_upload",
                selector="#w8_tax_upload",
                field_type=FieldType.FILE,
                value=None,
                rationale="IRS W-8BEN Foreign Status Certification",
            ),
        ],
    )

    result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
    )

    assert result.status == "DRY_RUN_SUCCESS"
    attached_count = await browser_page.evaluate("() => document.getElementById('w8_tax_upload').files.length")
    assert attached_count == 1
    file_name = await browser_page.evaluate("() => document.getElementById('w8_tax_upload').files[0].name")
    assert "w8ben_" in file_name
    assert file_name.endswith(".pdf")


async def test_custom_role_button_submit_detection(browser_page, test_screenshot_dir):
    """Verify that custom SPAs using [role=button] for submit are properly detected and guarded."""
    custom_btn_html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="custom_spa_form">
        <input type="text" id="uname" name="uname" />
        <div role="button" id="custom_submit" tabindex="0">Submit Application</div>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(custom_btn_html)

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/custom_spa",
        items=[
            FillPlanItem(field_id="uname", selector="#uname", field_type=FieldType.TEXT, value="Alice"),
        ],
    )

    result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
    )

    assert result.status == "DRY_RUN_SUCCESS"
    assert result.submit_button_detected is not None
    assert "submit application" in result.submit_button_detected.lower()

    guarded = await browser_page.evaluate("() => document.getElementById('custom_submit').getAttribute('data-slothform-dry-run')")
    assert guarded == "guarded"

