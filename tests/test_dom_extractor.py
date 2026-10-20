"""Integration and unit tests for DOMExtractor across Greenhouse, Lever, Ashby, and W-8BEN forms."""

import pytest
from playwright.async_api import async_playwright
from app.models.browser_schema import FieldType
from app.services.dom_extractor import DOMExtractor


@pytest.fixture
async def browser_page():
    """Provides an isolated Playwright page in a headless Chromium sandbox."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        yield page
        await browser.close()


# ==============================================================================
# 1. Greenhouse Form Extraction Tests
# ==============================================================================


GREENHOUSE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Job Application - Staff Distributed Systems Engineer</title></head>
<body>
  <div id="wrapper">
    <form id="application_form" action="/apply" method="POST">
      <div class="field">
        <label for="first_name">First Name <span class="asterisk">*</span></label>
        <input type="text" id="first_name" name="job_application[first_name]" required />
      </div>
      <div class="field">
        <label for="last_name">Last Name <span class="asterisk">*</span></label>
        <input type="text" id="last_name" name="job_application[last_name]" required />
      </div>
      <div class="field">
        <label for="email">Email <span class="asterisk">*</span></label>
        <input type="email" id="email" name="job_application[email]" required />
      </div>
      <div class="field">
        <label for="phone">Phone</label>
        <input type="tel" id="phone" name="job_application[phone]" />
      </div>
      <div class="field">
        <label for="resume">Resume/CV <span class="asterisk">*</span></label>
        <input type="file" id="resume" name="job_application[resume]" required />
      </div>
      <div class="field">
        <label for="work_authorization">Are you authorized to work in the US?</label>
        <select id="work_authorization" name="job_application[answers_attributes][0][boolean_value]">
          <option value="">-- Select --</option>
          <option value="1">Yes</option>
          <option value="0">No</option>
        </select>
      </div>
      <div class="field">
        <label for="cover_letter">Cover Letter</label>
        <textarea id="cover_letter" name="job_application[cover_letter]"></textarea>
      </div>
      <button type="submit" id="submit_app">Submit Application</button>
    </form>
  </div>
</body>
</html>
"""


async def test_extract_greenhouse_form(browser_page):
    """Verify DOMExtractor correctly parses Greenhouse ATS structures."""
    await browser_page.set_content(GREENHOUSE_HTML)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert schema.detected_platform == "greenhouse"
    assert len(schema.fields) == 7
    assert len(schema.submit_buttons) == 1
    assert schema.submit_buttons[0].text == "Submit Application"

    # Verify First Name
    fn = next(f for f in schema.fields if f.field_id == "first_name")
    assert fn.field_type == FieldType.TEXT
    assert fn.required is True
    assert "First Name" in fn.label

    # Verify Email
    em = next(f for f in schema.fields if f.field_id == "email")
    assert em.field_type == FieldType.EMAIL
    assert em.required is True

    # Verify Resume file upload
    res = next(f for f in schema.fields if f.field_id == "resume")
    assert res.field_type == FieldType.FILE
    assert res.required is True

    # Verify Select options
    auth = next(f for f in schema.fields if f.field_id == "work_authorization")
    assert auth.field_type == FieldType.SELECT
    assert len(auth.options) == 3
    assert any(o.label == "Yes" and o.value == "1" for o in auth.options)
    assert any(o.label == "No" and o.value == "0" for o in auth.options)


# ==============================================================================
# 2. Lever Form Extraction Tests
# ==============================================================================


