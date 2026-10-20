"""Unit and integration tests for Ultramarine 1 Flash client, sticky caching, and reasoning."""

import hashlib
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.ultramarine_client import UltramarineClient
from app.core.vault import create_sample_profile
from app.models.browser_schema import (
    FieldType,
    FillPlan,
    FormField,
    FormSchema,
    SubmitButton,
)


@pytest.fixture
def sample_profile():
    return create_sample_profile()


@pytest.fixture
def greenhouse_schema():
    return FormSchema(
        url="https://boards.greenhouse.io/anthropic/jobs/4012345",
        page_title="Anthropic Job Application - Research Engineer",
        detected_platform="greenhouse",
        fields=[
            FormField(
                field_id="first_name",
                selector="#first_name",
                field_type=FieldType.TEXT,
                label="First Name *",
                required=True,
            ),
            FormField(
                field_id="last_name",
                selector="#last_name",
                field_type=FieldType.TEXT,
                label="Last Name *",
                required=True,
            ),
            FormField(
                field_id="email",
                selector="#email",
                field_type=FieldType.EMAIL,
                label="Email *",
                required=True,
            ),
            FormField(
                field_id="phone",
                selector="#phone",
                field_type=FieldType.TEL,
                label="Phone *",
                required=True,
            ),
            FormField(
                field_id="resume",
                selector="#resume",
                field_type=FieldType.FILE,
                label="Resume/CV *",
                required=True,
            ),
            FormField(
                field_id="job_application_answers_attributes_0_text_value",
                selector="#job_application_answers_attributes_0_text_value",
                field_type=FieldType.URL,
                label="LinkedIn Profile",
                name_attr="job_application[answers_attributes][0][text_value]",
            ),
            FormField(
                field_id="job_application_answers_attributes_1_text_value",
                selector="#job_application_answers_attributes_1_text_value",
                field_type=FieldType.URL,
                label="GitHub URL",
                name_attr="job_application[answers_attributes][1][text_value]",
            ),
            FormField(
                field_id="essay_distributed_systems",
                selector="#essay_distributed_systems",
                field_type=FieldType.TEXTAREA,
                label="Describe a challenging distributed systems problem you solved",
                required=True,
            ),
        ],
        submit_buttons=[
            SubmitButton(selector="#submit_app", text="Submit Application", is_primary=True)
        ],
    )


@pytest.fixture
def w8ben_schema():
    return FormSchema(
        url="https://compliance.contractor.io/w8ben",
        page_title="Certificate of Foreign Status of Beneficial Owner (Form W-8BEN)",
        detected_platform="w8ben",
        fields=[
            FormField(
                field_id="line1_name",
                selector="#line1_name",
                field_type=FieldType.TEXT,
                label="1. Name of individual who is the beneficial owner",
                required=True,
            ),
            FormField(
                field_id="line2_country",
                selector="#line2_country",
                field_type=FieldType.TEXT,
                label="2. Country of citizenship",
                required=True,
            ),
            FormField(
                field_id="line3_address",
                selector="#line3_address",
                field_type=FieldType.TEXT,
                label="3. Permanent residence address (street, apt. or suite no., or rural route)",
                required=True,
            ),
            FormField(
                field_id="line3_city",
                selector="#line3_city",
                field_type=FieldType.TEXT,
                label="City or town, state or province. Include postal code where appropriate.",
                required=True,
            ),
            FormField(
                field_id="line6a_ftin",
                selector="#line6a_ftin",
                field_type=FieldType.TEXT,
                label="6a. Foreign tax identifying number",
                required=True,
            ),
            FormField(
                field_id="line6b_no_ftin",
                selector="#line6b_no_ftin",
                field_type=FieldType.CHECKBOX,
                label="6b. Check if FTIN not legally required",
                required=False,
            ),
            FormField(
                field_id="line8_dob",
                selector="#line8_dob",
                field_type=FieldType.DATE,
                label="8. Date of birth (MM-DD-YYYY)",
                required=True,
            ),
            FormField(
                field_id="line9_country",
                selector="#line9_country",
                field_type=FieldType.TEXT,
                label="9. I certify that the beneficial owner is a resident of country",
                required=True,
            ),
            FormField(
                field_id="line10_article",
                selector="#line10_article",
                field_type=FieldType.TEXT,
                label="10. Special rates and conditions: Article and paragraph",
                required=True,
            ),
            FormField(
                field_id="line10_rate",
                selector="#line10_rate",
                field_type=FieldType.TEXT,
                label="Rate of withholding claimed (%)",
                required=True,
            ),
            FormField(
                field_id="line10_income_type",
                selector="#line10_income_type",
                field_type=FieldType.TEXT,
                label="Type of income",
                required=True,
            ),
            FormField(
                field_id="line10_explanation",
                selector="#line10_explanation",
                field_type=FieldType.TEXTAREA,
                label="Explain the additional conditions in the Article the beneficial owner meets",
                required=True,
            ),
            FormField(
                field_id="signature",
                selector="#signature",
                field_type=FieldType.TEXT,
                label="Sign Here: Full Name",
                required=True,
            ),
            FormField(
                field_id="capacity",
                selector="#capacity",
                field_type=FieldType.TEXT,
                label="Capacity in which acting",
                required=True,
            ),
        ],
        submit_buttons=[
            SubmitButton(selector="#submit_w8ben", text="Submit Form W-8BEN", is_primary=True)
        ],
    )


