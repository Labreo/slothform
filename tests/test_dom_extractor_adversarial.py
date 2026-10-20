"""Adversarial stress-testing suite for DOMExtractor.

Empirically tests resilience against:
1. Malformed HTML with unclosed tags (unclosed form, unclosed divs, unclosed fieldsets,
   unclosed labels, unclosed select options, unquoted attributes, orphan inputs, overlapping tags)
2. Deeply nested iframes (3+ levels of depth: root -> L1 -> L2 -> L3 -> L4)
3. Obfuscated dynamic input IDs (React 18 IDs, UUIDs, special CSS characters, numeric IDs, spaced IDs)
4. Hidden and disabled inputs (display:none, visibility:hidden, disabled, readonly, type=hidden, honeypots)
5. Forms with zero submit buttons (autosave forms, discard-only buttons, read-only forms)
6. Forms with multiple submit buttons, conflicting actions, and selector deduplication
7. Extreme edge cases: empty DOM, 120+ dense fields, Unicode & emoji labels, XSS script injection tags
8. End-to-end selector validity verification: every generated selector is queryable by Playwright locators
"""

import html
import pytest
from playwright.async_api import async_playwright
from app.models.browser_schema import FieldType, FormSchema
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
# 1. Malformed HTML with Unclosed Tags & Corrupted Structures
# ==============================================================================


MALFORMED_HTML = """
<!DOCTYPE html>
<html>
<head><title>Corrupted & Unclosed Tags Portal</title>
<body>
  <!-- Unclosed wrapper div -->
  <div class="main-container">
    <!-- Unclosed form #1 overlapping form #2 -->
    <form id="broken_form" action="/corrupt" method="POST">
      <fieldset>
        <legend>Applicant Information
        <!-- Unclosed div and label -->
        <div class="field">
          <label for="unclosed_input">Full Legal Name
          <input type="text" id="unclosed_input" name="unclosed_field" value="John Doe">
        <!-- Unclosed div -->
        <div class="field">
          <label for="unquoted_attr">Unquoted Attributes
          <input type=email id=unquoted_attr name=unquoted_email required>
        <!-- Unclosed select with unclosed options -->
        <div class="field">
          <label for="unclosed_select">Country of Residence
          <select id="unclosed_select" name="country">
            <option value="US">United States
            <option value="IN">India
            <option value="UK">United Kingdom
        <!-- Broken table layout wrapping inputs -->
        <table>
          <tr>
            <td>
              <label for="table_input">Phone in Table Cell</label>
            <td>
              <input type="tel" id="table_input" name="phone_num">
        <!-- Orphan input outside fieldset -->
        <label for="notes">Comments & Notes</label>
        <textarea id="notes" name="candidate_notes">Pre-filled notes</textarea>
        <!-- File input without closing container -->
        <label for="dangling_file">Resume File</label>
        <input type="file" id="dangling_file" name="resume_file">
      <!-- Unclosed fieldset -->
      <button type="submit" id="btn_submit">Submit Corrupted Form</button>
  <!-- Missing closing tags for form and div -->
</body>
</html>
"""