LEVER_HTML = """
<!DOCTYPE html>
<html>
<head><title>Acme Corp - Senior Autonomous Systems Engineer</title></head>
<body>
  <div class="application-container">
    <form class="application-form" id="application-form" action="/apply" method="POST">
      <div class="application-question">
        <div class="application-label">Resume/CV <span>✱</span></div>
        <input type="file" name="resume" class="card-upload-input" />
      </div>
      <div class="application-question">
        <div class="application-label">Full name <span>✱</span></div>
        <input type="text" name="name" required />
      </div>
      <div class="application-question">
        <div class="application-label">Email <span>✱</span></div>
        <input type="email" name="email" required />
      </div>
      <div class="application-question">
        <div class="application-label">Phone </div>
        <input type="tel" name="phone" />
      </div>
      <div class="application-question">
        <div class="application-label">Current company </div>
        <input type="text" name="org" />
      </div>
      <div class="application-question">
        <div class="application-label">LinkedIn URL</div>
        <input type="text" name="urls[LinkedIn]" />
      </div>
      <div class="application-question">
        <div class="application-label">GitHub URL</div>
        <input type="text" name="urls[GitHub]" />
      </div>
      <div class="application-question">
        <div class="application-label">Additional Information / Essay</div>
        <textarea name="comments" placeholder="Add any details you would like to share..."></textarea>
      </div>
      <button type="submit" class="template-btn-submit">Submit application</button>
    </form>
  </div>
</body>
</html>
"""


async def test_extract_lever_form(browser_page):
    """Verify DOMExtractor correctly resolves Lever forms with single Full Name and grouped labels."""
    await browser_page.set_content(LEVER_HTML)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert schema.detected_platform == "lever"
    assert len(schema.fields) == 8
    assert len(schema.submit_buttons) == 1
    assert "Submit" in schema.submit_buttons[0].text

    name_field = next(f for f in schema.fields if f.name_attr == "name")
    assert name_field.field_type == FieldType.TEXT
    assert "Full name" in name_field.label
    assert name_field.required is True

    linkedin = next(f for f in schema.fields if f.name_attr == "urls[LinkedIn]")
    assert linkedin.field_type == FieldType.URL
    assert "LinkedIn" in linkedin.label

    github = next(f for f in schema.fields if f.name_attr == "urls[GitHub]")
    assert github.field_type == FieldType.URL

    textarea = next(f for f in schema.fields if f.name_attr == "comments")
    assert textarea.field_type == FieldType.TEXTAREA


# ==============================================================================
# 3. IRS Form W-8BEN Tax Treaty Extraction Tests
# ==============================================================================


W8BEN_HTML = """
<!DOCTYPE html>
<html>
<head><title>IRS Form W-8BEN Certificate of Foreign Status</title></head>
<body>
  <h1>Form W-8BEN Certificate of Foreign Status of Beneficial Owner</h1>
  <form id="w8ben_form">
    <div class="section">
      <h3>Part I Identification of Beneficial Owner</h3>
      <div class="field">
        <label for="beneficial_owner_name">1. Name of individual who is the beneficial owner</label>
        <input type="text" id="beneficial_owner_name" name="beneficial_owner_name" required />
      </div>
      <div class="field">
        <label for="country_citizenship">2. Country of citizenship</label>
        <select id="country_citizenship" name="country_citizenship">
          <option value="IN">India</option>
          <option value="GB">United Kingdom</option>
          <option value="DE">Germany</option>
        </select>
      </div>
      <div class="field">
        <label for="perm_address">3. Permanent residence address</label>
        <input type="text" id="perm_address" name="perm_address" required />
      </div>
      <div class="field">
        <label for="ftin">6a. Foreign tax identifying number (FTIN / Indian PAN)</label>
        <input type="text" id="ftin" name="foreign_tax_id" required />
      </div>
      <div class="field">
        <label for="ftin_not_req">6b. Check if FTIN not legally required</label>
        <input type="checkbox" id="ftin_not_req" name="ftin_not_required" />
      </div>
      <div class="field">
        <label for="dob">8. Date of birth (MM-DD-YYYY)</label>
        <input type="text" id="dob" name="date_of_birth" placeholder="MM-DD-YYYY" />
      </div>
    </div>
    <div class="section">
      <h3>Part II Claim of Tax Treaty Benefits</h3>
      <div class="field">
        <label for="treaty_country">9. Treaty Country</label>
        <input type="text" id="treaty_country" name="treaty_country" value="India" />
      </div>
      <div class="field">
        <label for="treaty_article">10. Special rates and conditions (Article number)</label>
        <input type="text" id="treaty_article" name="treaty_article" />
      </div>
      <div class="field">
        <label for="withholding_rate">10. Rate of withholding (%)</label>
        <input type="number" id="withholding_rate" name="withholding_rate" />
      </div>
    </div>
    <button type="submit" id="submit_w8ben">Submit Tax Certification</button>
  </form>
</body>
</html>
"""