def test_ultramarine_client_init_and_config():
    """Verify UltramarineClient initialization, defaults, and offline detection."""
    client = UltramarineClient(api_key="pi_live_dummy", offline_mode=True)
    assert client.offline_mode is True
    assert client.model == "ultramarine-1-flash"
    assert client.base_url == "https://api.paperinstruments.com/v1"
    assert client.client is None


def test_sticky_caching_session_id_computation():
    """Verify deterministic session ID hashing (sess_{sha256(url)[:12]})."""
    url1 = "https://boards.greenhouse.io/stripe/jobs/123456"
    url2 = "https://boards.greenhouse.io/stripe/jobs/789012"

    sess1_a = UltramarineClient.compute_session_id(url1)
    sess1_b = UltramarineClient.compute_session_id(url1)
    sess2 = UltramarineClient.compute_session_id(url2)

    expected_sha1 = hashlib.sha256(url1.encode("utf-8")).hexdigest()[:12]
    assert sess1_a == f"sess_{expected_sha1}"
    assert sess1_a == sess1_b  # Determinism
    assert sess1_a != sess2    # Distinctness


def test_prompt_construction(greenhouse_schema, sample_profile):
    """Verify system prompt and serialized user content construction."""
    client = UltramarineClient(offline_mode=True)
    sys_prompt = client.build_system_prompt()
    user_prompt = client.build_user_prompt(greenhouse_schema, sample_profile)

    # System prompt assertions
    assert "Paper Instruments Ultramarine 1 Flash" in sys_prompt
    assert "Ground Truth Invariant" in sys_prompt
    assert "IRS Form W-8BEN Tax Rules" in sys_prompt
    assert "Article 12(2)" in sys_prompt
    assert "15% withholding rate" in sys_prompt
    assert "FillPlan" in sys_prompt

    # User prompt assertions
    user_data = json.loads(user_prompt)
    assert "target_form" in user_data
    assert "candidate_profile" in user_data
    assert user_data["candidate_profile"]["core"]["full_name"] == sample_profile.core.full_name
    assert user_data["candidate_profile"]["tax"]["pan"] == sample_profile.tax.pan


def test_pydantic_fill_plan_validation():
    """Verify strict Pydantic model validation on FillPlan and FillPlanItem."""
    plan_dict = {
        "target_url": "https://example.com/apply",
        "items": [
            {
                "field_id": "name",
                "selector": "#name",
                "field_type": "text",
                "value": "Alice",
                "frame_index": 0,
            }
        ],
        "resume_path": "/tmp/resume.pdf",
    }
    plan = FillPlan.model_validate(plan_dict)
    assert plan.target_url == "https://example.com/apply"
    assert len(plan.items) == 1
    assert plan.items[0].value == "Alice"

    # Validation failure on invalid field_type
    with pytest.raises(Exception):
        FillPlan.model_validate({
            "target_url": "https://example.com/apply",
            "items": [
                {
                    "field_id": "name",
                    "selector": "#name",
                    "field_type": "invalid_element_type",
                    "value": "Alice",
                }
            ],
        })