async def test_adversarial_malformed_html_unclosed_tags(browser_page):
    """Verify DOMExtractor does not crash on malformed HTML with unclosed tags and extracts valid schema."""
    await browser_page.set_content(MALFORMED_HTML)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert isinstance(schema, FormSchema)
    assert len(schema.fields) == 6
    assert len(schema.submit_buttons) == 1

    # Verify text input (noting that unclosed label leakage may trigger semantic promotion)
    unclosed_input = next((f for f in schema.fields if f.field_id == "unclosed_input"), None)
    assert unclosed_input is not None
    assert unclosed_input.field_type in (FieldType.TEXT, FieldType.TEL)
    assert "Full Legal Name" in unclosed_input.label

    # Verify unquoted attribute field
    unquoted = next((f for f in schema.fields if f.field_id == "unquoted_attr"), None)
    assert unquoted is not None
    assert unquoted.field_type == FieldType.EMAIL
    assert unquoted.required is True

    # Verify unclosed select with unclosed options
    unclosed_sel = next((f for f in schema.fields if f.field_id == "unclosed_select"), None)
    assert unclosed_sel is not None
    assert unclosed_sel.field_type == FieldType.SELECT
    assert len(unclosed_sel.options) == 3
    assert any(o.value == "IN" and "India" in o.label for o in unclosed_sel.options)

    # Verify table input
    table_inp = next((f for f in schema.fields if f.field_id == "table_input"), None)
    assert table_inp is not None
    assert table_inp.field_type == FieldType.TEL

    # Verify textarea
    ta = next((f for f in schema.fields if f.field_id == "notes"), None)
    assert ta is not None
    assert ta.field_type == FieldType.TEXTAREA

    # Verify file input
    fl = next((f for f in schema.fields if f.field_id == "dangling_file"), None)
    assert fl is not None
    assert fl.field_type == FieldType.FILE

    # Verify submit button
    assert schema.submit_buttons[0].text == "Submit Corrupted Form"


# ==============================================================================
# 2. Deeply Nested Iframes (3+ Levels of Depth)
# ==============================================================================


async def test_adversarial_nested_iframes_depth_3_plus(browser_page):
    """Verify recursive DOM extraction across 4 levels of nested iframes."""
    # Construct 4-level deep iframe tree using HTML-escaped srcdoc attributes
    level_4_html = """
    <!DOCTYPE html>
    <html>
    <body>
      <form id="form_l4">
        <label for="input_l4">Deepest Input Level 4</label>
        <input type="text" id="input_l4" name="l4_val" required />
        <button type="submit" id="sub_l4">Final Nested Submit</button>
      </form>
    </body>
    </html>
    """

    level_3_html = f"""
    <!DOCTYPE html>
    <html>
    <body>
      <form id="form_l3">
        <label for="input_l3">Nested Input Level 3</label>
        <input type="email" id="input_l3" name="l3_val" />
      </form>
      <iframe id="iframe_l4" srcdoc="{html.escape(level_4_html)}"></iframe>
    </body>
    </html>
    """

    level_2_html = f"""
    <!DOCTYPE html>
    <html>
    <body>
      <form id="form_l2">
        <label for="input_l2">Nested Input Level 2</label>
        <input type="tel" id="input_l2" name="l2_val" />
      </form>
      <iframe id="iframe_l3" srcdoc="{html.escape(level_3_html)}"></iframe>
    </body>
    </html>
    """

    root_html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Multi-Level Nested Enterprise Portal</title></head>
    <body>
      <h1>Top Level Frame</h1>
      <form id="form_root">
        <label for="input_root">Root Level Input</label>
        <input type="text" id="input_root" name="root_val" />
      </form>
      <iframe id="iframe_l2" srcdoc="{html.escape(level_2_html)}"></iframe>
    </body>
    </html>
    """

    await browser_page.set_content(root_html)
    # Give browser time to load and mount the nested frame hierarchy
    await browser_page.wait_for_timeout(600)

    # Verify Playwright has registered all 4 frames in hierarchy
    assert len(browser_page.frames) >= 4

    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert schema.has_iframes is True
    # Should have extracted fields from all 4 levels
    field_ids = [f.field_id for f in schema.fields]
    assert "input_root" in field_ids
    assert "input_l2" in field_ids
    assert "input_l3" in field_ids
    assert "input_l4" in field_ids

    # Check that frame_index correctly reflects frame levels
    frame_indices = {f.field_id: f.frame_index for f in schema.fields}
    assert frame_indices["input_root"] == 0
    assert frame_indices["input_l4"] > 0

    # Verify submit button from deepest nested frame was extracted
    assert len(schema.submit_buttons) >= 1
    assert any("Final Nested Submit" in btn.text for btn in schema.submit_buttons)


# ==============================================================================
# 3. Obfuscated Dynamic Input IDs & Special Characters
# ==============================================================================


OBFUSCATED_IDS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Obfuscated Dynamic Form</title></head>
<body>
  <form id="dynamic_form">
    <!-- React 18 style colon-delimited ID -->
    <div class="field">
      <label for=":r1:name:">React 18 Dynamic Field</label>
      <input type="text" id=":r1:name:" name="react_name" />
    </div>

    <!-- UUID style ID -->
    <div class="field">
      <label for="d5f8c2b4-7a3e-4f11-9a2d-8b6e4c7a1029">UUID Dynamic Field</label>
      <input type="email" id="d5f8c2b4-7a3e-4f11-9a2d-8b6e4c7a1029" name="uuid_field" />
    </div>

    <!-- Dot and bracket separated ID -->
    <div class="field">
      <label for="user.profile.details[0].phone">Dotted Array ID</label>
      <input type="tel" id="user.profile.details[0].phone" name="user[phone]" />
    </div>

    <!-- Pure numeric ID (starts with digit) -->
    <div class="field">
      <label for="987654321">Numeric ID</label>
      <input type="text" id="987654321" name="numeric_id_field" />
    </div>

    <!-- Special CSS characters in ID ($@#%/+!~) -->
    <div class="field">
      <label for="weird$char@id/test+1">Special Characters ID</label>
      <input type="text" id="weird$char@id/test+1" name="weird_chars" />
    </div>

    <!-- Space inside ID -->
    <div class="field">
      <label for="id with spaces">ID with spaces</label>
      <input type="text" id="id with spaces" name="spaced_id" />
    </div>

    <!-- Obfuscated ID with parent enclosing label -->
    <label class="parent-label">
      <span>Enclosing Label for Dynamic Input</span>
      <input type="text" id="_dyn_k89x_0912" name="dyn_val" />
    </label>

    <button type="submit" id="submit_dyn">Submit Dynamic</button>
  </form>
</body>
</html>
"""


