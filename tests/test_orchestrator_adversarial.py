"""Adversarial stress-testing suite for UltramarineClient and FillOrchestrator.

Milestone M3 Empirical Adversary:
1. Malformed DOM Schemas (empty fields, missing selectors, unrecognized types, extreme URLs).
2. Remote API Failure, Timeout, & Fallback (timeouts, HTTP 5xx, HTTP 429, malformed/non-JSON, schema mismatches).
3. CIBA Consent Denial & Timeout Refusal Invariance (dry_run=True, dry_run=False, expired, timeout, unapproved).
4. Session Release Guarantees in Finally Blocks (errors during init, extraction, reasoning, CIBA, filling).
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
import pytest
from playwright.async_api import async_playwright

from app.core.auth0_client import Auth0CIBAClient
from app.core.ultramarine_client import UltramarineClient
from app.core.vault import VaultManager, create_sample_profile
from app.models.browser_schema import (
    FieldType,
    FormField,
    FormSchema,
    SubmitButton,
)
from app.models.ciba_schema import (
    ConsentResult,
    RefusalToSubmitError,
)
from app.services.browserbase_service import BrowserbaseService
from app.services.dom_extractor import DOMExtractor
from app.services.fill_orchestrator import FillOrchestrator
from app.services.form_filler import FormFiller


@pytest.fixture
async def browser_page():
    """Provides a fresh isolated Playwright page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        yield page
        await browser.close()


@pytest.fixture
def sample_profile():
    return create_sample_profile()


@pytest.fixture
def temp_vault(tmp_path):
    vault_file = str(tmp_path / "adversarial_vault.enc")
    mgr = VaultManager(vault_path=vault_file, vault_key="adversarial_test_secret_32bytes!")
    profile = create_sample_profile()
    mgr.save_profile(profile)
    return mgr


TEST_HTML_WITH_MONITOR = """
<!DOCTYPE html>
<html>
<head><title>Adversarial Test Form</title></head>
<body>
  <h1>Adversarial Form Target</h1>
  <form id="adv_form" action="/submit" method="POST" onsubmit="window.__submitted = true; event.preventDefault(); return false;">
    <label for="name">Name</label>
    <input type="text" id="name" name="name" />
    <label for="email">Email</label>
    <input type="email" id="email" name="email" />
    <button type="submit" id="submit_btn">Submit</button>
  </form>
</body>
</html>
"""


# ==============================================================================
# Suite 1: Malformed DOM Schemas (UltramarineClient & FillOrchestrator)
# ==============================================================================

