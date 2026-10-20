"""Adversarial stress-testing suite for FormFiller pre-submission --dry-run safety guard.

Investigates whether FormFiller under dry_run=True can be forced into accidental submissions:
1. Forms where Enter key triggers accidental submission (Combobox fallback & text inputs)
2. Forms with auto-submit on change (e.g. country select, terms checkbox)
3. Forms with auto-submit on input (e.g. zip code or coupon auto-lookup)
4. Forms with auto-submit on blur (JS form.submit() on leaving field)
5. Forms with direct HTMLFormElement.prototype.submit()
6. Deceptive multiple submit buttons (e.g. "Save Draft" vs "Submit Application")
7. Hidden submit triggers (<input type="submit" style="display:none">)
"""

import os
import pytest
from playwright.async_api import async_playwright
from app.models.browser_schema import (
    FieldType,
    FillPlan,
    FillPlanItem,
)
from app.services.form_filler import FormFiller


@pytest.fixture
async def browser_page():
    """Provides an isolated Playwright page in a headless Chromium sandbox."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        yield page
        await browser.close()


@pytest.fixture
def test_screenshot_dir(tmp_path):
    """Provides an isolated temporary screenshot directory."""
    s_dir = str(tmp_path / "adversarial_screenshots")
    os.makedirs(s_dir, exist_ok=True)
    return s_dir


# ==============================================================================
# Challenge 1: Combobox Fallback Pressing Enter Triggers Implicit Form Submit
# ==============================================================================


async def test_combobox_enter_key_triggers_accidental_submission(browser_page, test_screenshot_dir):
    """
    STRESS TEST: When a COMBOBOX has no matching dropdown options, FormFiller lines 116-117
    executes:
        await locator.fill(val_str, timeout=2000)
        await page.keyboard.press("Enter")
    In standard HTML forms, pressing Enter inside an <input> triggers implicit form submission!
    Under --dry-run, this MUST NEVER submit the form or issue a submit request.
    """
    html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="job_form" action="https://httpbin.org/post" method="POST"
            onsubmit="window.__form_submitted = true; event.preventDefault(); return false;">
        <label for="role_input">Target Role</label>
        <input type="text" id="role_input" role="combobox" name="role" />
        <button type="submit" id="submit_btn">Submit Application</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(html)

    network_requests = []
    browser_page.on("request", lambda r: network_requests.append(r.url))

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/adversarial_combobox",
        items=[
            FillPlanItem(
                field_id="role_input",
                selector="#role_input",
                field_type=FieldType.COMBOBOX,
                value="Staff Security Architect",
            ),
        ],
    )

    result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
        session_id="sess_adv_combobox",
    )

    is_submitted = await browser_page.evaluate("() => window.__form_submitted === true")
    post_requests = [r for r in network_requests if "httpbin.org/post" in r]

    # Under --dry-run, form submission MUST be strictly impossible!
    assert is_submitted is not True, (
        f"CRITICAL VULNERABILITY: Form was submitted during --dry-run! "
        f"FormFiller pressed Enter on combobox input, triggering implicit HTML form submission. "
        f"result.submitted was {result.submitted}, but browser state __form_submitted is True."
    )
    assert len(post_requests) == 0, (
        f"CRITICAL VULNERABILITY: HTTP POST request sent to server during --dry-run! Requests: {post_requests}"
    )


# ==============================================================================
# Challenge 2: Auto-Submitting Inputs (onchange="this.form.submit()")
# ==============================================================================


async def test_onchange_auto_submit_trigger(browser_page, test_screenshot_dir):
    """
    STRESS TEST: A form with a select or input that auto-submits on change:
    <select onchange="this.form.submit()">.
    When FormFiller populates this field, Playwright dispatches the change event.
    Under --dry-run, the agent MUST NOT trigger form submission or network POST.
    """
    html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="auto_submit_form" action="https://httpbin.org/post" method="POST">
        <label for="country_select">Select Country</label>
        <select id="country_select" name="country" onchange="this.form.submit();">
          <option value="US">United States</option>
          <option value="IN">India</option>
          <option value="DE">Germany</option>
        </select>
        <button type="submit" id="submit_btn">Submit Application</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(html)

    network_requests = []
    browser_page.on("request", lambda r: network_requests.append(r.url))

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/auto_submit",
        items=[
            FillPlanItem(
                field_id="country_select",
                selector="#country_select",
                field_type=FieldType.SELECT,
                value="IN",
            ),
        ],
    )

    _result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
        session_id="sess_adv_auto_submit",
    )

    post_requests = [r for r in network_requests if "httpbin.org/post" in r]

    assert len(post_requests) == 0, (
        f"CRITICAL VULNERABILITY: Form auto-submitted over network during --dry-run via onchange event! "
        f"FormFiller did not neutralize HTMLFormElement.prototype.submit or navigation during dry-run. "
        f"Network requests intercepted: {post_requests}"
    )


# ==============================================================================
# Challenge 3: Onblur JavaScript form.submit() Invocation
# ==============================================================================


async def test_onblur_javascript_form_submit(browser_page, test_screenshot_dir):
    """
    STRESS TEST: Form where an input triggers form.submit() on blur.
    When FormFiller finishes typing in the input and moves focus to the next field or submit button,
    the blur event fires and calls form.submit().
    Under --dry-run, this submission must be intercepted / prevented.
    """
    html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="blur_submit_form" action="https://httpbin.org/post" method="POST">
        <label for="applicant_name">Full Name</label>
        <input type="text" id="applicant_name" name="name"
               onblur="this.form.submit();" />
        <label for="notes">Notes</label>
        <textarea id="notes" name="notes"></textarea>
        <button type="submit" id="submit_btn">Submit</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(html)

    network_requests = []
    browser_page.on("request", lambda r: network_requests.append(r.url))

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/blur_submit",
        items=[
            FillPlanItem(
                field_id="applicant_name",
                selector="#applicant_name",
                field_type=FieldType.TEXT,
                value="Alice Wonder",
            ),
            FillPlanItem(
                field_id="notes",
                selector="#notes",
                field_type=FieldType.TEXTAREA,
                value="Some notes",
            ),
        ],
    )

    _result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
        session_id="sess_adv_blur",
    )

    post_requests = [r for r in network_requests if "httpbin.org/post" in r]

    assert len(post_requests) == 0, (
        f"CRITICAL VULNERABILITY: Form submitted on blur over network during --dry-run! "
        f"Requests: {post_requests}"
    )


# ==============================================================================
# Challenge 4: Multiple Deceptive Submit Buttons
# ==============================================================================


async def test_deceptive_first_submit_button_selection(browser_page, test_screenshot_dir):
    """
    STRESS TEST: A form with multiple submit buttons where the first button is deceptive:
    e.g. <button type="submit" name="action" value="draft">Save Draft</button>
    followed by:
    <button type="submit" name="action" value="submit">Submit Application</button>.
    
    FormFiller uses:
        candidate_selectors = ['button[type="submit"]', ...]
    and takes .first.
    
    In dry-run mode:
    Which button is styled with amber glow?
    If 'Save Draft' is styled, the user verification screenshot falsely claims the submit button
    is guarded while the ACTUAL application submit button has no safety outline!
    """
    html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="multi_btn_form">
        <input type="text" id="uname" name="uname" />
        <div class="actions">
          <button type="submit" id="btn_draft" name="action" value="draft">Save Draft</button>
          <button type="submit" id="btn_cancel" name="action" value="cancel">Cancel Application</button>
          <button type="submit" id="btn_final" name="action" value="submit">Submit Application</button>
        </div>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(html)

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/deceptive_buttons",
        items=[
            FillPlanItem(field_id="uname", selector="#uname", field_type=FieldType.TEXT, value="John Doe"),
        ],
    )

    result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
        session_id="sess_adv_deceptive",
    )

    assert result.status == "DRY_RUN_SUCCESS"

    # Check which button received the amber glow outline
    draft_guarded = await browser_page.evaluate("() => document.getElementById('btn_draft').getAttribute('data-slothform-dry-run')")
    final_guarded = await browser_page.evaluate("() => document.getElementById('btn_final').getAttribute('data-slothform-dry-run')")

    # The actual submission button MUST be guarded!
    assert final_guarded == "guarded", (
        f"DEFECT: In a multi-button form, FormFiller picked the first button[type='submit'] ('Save Draft') "
        f"instead of the primary 'Submit Application' button! "
        f"btn_draft guarded: {draft_guarded}, btn_final guarded: {final_guarded}."
    )


# ==============================================================================
# Challenge 5: Hidden Submit Input Preceding Visible Submit Button
# ==============================================================================


async def test_hidden_submit_input_stealing_guard(browser_page, test_screenshot_dir):
    """
    STRESS TEST: A form with a hidden submit input:
    <input type="submit" style="display:none;" id="hidden_submit" />
    and a visible submit button:
    <button type="submit" id="visible_submit">Submit Application</button>.
    
    If the hidden input is styled or picked:
    The visual screenshot will NOT show any amber outline on the visible button!
    """
    html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="hidden_trigger_form">
        <button type="submit" id="hidden_submit" style="display:none;">Hidden</button>
        <input type="text" id="uname" name="uname" />
        <button type="submit" id="visible_submit">Submit Application</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(html)

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/hidden_trigger",
        items=[
            FillPlanItem(field_id="uname", selector="#uname", field_type=FieldType.TEXT, value="John Doe"),
        ],
    )

    result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
        session_id="sess_adv_hidden",
    )

    assert result.status == "DRY_RUN_SUCCESS"

    visible_guarded = await browser_page.evaluate("() => document.getElementById('visible_submit').getAttribute('data-slothform-dry-run')")
    assert visible_guarded == "guarded", (
        "DEFECT: The visible submit button was not guarded because a hidden button[type=submit] was present first!"
    )


# ==============================================================================
# Challenge 6: Input oninput Auto-Submit Trigger
# ==============================================================================


async def test_oninput_auto_submit_trigger(browser_page, test_screenshot_dir):
    """
    STRESS TEST: An input field that triggers form submission on input once length >= 5:
    e.g. zip code or coupon code or PAN number validation.
    When FormFiller fills the input, input events fire.
    Under --dry-run, this submission MUST NOT occur.
    """
    html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="input_submit_form" action="https://httpbin.org/post" method="POST">
        <label for="zip_code">ZIP Code</label>
        <input type="text" id="zip_code" name="zip"
               oninput="if(this.value.length >= 5) this.form.submit();" />
        <button type="submit" id="submit_btn">Submit</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(html)

    network_requests = []
    browser_page.on("request", lambda r: network_requests.append(r.url))

    filler = FormFiller(screenshot_dir=test_screenshot_dir)
    plan = FillPlan(
        target_url="https://example.com/input_submit",
        items=[
            FillPlanItem(
                field_id="zip_code",
                selector="#zip_code",
                field_type=FieldType.TEXT,
                value="94105",
            ),
        ],
    )

    _result = await filler.fill(
        page=browser_page,
        fill_plan=plan,
        dry_run=True,
        session_id="sess_adv_input",
    )

    post_requests = [r for r in network_requests if "httpbin.org/post" in r]

    assert len(post_requests) == 0, (
        f"CRITICAL VULNERABILITY: Form submitted on input event over network during --dry-run! "
        f"Requests: {post_requests}"
    )