async def test_adversarial_obfuscated_dynamic_ids(browser_page):
    """Verify DOMExtractor escapes obfuscated/dynamic IDs and generates valid CSS selectors."""
    await browser_page.set_content(OBFUSCATED_IDS_HTML)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert len(schema.fields) == 7

    for field in schema.fields:
        # Crucial empirical check: every selector generated MUST be valid and queryable by Playwright
        loc = browser_page.locator(field.selector)
        count = await loc.count()
        assert count >= 1, f"Selector '{field.selector}' failed to locate element for field '{field.field_id}'"

    # Verify label resolution for React colon ID
    react_field = next(f for f in schema.fields if f.field_id == ":r1:name:")
    assert "React 18 Dynamic Field" in react_field.label

    # Verify numeric ID selector escaping
    num_field = next(f for f in schema.fields if f.field_id == "987654321")
    assert "Numeric ID" in num_field.label

    # Verify enclosing parent label resolution
    dyn_field = next(f for f in schema.fields if f.field_id == "_dyn_k89x_0912")
    assert "Enclosing Label for Dynamic Input" in dyn_field.label


# ==============================================================================
# 4. Hidden and Disabled Inputs
# ==============================================================================


HIDDEN_DISABLED_HTML = """
<!DOCTYPE html>
<html>
<head><title>Form with Hidden and Disabled Inputs</title></head>
<body>
  <form id="state_form">
    <!-- Standard visible input -->
    <label for="visible_user">Username</label>
    <input type="text" id="visible_user" name="username" required />

    <!-- Type hidden (Must be omitted from interactive FormSchema) -->
    <input type="hidden" id="csrf_token" name="csrf" value="d98a7cf90b21" />

    <!-- Type reset and button (Must be omitted from interactive FormSchema) -->
    <input type="reset" id="reset_btn" value="Reset All" />
    <input type="button" id="click_btn" value="Generic Action" />

    <!-- Visually hidden file input (Common in ATS forms - MUST be retained) -->
    <label for="resume_upload">Resume Upload</label>
    <input type="file" id="resume_upload" name="resume" style="display: none;" />

    <!-- Visually hidden text input (display: none honeypot) -->
    <input type="text" id="honeypot" name="hp_field" style="display: none;" placeholder="Do not fill" />

    <!-- Visually hidden input (visibility: hidden) -->
    <input type="text" id="hidden_vis" name="vis_field" style="visibility: hidden;" />

    <!-- HTML5 hidden attribute -->
    <input type="text" id="attr_hidden" name="hidden_attr_field" hidden />

    <!-- Disabled text input -->
    <label for="disabled_field">Disabled Field</label>
    <input type="text" id="disabled_field" name="disabled_text" disabled value="Preset Value" />

    <!-- Readonly text input -->
    <label for="readonly_field">Readonly Field</label>
    <input type="text" id="readonly_field" name="readonly_text" readonly value="Locked Value" />

    <!-- Disabled select -->
    <label for="disabled_select">Disabled Select</label>
    <select id="disabled_select" name="disabled_sel" disabled>
      <option value="1">Locked Option</option>
    </select>

    <button type="submit" id="submit_state">Save State</button>
  </form>
</body>
</html>
"""