class TestMalformedDOMSchemas:
    """Stress-test UltramarineClient and FillOrchestrator with malformed DOM schemas."""

    @pytest.mark.asyncio
    async def test_empty_dom_schema_generates_empty_plan_and_orchestrator_succeeds(
        self, browser_page, temp_vault
    ):
        """Empty fields list produces valid FillPlan with items=[] and orchestrator completes."""
        client = UltramarineClient(offline_mode=True)
        empty_schema = FormSchema(
            url="https://example.com/empty",
            page_title="Empty Application",
            fields=[],
            submit_buttons=[],
        )
        plan = await client.generate_fill_plan(empty_schema, temp_vault.get_profile())
        assert plan.target_url == "https://example.com/empty"
        assert plan.items == []

        # Run orchestrator with empty schema
        ciba = Auth0CIBAClient(offline_mode=True)
        orchestrator = FillOrchestrator(
            vault_manager=temp_vault,
            ciba_client=ciba,
            browserbase_service=BrowserbaseService(offline=True),
            ultramarine_client=client,
            auto_approve_ciba=True,
        )
        result = await orchestrator.run(
            target_url="https://example.com/empty",
            dry_run=True,
            html_override="<html><body><p>No interactive inputs</p></body></html>",
        )
        assert result.status == "DRY_RUN_SUCCESS"
        assert result.fields_filled_count == 0

    @pytest.mark.asyncio
    async def test_malformed_selectors_in_schema(self, browser_page, temp_vault):
        """Bizarre or invalid CSS selectors in schema are handled without crashing."""
        client = UltramarineClient(offline_mode=True)
        malformed_schema = FormSchema(
            url="https://example.com/malformed-selectors",
            page_title="Malformed Selectors",
            fields=[
                FormField(
                    field_id="first_name",
                    selector=":::invalid-selector:::",
                    field_type=FieldType.TEXT,
                    label="First Name",
                ),
                FormField(
                    field_id="last_name",
                    selector="[unclosed-bracket",
                    field_type=FieldType.TEXT,
                    label="Last Name",
                ),
                FormField(
                    field_id="email",
                    selector="",
                    field_type=FieldType.EMAIL,
                    label="Email",
                ),
            ],
            submit_buttons=[SubmitButton(selector="#submit", text="Submit")],
        )

        plan = await client.generate_fill_plan(malformed_schema, temp_vault.get_profile())
        assert len(plan.items) >= 2

        # FormFiller must tolerate invalid selectors without throwing unhandled exceptions
        await browser_page.set_content(TEST_HTML_WITH_MONITOR)
        filler = FormFiller()
        fill_result = await filler.fill(page=browser_page, fill_plan=plan, dry_run=True)
        assert fill_result is not None
        assert fill_result.status == "DRY_RUN_SUCCESS"

    @pytest.mark.asyncio
    async def test_unrecognized_field_types_and_missing_attributes(self, temp_vault):
        """Fields with empty IDs, missing labels, and unhandled field types skip gracefully."""
        client = UltramarineClient(offline_mode=True)
        weird_schema = FormSchema(
            url="https://example.com/unrecognized",
            page_title="Weird Fields",
            fields=[
                FormField(
                    field_id="",
                    selector="#blank_id",
                    field_type=FieldType.NUMBER,
                    label="",
                ),
                FormField(
                    field_id="custom_numeric_metric",
                    selector="#metric",
                    field_type=FieldType.NUMBER,
                    label="Unknown numeric statistic",
                ),
                FormField(
                    field_id="empty_select",
                    selector="#empty_select",
                    field_type=FieldType.SELECT,
                    label="Choose Option",
                    options=[],
                ),
            ],
        )

        plan = await client.generate_fill_plan(weird_schema, temp_vault.get_profile())
        assert plan is not None
        assert isinstance(plan.items, list)

    @pytest.mark.parametrize(
        "extreme_url",
        [
            "",
            "about:blank",
            "javascript:void(0)",
            "https://example.com/jobs/apply?role=Staff%20Architect&query=🚀&source='--",
            "http://127.0.0.1:99999/invalid/port",
            "https://sub.domain.corp.internal/w-8ben#section-6?p=1&q=2",
        ],
    )
    def test_session_id_computation_under_extreme_urls(self, extreme_url):
        """Deterministic session ID generation survives empty, unicode, and extreme URLs."""
        sess_id = UltramarineClient.compute_session_id(extreme_url)
        assert sess_id.startswith("sess_")
        assert len(sess_id) == 17  # "sess_" (5) + 12 hex chars

    @pytest.mark.asyncio
    async def test_massive_dom_schema_performance_and_stability(self, temp_vault):
        """A schema with 500 fields does not trigger recursion or memory exhaustion."""
        fields = [
            FormField(
                field_id=f"field_{i}",
                selector=f"#input_{i}",
                field_type=FieldType.TEXT if i % 2 == 0 else FieldType.TEXTAREA,
                label=f"Question {i} about technical experience",
            )
            for i in range(500)
        ]
        massive_schema = FormSchema(
            url="https://example.com/massive-form",
            page_title="Massive 500-Field Form",
            fields=fields,
        )

        client = UltramarineClient(offline_mode=True)
        plan = await client.generate_fill_plan(massive_schema, temp_vault.get_profile())
        assert plan is not None
        assert len(plan.items) >= 200


# ==============================================================================
# Suite 2: Remote API Failure, Timeout, & Fallback (UltramarineClient)
# ==============================================================================

