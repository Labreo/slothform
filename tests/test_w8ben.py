"""Unit tests for IRS Form W-8BEN tax treaty resolver and Indian contractor compliance."""

import re
import pytest

from app.core.vault import create_sample_profile
from app.models.browser_schema import (
    FieldType,
    FormField,
    FormSchema,
    SubmitButton,
)
from app.models.identity_schema import CoreProfile, TaxProfile
from app.services.essay_synthesizer import (
    InvalidTaxIdentifierError,
    MissingTaxIdentifierError,
    W8BENResolver,
)


@pytest.fixture
def resolver():
    return W8BENResolver()


@pytest.fixture
def w8ben_schema():
    return FormSchema(
        url="https://compliance.contractor.io/w8ben",
        page_title="Form W-8BEN Certificate of Foreign Status",
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
                field_id="line2_citizenship",
                selector="#line2_citizenship",
                field_type=FieldType.TEXT,
                label="2. Country of citizenship",
                required=True,
            ),
            FormField(
                field_id="line3_address",
                selector="#line3_address",
                field_type=FieldType.TEXT,
                label="3. Permanent residence address (street address)",
                required=True,
            ),
            FormField(
                field_id="line3_city_state_zip",
                selector="#line3_city_state_zip",
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
                label="Sign Here: Full Legal Name",
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


def test_w8ben_pan_mapping_to_box6a(resolver, w8ben_schema):
    """Verify Indian PAN is strictly mapped to Box 6a (Foreign Tax ID)."""
    profile = create_sample_profile()
    items = resolver.resolve_tax_fields(w8ben_schema, profile)

    box6a = next(i for i in items if i.field_id == "line6a_ftin")
    assert box6a.value == profile.tax.pan
    assert box6a.value == "ABCDE1234F"
    assert re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", box6a.value)


def test_w8ben_box6b_strictly_omitted_or_false(resolver, w8ben_schema):
    """Verify Box 6b is strictly 'false' / unchecked because Indian residents must possess PAN."""
    profile = create_sample_profile()
    items = resolver.resolve_tax_fields(w8ben_schema, profile)

    box6b = next(i for i in items if i.field_id == "line6b_no_ftin")
    assert box6b.value == "false"
    assert box6b.field_type == FieldType.CHECKBOX


def test_w8ben_dob_formatting_irs_mm_dd_yyyy(resolver):
    """Verify date of birth is strictly formatted to MM-DD-YYYY per IRS rules."""
    # Test ISO YYYY-MM-DD
    assert resolver.format_dob("1994-08-15") == "08-15-1994"

    # Test DD-MM-YYYY
    assert resolver.format_dob("15-08-1994") == "08-15-1994"

    # Test YYYY/MM/DD
    assert resolver.format_dob("1994/08/15") == "08-15-1994"

    # Test already formatted MM-DD-YYYY
    assert resolver.format_dob("08-15-1994") == "08-15-1994"

    # Test regex validation
    dob = resolver.format_dob("1990-12-05")
    assert re.match(r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])-[0-9]{4}$", dob)


def test_w8ben_dtaa_article_12_2_and_15_percent_rate(resolver, w8ben_schema):
    """Verify US-India DTAA Article 12(2) claims 15% withholding rate with statutory explanation."""
    profile = create_sample_profile()
    items = resolver.resolve_tax_fields(w8ben_schema, profile)

    article = next(i for i in items if i.field_id == "line10_article")
    assert article.value == "Article 12(2)"

    rate = next(i for i in items if i.field_id == "line10_rate")
    assert rate.value == "15%"

    explanation = next(i for i in items if i.field_id == "line10_explanation")
    assert "India" in explanation.value
    assert "technical software services" in explanation.value


def test_w8ben_lines_1_2_3_9_signature_and_capacity(resolver, w8ben_schema):
    """Verify Lines 1, 2, 3, 9, Signature, and Capacity mappings."""
    profile = create_sample_profile()
    items = resolver.resolve_tax_fields(w8ben_schema, profile)

    name = next(i for i in items if i.field_id == "line1_name")
    assert name.value == "Arjun Sharma"

    citizenship = next(i for i in items if i.field_id == "line2_citizenship")
    assert citizenship.value == "India"

    address = next(i for i in items if i.field_id == "line3_address")
    assert address.value == profile.core.address_line1

    city_zip = next(i for i in items if i.field_id == "line3_city_state_zip")
    assert "Bengaluru" in city_zip.value
    assert "560038" in city_zip.value

    country = next(i for i in items if i.field_id == "line9_country")
    assert country.value == "India"

    sig = next(i for i in items if i.field_id == "signature")
    assert sig.value == profile.core.full_name

    cap = next(i for i in items if i.field_id == "capacity")
    assert cap.value == "Self"


def test_w8ben_missing_pan_raises_error(resolver, w8ben_schema):
    """Verify that a missing PAN triggers MissingTaxIdentifierError under strict validation."""
    tax = TaxProfile(pan=None)
    core = CoreProfile(
        full_name="No PAN Contractor",
        email="nopan@example.com",
        phone="+919999999999",
        address_line1="123 Street",
        city="Mumbai",
        state_province="Maharashtra",
        postal_code="400001",
    )
    with pytest.raises(MissingTaxIdentifierError) as exc_info:
        resolver.resolve_tax_fields(w8ben_schema, tax_profile=tax, core_profile=core, strict_pan=True)
    assert "Foreign Tax Identifying Number (Indian PAN) is mandatory" in str(exc_info.value)


def test_w8ben_invalid_pan_format_raises_error(resolver, w8ben_schema):
    """Verify that an invalid PAN string triggers InvalidTaxIdentifierError."""
    # Too short
    with pytest.raises(InvalidTaxIdentifierError):
        resolver.validate_pan("ABCDE1234")

    # All numbers
    with pytest.raises(InvalidTaxIdentifierError):
        resolver.validate_pan("1234567890")

    # Lowercase or wrong pattern
    with pytest.raises(InvalidTaxIdentifierError):
        resolver.validate_pan("12345ABCDE")