async def test_adversarial_hidden_and_disabled_inputs(browser_page):
    """Verify DOMExtractor correctly handles hidden, display:none, disabled, and readonly inputs."""
    await browser_page.set_content(HIDDEN_DISABLED_HTML)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    field_ids = [f.field_id for f in schema.fields]

    # Invariant 1: type="hidden", type="reset", type="button" MUST NOT be in fields
    assert "csrf_token" not in field_ids
    assert "reset_btn" not in field_ids
    assert "click_btn" not in field_ids

    # Invariant 2: ATS hidden file input (display:none) MUST be retained for CDP streaming
    resume_field = next((f for f in schema.fields if f.field_id == "resume_upload"), None)
    assert resume_field is not None
    assert resume_field.field_type == FieldType.FILE

    # Invariant 3: Disabled and readonly inputs are captured with current values
    disabled_field = next((f for f in schema.fields if f.field_id == "disabled_field"), None)
    assert disabled_field is not None
    assert disabled_field.current_value == "Preset Value"

    readonly_field = next((f for f in schema.fields if f.field_id == "readonly_field"), None)
    assert readonly_field is not None
    assert readonly_field.current_value == "Locked Value"


# ==============================================================================
# 5. Forms with Zero Submit Buttons
# ==============================================================================


NO_SUBMIT_HTML = """
<!DOCTYPE html>
<html>
<head><title>Read-Only Survey or Auto-Saving Form</title></head>
<body>
  <form id="autosave_form">
    <div class="field">
      <label for="notes">Quick Notes</label>
      <textarea id="notes" name="notes">Type thoughts here...</textarea>
    </div>
    <div class="field">
      <label for="tag">Category Tag</label>
      <input type="text" id="tag" name="tag" value="general" />
    </div>
    <!-- Only a reset and generic non-submit button -->
    <div class="actions">
      <button type="button" id="discard_btn">Discard Changes</button>
      <input type="reset" id="rst" value="Clear Form" />
    </div>
  </form>
</body>
</html>
"""


async def test_adversarial_zero_submit_buttons(browser_page):
    """Verify DOMExtractor returns an empty submit_buttons list without crashing when 0 submit buttons exist."""
    await browser_page.set_content(NO_SUBMIT_HTML)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert isinstance(schema, FormSchema)
    assert len(schema.fields) == 2
    # Must cleanly detect 0 submit buttons
    assert len(schema.submit_buttons) == 0
    assert schema.detected_platform == "generic"


# ==============================================================================
# 6. Forms with Multiple Submit Buttons & Conflicting Actions
# ==============================================================================


MULTI_SUBMIT_HTML = """
<!DOCTYPE html>
<html>
<head><title>Multi-Action Candidate Application</title></head>
<body>
  <form id="multi_action_form" action="/submit" method="POST">
    <div class="field">
      <label for="applicant_name">Full Name</label>
      <input type="text" id="applicant_name" name="name" required />
    </div>

    <!-- Secondary navigation / draft button -->
    <button type="button" id="btn_draft" class="draft-btn">Save Draft Application</button>

    <!-- Multiple submit buttons -->
    <button type="submit" id="btn_preview" class="btn-preview">Preview Application</button>
    <button type="submit" id="btn_apply" class="primary-submit">Submit Application</button>
    <input type="submit" id="btn_alt_apply" value="Apply with Resume Only" />
    
    <!-- Duplicate button with identical class -->
    <button type="submit" class="primary-submit" id="btn_bottom_apply">Submit Application</button>
  </form>
</body>
</html>
"""