class TestRemoteAPIFailuresAndTimeouts:
    """Stress-test UltramarineClient remote API error resilience and fallback activation."""

    @pytest.mark.asyncio
    async def test_api_timeout_triggers_heuristic_fallback(self, temp_vault):
        """Read/connect timeout from Ultramarine API triggers offline heuristic fallback."""
        mock_openai = MagicMock()
        mock_completions = AsyncMock()
        mock_completions.create.side_effect = asyncio.TimeoutError("Paper Instruments read timeout after 30.0s")
        mock_openai.chat.completions = mock_completions

        client = UltramarineClient(api_key="pi_live_test_key", offline_mode=False)
        client.client = mock_openai

        schema = FormSchema(
            url="https://boards.greenhouse.io/stripe/jobs/123",
            page_title="Stripe Job Application",
            fields=[
                FormField(field_id="first_name", selector="#first_name", field_type=FieldType.TEXT, label="First Name"),
                FormField(field_id="email", selector="#email", field_type=FieldType.EMAIL, label="Email"),
            ],
        )

        plan = await client.generate_fill_plan(schema, temp_vault.get_profile())
        assert plan is not None
        assert len(plan.items) == 2
        assert plan.items[0].value == "Arjun"
        assert plan.items[1].value == temp_vault.get_profile().core.email

    @pytest.mark.parametrize(
        "api_exception",
        [
            RuntimeError("HTTP 500 Internal Server Error"),
            RuntimeError("HTTP 502 Bad Gateway"),
            RuntimeError("HTTP 503 Service Unavailable"),
            RuntimeError("HTTP 504 Gateway Timeout"),
            RuntimeError("HTTP 429 Too Many Requests: Rate limit exceeded"),
            ConnectionResetError("Connection reset by peer"),
        ],
    )
    @pytest.mark.asyncio
    async def test_api_server_and_rate_limit_errors_fallback(self, temp_vault, api_exception):
        """API server errors (5xx) and rate limiting (429) cleanly activate heuristic fallback."""
        mock_openai = MagicMock()
        mock_completions = AsyncMock()
        mock_completions.create.side_effect = api_exception
        mock_openai.chat.completions = mock_completions

        client = UltramarineClient(api_key="pi_live_test_key", offline_mode=False)
        client.client = mock_openai

        schema = FormSchema(
            url="https://boards.greenhouse.io/stripe/jobs/123",
            page_title="Job",
            fields=[
                FormField(field_id="first_name", selector="#first_name", field_type=FieldType.TEXT, label="First Name")
            ],
        )

        plan = await client.generate_fill_plan(schema, temp_vault.get_profile())
        assert plan is not None
        assert len(plan.items) == 1
        assert plan.items[0].value == "Arjun"

    @pytest.mark.parametrize(
        "malformed_content",
        [
            "<html><body>502 Bad Gateway</body></html>",
            "",
            "   \n\t  ",
            "{\"target_url\": \"https://example.com\", \"items\": [",  # Truncated JSON
            "Here is your completed fill plan: {\"target_url\": ...",  # Unparsed commentary
            "null",
            "42",
            "true",
            "[\"list\", \"instead\", \"of\", \"dict\"]",
        ],
    )
    @pytest.mark.asyncio
    async def test_api_malformed_and_non_json_responses_fallback(self, temp_vault, malformed_content):
        """Malformed, HTML, truncated, or non-object JSON triggers fallback without crashing."""
        mock_openai = MagicMock()
        mock_completions = AsyncMock()

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = malformed_content
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_completions.create.return_value = mock_response
        mock_openai.chat.completions = mock_completions

        client = UltramarineClient(api_key="pi_live_test_key", offline_mode=False)
        client.client = mock_openai

        schema = FormSchema(
            url="https://boards.greenhouse.io/stripe/jobs/123",
            page_title="Job",
            fields=[
                FormField(field_id="first_name", selector="#first_name", field_type=FieldType.TEXT, label="First Name")
            ],
        )

        plan = await client.generate_fill_plan(schema, temp_vault.get_profile())
        assert plan is not None
        assert len(plan.items) == 1
        assert plan.items[0].value == "Arjun"

    @pytest.mark.asyncio
    async def test_api_invalid_pydantic_schema_triggers_fallback(self, temp_vault):
        """API responses containing invalid field types or invalid items fail validation and fallback."""
        mock_openai = MagicMock()
        mock_completions = AsyncMock()

        # Payload has unrecognized field_type
        bad_pydantic_payload = {
            "target_url": "https://boards.greenhouse.io/stripe/jobs/123",
            "items": [
                {
                    "field_id": "name",
                    "selector": "#name",
                    "field_type": "QUANTUM_TELEPORT_FIELD",  # Invalid enum value
                    "value": "Arjun",
                }
            ],
        }

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps(bad_pydantic_payload)
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_completions.create.return_value = mock_response
        mock_openai.chat.completions = mock_completions

        client = UltramarineClient(api_key="pi_live_test_key", offline_mode=False)
        client.client = mock_openai

        schema = FormSchema(
            url="https://boards.greenhouse.io/stripe/jobs/123",
            page_title="Job",
            fields=[
                FormField(field_id="first_name", selector="#first_name", field_type=FieldType.TEXT, label="First Name")
            ],
        )

        plan = await client.generate_fill_plan(schema, temp_vault.get_profile())
        assert plan is not None
        # Heuristic fallback returned valid text field item
        assert plan.items[0].field_type == FieldType.TEXT