async def test_extract_w8ben_form(browser_page):
    """Verify DOMExtractor handles IRS Form W-8BEN tax identification fields."""
    await browser_page.set_content(W8BEN_HTML)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert schema.detected_platform == "w8ben"
    assert len(schema.fields) == 9
    assert len(schema.submit_buttons) == 1

    # Box 6a Foreign Tax ID
    box6a = next(f for f in schema.fields if f.field_id == "ftin")
    assert "Foreign tax identifying number" in box6a.label or "6a" in box6a.label
    assert box6a.required is True

    # Box 6b Checkbox
    box6b = next(f for f in schema.fields if f.field_id == "ftin_not_req")
    assert box6b.field_type == FieldType.CHECKBOX

    # Box 8 Date of birth
    box8 = next(f for f in schema.fields if f.field_id == "dob")
    assert box8.field_type == FieldType.DATE
    assert box8.placeholder == "MM-DD-YYYY"


# ==============================================================================
# 4. Multi-Frame / Nested Iframe Extraction Tests
# ==============================================================================


async def test_extract_nested_iframes(browser_page):
    """Verify recursive traversal across embedded iframes (e.g. corporate career page embedding ATS)."""
    parent_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Careers at Global Corp</title></head>
    <body>
      <nav><h1>Welcome to Global Corp</h1></nav>
      <iframe id="grnhse_iframe" srcdoc='
        <html>
        <body>
          <form id="application_form">
            <label for="applicant_name">Your Name</label>
            <input type="text" id="applicant_name" required />
            <label for="applicant_email">Email</label>
            <input type="email" id="applicant_email" required />
            <button type="submit">Apply Now</button>
          </form>
        </body>
        </html>
      '></iframe>
    </body>
    </html>
    """
    await browser_page.set_content(parent_html)
    # Allow iframe to attach
    await browser_page.wait_for_timeout(300)

    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert schema.has_iframes is True
    assert len(schema.fields) >= 2
    # Field from child frame has frame_index > 0
    child_fields = [f for f in schema.fields if f.frame_index > 0]
    assert len(child_fields) >= 2
    assert any(f.field_id == "applicant_name" for f in child_fields)
    assert len(schema.submit_buttons) >= 1


# ==============================================================================
# 5. Ashby Custom Combobox & Additional Edge Case Tests
# ==============================================================================


ASHBY_HTML = """
<!DOCTYPE html>
<html>
<head><title>Ashby Application - Principal Architect</title></head>
<body>
  <form action="/apply">
    <div class="field">
      <label for="_systemfield_name">Full Name</label>
      <input type="text" id="_systemfield_name" required />
    </div>
    <div class="field">
      <label for="_systemfield_email">Email</label>
      <input type="email" id="_systemfield_email" required />
    </div>
    <div class="field">
      <label>Department</label>
      <div role="combobox" id="dept_combo" aria-label="Department Selection" tabindex="0">
        Engineering
      </div>
    </div>
    <button type="submit">Submit Application</button>
  </form>
</body>
</html>
"""


async def test_extract_ashby_combobox(browser_page):
    """Verify Ashby custom role=combobox extraction and platform detection."""
    await browser_page.set_content(ASHBY_HTML)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert schema.detected_platform == "ashby"
    assert len(schema.fields) == 3

    combo = next(f for f in schema.fields if f.field_id == "dept_combo")
    assert combo.field_type == FieldType.COMBOBOX
    assert "Department" in combo.label


async def test_extract_generic_minimal_form(browser_page):
    """Verify fallback platform detection for standard generic HTML forms."""
    minimal_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Contact Feedback</title></head>
    <body>
      <form>
        <label for="msg">Message</label>
        <textarea id="msg"></textarea>
        <button type="submit">Send</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(minimal_html)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert schema.detected_platform == "generic"
    assert len(schema.fields) == 1
    assert schema.fields[0].field_type == FieldType.TEXTAREA
    assert len(schema.submit_buttons) == 1