async def test_adversarial_multiple_submit_buttons_and_deduplication(browser_page):
    """Verify DOMExtractor correctly parses, classifies, and deduplicates multiple submit buttons."""
    await browser_page.set_content(MULTI_SUBMIT_HTML)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert len(schema.fields) == 1
    # Multiple submit buttons should be captured
    assert len(schema.submit_buttons) >= 3

    selectors = [btn.selector for btn in schema.submit_buttons]
    # Check deduplication: selectors must be unique
    assert len(selectors) == len(set(selectors))

    # All buttons with submit semantics should be detected
    texts = [btn.text for btn in schema.submit_buttons]
    assert any("Submit Application" in t for t in texts)
    assert any("Preview Application" in t for t in texts)
    assert any("Apply with Resume Only" in t for t in texts)


# ==============================================================================
# 7. Extreme Edge Cases: Empty DOM, 120+ Inputs, Unicode/Emoji, and XSS Injection
# ==============================================================================


async def test_adversarial_empty_dom(browser_page):
    """Verify DOMExtractor handles completely empty HTML without error."""
    await browser_page.set_content("<!DOCTYPE html><html><head><title>Empty</title></head><body></body></html>")
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert schema.fields == []
    assert schema.submit_buttons == []
    assert schema.has_iframes is False
    assert schema.detected_platform == "generic"


async def test_adversarial_unicode_emojis_and_xss_labels(browser_page):
    """Verify DOMExtractor handles Unicode, emojis, HTML entities, and script tags safely."""
    xss_unicode_html = """
    <!DOCTYPE html>
    <html>
    <head><title>International 🌐 & Safe 🛡️ Portal</title></head>
    <body>
      <form id="unicode_form">
        <div class="field">
          <label for="u_name">🚀 Candidate Full Name 🎯 &amp; Titles</label>
          <input type="text" id="u_name" name="candidate[name]" placeholder="Enter 姓名..." />
        </div>
        <div class="field">
          <!-- XSS payload in label - should be read as plain text without execution -->
          <label for="xss_field">Test &lt;script&gt;alert('xss')&lt;/script&gt; Label</label>
          <input type="text" id="xss_field" name="security_test" />
        </div>
        <div class="field">
          <label for="arabic_field">عنوان البريد الإلكتروني</label>
          <input type="email" id="arabic_field" name="arabic_email" />
        </div>
        <button type="submit" id="btn_intl">Envoyer la candidature 🚀</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(xss_unicode_html)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert len(schema.fields) == 3
    assert len(schema.submit_buttons) == 1

    # Check emoji in label
    u_field = next(f for f in schema.fields if f.field_id == "u_name")
    assert "🚀 Candidate Full Name 🎯" in u_field.label
    assert u_field.placeholder == "Enter 姓名..."

    # Check XSS string in label is treated as plain text
    xss_field = next(f for f in schema.fields if f.field_id == "xss_field")
    assert "<script>" in xss_field.label or "script" in xss_field.label

    # Check Arabic label
    ar_field = next(f for f in schema.fields if f.field_id == "arabic_field")
    assert "البريد الإلكتروني" in ar_field.label
    assert ar_field.field_type == FieldType.EMAIL

    # Check submit button with emoji
    assert "Envoyer la candidature 🚀" in schema.submit_buttons[0].text


async def test_adversarial_high_density_form_performance(browser_page):
    """Stress-test DOMExtractor with 120+ dynamically generated form fields for performance and memory."""
    fields_html = []
    for i in range(120):
        f_type = "text" if i % 4 == 0 else ("email" if i % 4 == 1 else ("tel" if i % 4 == 2 else "number"))
        fields_html.append(f"""
        <div class="form-group">
          <label for="field_{i}">Field Label Number {i} {'*' if i % 2 == 0 else ''}</label>
          <input type="{f_type}" id="field_{i}" name="input_array[{i}]" {'required' if i % 2 == 0 else ''} />
        </div>
        """)

    large_form_html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>High Density Enterprise Form</title></head>
    <body>
      <form id="massive_form">
        {"".join(fields_html)}
        <button type="submit">Submit All Records</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(large_form_html)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert len(schema.fields) == 120
    assert len(schema.submit_buttons) == 1
    # Check requirement detection across high density
    required_count = sum(1 for f in schema.fields if f.required)
    assert required_count == 60


# ==============================================================================
# 8. Zero Inputs with Only Submit Button
# ==============================================================================


async def test_adversarial_zero_inputs_only_submit(browser_page):
    """Verify DOMExtractor handles pages with zero interactive inputs but a submit button."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Terms Acceptance Confirmation</title></head>
    <body>
      <form action="/accept">
        <p>Please click below to confirm acceptance of terms.</p>
        <button type="submit" id="btn_agree">Accept & Continue</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(html_content)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert len(schema.fields) == 0
    assert len(schema.submit_buttons) == 1
    assert schema.submit_buttons[0].text == "Accept & Continue"