# ==============================================================================
# Suite 3: CIBA Consent Denial & Timeout Refusal Invariance (FillOrchestrator)
# ==============================================================================

class TestCIBARefusalInvariance:
    """Stress-test CIBA consent denial and timeout refusal invariance in FillOrchestrator."""

    @pytest.mark.asyncio
    async def test_ciba_denial_refusal_invariant_dry_run_true(self, browser_page, temp_vault):
        """When CIBA consent is rejected in dry-run mode, RefusalToSubmitError is raised and form is NOT submitted."""
        await browser_page.set_content(TEST_HTML_WITH_MONITOR)

        ciba = Auth0CIBAClient(offline_mode=True)
        # Force refusal on initiation
        orig_initiate = ciba.initiate_consent

        async def _deny_on_init(*args, **kwargs):
            req = await orig_initiate(*args, **kwargs)
            ciba.simulate_denial(req.auth_req_id)
            return req

        ciba.initiate_consent = _deny_on_init

        orchestrator = FillOrchestrator(
            vault_manager=temp_vault,
            ciba_client=ciba,
            browserbase_service=BrowserbaseService(offline=True),
            ultramarine_client=UltramarineClient(offline_mode=True),
            auto_approve_ciba=False,
        )

        with pytest.raises(RefusalToSubmitError) as exc_info:
            await orchestrator.run(
                target_url="https://example.com/apply",
                dry_run=True,
                page=browser_page,
            )

        assert "access_denied" in str(exc_info.value).lower() or "refused" in str(exc_info.value).lower()
        # Form was never submitted
        is_sub = await browser_page.evaluate("() => Boolean(window.__submitted)")
        assert is_sub is False

    @pytest.mark.asyncio
    async def test_ciba_denial_refusal_invariant_dry_run_false(self, browser_page, temp_vault):
        """CRITICAL: In live mode (dry_run=False), CIBA rejection MUST abort submission completely."""
        await browser_page.set_content(TEST_HTML_WITH_MONITOR)

        ciba = Auth0CIBAClient(offline_mode=True)
        orig_initiate = ciba.initiate_consent

        async def _deny_on_init(*args, **kwargs):
            req = await orig_initiate(*args, **kwargs)
            ciba.simulate_denial(req.auth_req_id)
            return req

        ciba.initiate_consent = _deny_on_init

        orchestrator = FillOrchestrator(
            vault_manager=temp_vault,
            ciba_client=ciba,
            browserbase_service=BrowserbaseService(offline=True),
            ultramarine_client=UltramarineClient(offline_mode=True),
            auto_approve_ciba=False,
        )

        with pytest.raises(RefusalToSubmitError):
            await orchestrator.run(
                target_url="https://example.com/apply",
                dry_run=False,  # LIVE SUBMISSION MODE
                page=browser_page,
            )

        # Invariant check: In live mode, form MUST NOT be submitted when CIBA is denied
        is_sub = await browser_page.evaluate("() => Boolean(window.__submitted)")
        assert is_sub is False

    @pytest.mark.asyncio
    async def test_ciba_expiration_refusal_invariant(self, browser_page, temp_vault):
        """Expired CIBA auth request raises RefusalToSubmitError."""
        await browser_page.set_content(TEST_HTML_WITH_MONITOR)

        ciba = Auth0CIBAClient(offline_mode=True)
        orig_initiate = ciba.initiate_consent

        async def _expire_on_init(*args, **kwargs):
            req = await orig_initiate(*args, **kwargs)
            ciba.simulate_expiration(req.auth_req_id)
            return req

        ciba.initiate_consent = _expire_on_init

        orchestrator = FillOrchestrator(
            vault_manager=temp_vault,
            ciba_client=ciba,
            browserbase_service=BrowserbaseService(offline=True),
            ultramarine_client=UltramarineClient(offline_mode=True),
            auto_approve_ciba=False,
        )

        with pytest.raises(RefusalToSubmitError) as exc_info:
            await orchestrator.run(
                target_url="https://example.com/apply",
                dry_run=False,
                page=browser_page,
            )

        assert "expired" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_ciba_unapproved_result_raises_refusal(self, browser_page, temp_vault):
        """If poll_consent returns approved=False without raising directly, orchestrator raises RefusalToSubmitError."""
        await browser_page.set_content(TEST_HTML_WITH_MONITOR)

        mock_ciba = MagicMock()
        mock_ciba.initiate_consent = AsyncMock(
            return_value=MagicMock(auth_req_id="mock_req_123")
        )
        mock_ciba.poll_consent = AsyncMock(
            return_value=ConsentResult(approved=False, error="Biometric validation failed on device")
        )

        orchestrator = FillOrchestrator(
            vault_manager=temp_vault,
            ciba_client=mock_ciba,
            browserbase_service=BrowserbaseService(offline=True),
            ultramarine_client=UltramarineClient(offline_mode=True),
        )

        with pytest.raises(RefusalToSubmitError) as exc_info:
            await orchestrator.run(
                target_url="https://example.com/apply",
                dry_run=False,
                page=browser_page,
            )

        assert "Biometric validation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_ciba_failure_halts_before_form_filling_stage(self, browser_page, temp_vault):
        """Stages FORM_FILLING (90%) and COMPLETED (100%) are NEVER reported if CIBA fails."""
        await browser_page.set_content(TEST_HTML_WITH_MONITOR)

        ciba = Auth0CIBAClient(offline_mode=True)
        orig_initiate = ciba.initiate_consent

        async def _deny(*args, **kwargs):
            req = await orig_initiate(*args, **kwargs)
            ciba.simulate_denial(req.auth_req_id)
            return req

        ciba.initiate_consent = _deny

        stages = []
        def telemetry(stage, pct):
            stages.append((stage, pct))

        orchestrator = FillOrchestrator(
            vault_manager=temp_vault,
            ciba_client=ciba,
            browserbase_service=BrowserbaseService(offline=True),
            ultramarine_client=UltramarineClient(offline_mode=True),
        )

        with pytest.raises(RefusalToSubmitError):
            await orchestrator.run(
                target_url="https://example.com/apply",
                dry_run=True,
                page=browser_page,
                progress_callback=telemetry,
            )

        # Verify stages terminated at CIBA_CONSENT
        stage_names = [s[0] for s in stages]
        assert "SESSION_INIT" in stage_names
        assert "DOM_EXTRACTION" in stage_names
        assert "AI_REASONING" in stage_names
        assert "CIBA_CONSENT" in stage_names
        assert "FORM_FILLING" not in stage_names
        assert "COMPLETED" not in stage_names