@pytest.mark.asyncio
async def test_offline_heuristic_fallback_greenhouse(greenhouse_schema, sample_profile):
    """Verify deterministic heuristic fallback accurately populates Greenhouse ATS fields."""
    client = UltramarineClient(offline_mode=True)
    plan = await client.generate_fill_plan(greenhouse_schema, sample_profile)

    assert plan.target_url == greenhouse_schema.url
    assert len(plan.items) >= 7

    # Check candidate core fields
    first_name_item = next(i for i in plan.items if i.selector == "#first_name")
    assert first_name_item.value == "Arjun"

    last_name_item = next(i for i in plan.items if i.selector == "#last_name")
    assert last_name_item.value == "Sharma"

    email_item = next(i for i in plan.items if i.selector == "#email")
    assert email_item.value == sample_profile.core.email

    phone_item = next(i for i in plan.items if i.selector == "#phone")
    assert phone_item.value == sample_profile.core.phone

    linkedin_item = next(i for i in plan.items if "0_text_value" in i.field_id)
    assert linkedin_item.value == sample_profile.career.linkedin_url

    github_item = next(i for i in plan.items if "1_text_value" in i.field_id)
    assert github_item.value == sample_profile.career.github_url

    essay_item = next(i for i in plan.items if i.field_id == "essay_distributed_systems")
    assert "Arjun Sharma" in essay_item.value or "distributed" in essay_item.value.lower()
    assert any(skill in essay_item.value for skill in sample_profile.career.skills)


@pytest.mark.asyncio
async def test_offline_heuristic_fallback_w8ben(w8ben_schema, sample_profile):
    """Verify deterministic heuristic fallback handles Form W-8BEN compliance rules."""
    client = UltramarineClient(offline_mode=True)
    plan = await client.generate_fill_plan(w8ben_schema, sample_profile)

    assert plan.target_url == w8ben_schema.url
    assert len(plan.items) >= 10

    # Line 1: Full name
    name_item = next(i for i in plan.items if i.field_id == "line1_name")
    assert name_item.value == sample_profile.core.full_name

    # Line 2: Citizenship
    country_item = next(i for i in plan.items if i.field_id == "line2_country")
    assert country_item.value == "India"

    # Line 6a: Indian PAN strictly mapped
    pan_item = next(i for i in plan.items if i.field_id == "line6a_ftin")
    assert pan_item.value == "ABCDE1234F"

    # Line 6b: MUST BE FALSE / UNCHECKED
    no_ftin_item = next(i for i in plan.items if i.field_id == "line6b_no_ftin")
    assert no_ftin_item.value == "false"

    # Line 8: DOB formatted to MM-DD-YYYY
    dob_item = next(i for i in plan.items if i.field_id == "line8_dob")
    assert dob_item.value == "08-15-1994"

    # Line 10: Special rates and treaty benefits
    article_item = next(i for i in plan.items if i.field_id == "line10_article")
    assert article_item.value == "Article 12(2)"

    rate_item = next(i for i in plan.items if i.field_id == "line10_rate")
    assert rate_item.value == "15%"


@pytest.mark.asyncio
async def test_live_api_with_mocked_openai_client(greenhouse_schema, sample_profile):
    """Verify live client path passes sticky x-session-id and validates model completions."""
    mock_openai = MagicMock()
    mock_completions = AsyncMock()

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()

    simulated_plan = {
        "target_url": greenhouse_schema.url,
        "items": [
            {
                "field_id": "first_name",
                "selector": "#first_name",
                "field_type": "text",
                "value": "Arjun",
                "frame_index": 0,
            },
            {
                "field_id": "email",
                "selector": "#email",
                "field_type": "email",
                "value": "arjun@example.com",
                "frame_index": 0,
            },
        ],
        "resume_path": "/tmp/resume.pdf",
    }
    mock_message.content = json.dumps(simulated_plan)
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_completions.create.return_value = mock_response
    mock_openai.chat.completions = mock_completions

    client = UltramarineClient(api_key="pi_live_real_key_123", offline_mode=False)
    client.client = mock_openai

    session_id = "sess_custom_test_99"
    plan = await client.generate_fill_plan(greenhouse_schema, sample_profile, session_id=session_id)

    assert plan.target_url == greenhouse_schema.url
    assert len(plan.items) == 2

    # Verify call arguments
    mock_completions.create.assert_awaited_once()
    kwargs = mock_completions.create.call_args.kwargs
    assert kwargs["model"] == "ultramarine-1-flash"
    assert kwargs["extra_headers"] == {"x-session-id": session_id}
    assert kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_live_api_error_graceful_fallback(greenhouse_schema, sample_profile):
    """Verify that remote API errors gracefully trigger the offline heuristic fallback engine."""
    mock_openai = MagicMock()
    mock_completions = AsyncMock()
    mock_completions.create.side_effect = RuntimeError("Paper Instruments API 503 Service Unavailable")
    mock_openai.chat.completions = mock_completions

    client = UltramarineClient(api_key="pi_live_real_key_123", offline_mode=False)
    client.client = mock_openai

    # Should not raise; falls back gracefully
    plan = await client.generate_fill_plan(greenhouse_schema, sample_profile)
    assert plan is not None
    assert plan.target_url == greenhouse_schema.url
    assert len(plan.items) >= 7