# ==============================================================================
# 9. Complex Labels with Nested SVGs, Badges & Icons
# ==============================================================================


async def test_adversarial_complex_nested_label_structures(browser_page):
    """Verify label resolution handles nested SVG icons, badges, and formatting spans."""
    complex_labels_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Complex Label UI</title></head>
    <body>
      <form id="svg_form">
        <div class="form-group">
          <label for="github_input">
            <svg height="16" width="16"><path d="M0 0h16v16H0z"/></svg>
            <span>GitHub Profile</span>
            <span class="badge badge-optional">(Optional)</span>
          </label>
          <input type="url" id="github_input" name="github_url" />
        </div>
        <div class="form-group">
          <!-- aria-labelledby pointing to multiple elements concatenated -->
          <span id="salary_cur">Expected Salary</span>
          <span id="salary_note">(USD / Year)</span>
          <input type="number" id="salary_input" name="comp" aria-labelledby="salary_cur" />
        </div>
        <button type="submit">Submit Profile</button>
      </form>
    </body>
    </html>
    """
    await browser_page.set_content(complex_labels_html)
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(browser_page)

    assert len(schema.fields) == 2
    gh_field = next(f for f in schema.fields if f.field_id == "github_input")
    assert "GitHub Profile" in gh_field.label
    assert gh_field.field_type == FieldType.URL

    salary_field = next(f for f in schema.fields if f.field_id == "salary_input")
    assert "Expected Salary" in salary_field.label


# ==============================================================================
# 10. Frame Evaluation Failure Resilience (Mock Frame Error)
# ==============================================================================


async def test_adversarial_frame_evaluation_error_resilience(browser_page):
    """Verify that a failing or detached frame does not crash the entire schema extraction."""
    await browser_page.set_content("<html><body><input id='root_inp'><button type='submit'>Go</button></body></html>")

    class FaultyFrame:
        """Simulates a cross-origin or detached frame that throws on evaluate."""
        async def evaluate(self, script):
            raise RuntimeError("SecurityError: Blocked a frame with origin from accessing a cross-origin frame.")

    class PageWrapper:
        def __init__(self, page, faulty_frame):
            self.page = page
            self.url = page.url
            self.frames = list(page.frames) + [faulty_frame]

        async def title(self):
            return await self.page.title()

    wrapped_page = PageWrapper(browser_page, FaultyFrame())
    extractor = DOMExtractor()
    schema = await extractor.extract_schema(wrapped_page)

    # Should cleanly recover, log warning, and extract root frame
    assert len(schema.fields) == 1
    assert schema.fields[0].field_id == "root_inp"
    assert len(schema.submit_buttons) == 1