# ==============================================================================
# Suite 4: Session Release Guarantee in Finally Blocks (FillOrchestrator)
# ==============================================================================

class TestSessionReleaseGuarantee:
    """Stress-test Browserbase session release guarantee under injected errors across all pipeline stages."""

    @pytest.mark.asyncio
    async def test_session_released_on_dom_extraction_error(self):
        """Unexpected exception in DOM extraction still releases Browserbase session."""
        bb = BrowserbaseService(offline=True)
        released = []
        orig_release = bb.release_session
        bb.release_session = lambda s: (released.append(s), orig_release(s))[1]

        extractor = DOMExtractor()
        extractor.extract_schema = MagicMock(side_effect=RuntimeError("DOM parser crashed unexpectedly"))

        orchestrator = FillOrchestrator(
            browserbase_service=bb,
            dom_extractor=extractor,
            ciba_client=Auth0CIBAClient(offline_mode=True),
            auto_approve_ciba=True,
        )

        with pytest.raises(RuntimeError) as exc_info:
            await orchestrator.run(
                target_url="https://example.com/test",
                dry_run=True,
                html_override="<html><body></body></html>",
            )

        assert "DOM parser crashed" in str(exc_info.value)
        assert len(released) == 1, "Browserbase session was NOT released when DOM extraction failed!"

    @pytest.mark.asyncio
    async def test_session_released_on_ai_reasoning_error(self):
        """Unexpected exception in AI reasoning still releases Browserbase session."""
        bb = BrowserbaseService(offline=True)
        released = []
        orig_release = bb.release_session
        bb.release_session = lambda s: (released.append(s), orig_release(s))[1]

        mock_ultramarine = MagicMock()
        mock_ultramarine.generate_fill_plan = AsyncMock(side_effect=ValueError("Unhandled model exception"))

        orchestrator = FillOrchestrator(
            browserbase_service=bb,
            ultramarine_client=mock_ultramarine,
            ciba_client=Auth0CIBAClient(offline_mode=True),
            auto_approve_ciba=True,
        )

        with pytest.raises(ValueError) as exc_info:
            await orchestrator.run(
                target_url="https://example.com/test",
                dry_run=True,
                html_override="<html><body></body></html>",
            )

        assert "Unhandled model exception" in str(exc_info.value)
        assert len(released) == 1, "Browserbase session was NOT released when AI reasoning failed!"

    @pytest.mark.asyncio
    async def test_session_released_on_ciba_denial_or_timeout(self):
        """CIBA consent denial or expiration still releases Browserbase cloud session."""
        bb = BrowserbaseService(offline=True)
        released = []
        orig_release = bb.release_session
        bb.release_session = lambda s: (released.append(s), orig_release(s))[1]

        ciba = Auth0CIBAClient(offline_mode=True)
        orig_initiate = ciba.initiate_consent

        async def _deny(*args, **kwargs):
            req = await orig_initiate(*args, **kwargs)
            ciba.simulate_denial(req.auth_req_id)
            return req

        ciba.initiate_consent = _deny

        orchestrator = FillOrchestrator(
            browserbase_service=bb,
            ciba_client=ciba,
            ultramarine_client=UltramarineClient(offline_mode=True),
            auto_approve_ciba=False,
        )

        with pytest.raises(RefusalToSubmitError):
            await orchestrator.run(
                target_url="https://example.com/test",
                dry_run=True,
                html_override="<html><body></body></html>",
            )

        assert len(released) == 1, "Browserbase session was NOT released when CIBA consent was denied!"

    @pytest.mark.asyncio
    async def test_session_released_on_form_filling_error(self):
        """Unexpected exception in FormFiller still releases Browserbase session."""
        bb = BrowserbaseService(offline=True)
        released = []
        orig_release = bb.release_session
        bb.release_session = lambda s: (released.append(s), orig_release(s))[1]

        mock_filler = MagicMock()
        mock_filler.fill = AsyncMock(side_effect=RuntimeError("CDP connection lost during form fill"))

        orchestrator = FillOrchestrator(
            browserbase_service=bb,
            form_filler=mock_filler,
            ciba_client=Auth0CIBAClient(offline_mode=True),
            ultramarine_client=UltramarineClient(offline_mode=True),
            auto_approve_ciba=True,
        )

        with pytest.raises(RuntimeError) as exc_info:
            await orchestrator.run(
                target_url="https://example.com/test",
                dry_run=True,
                html_override="<html><body></body></html>",
            )

        assert "CDP connection lost" in str(exc_info.value)
        assert len(released) == 1, "Browserbase session was NOT released when form filling failed!"

    @pytest.mark.asyncio
    async def test_session_release_handles_release_api_exception(self):
        """If release_session raises an exception, it does not mask the original exception."""
        bb = BrowserbaseService(offline=True)
        bb.release_session = MagicMock(side_effect=RuntimeError("Cloud API 500 when releasing session"))

        mock_filler = MagicMock()
        mock_filler.fill = AsyncMock(side_effect=ValueError("Original filling error"))

        orchestrator = FillOrchestrator(
            browserbase_service=bb,
            form_filler=mock_filler,
            ciba_client=Auth0CIBAClient(offline_mode=True),
            auto_approve_ciba=True,
        )

        # Original error should still be raised, not masked by release_session error
        with pytest.raises(ValueError) as exc_info:
            await orchestrator.run(
                target_url="https://example.com/test",
                dry_run=True,
                html_override="<html><body></body></html>",
            )

        assert "Original filling error" in str(exc_info.value)
