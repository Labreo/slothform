"""Identity and field classification schemas for SlothForm."""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, EmailStr, Field


class SensitivityTier(str, Enum):
    """Four-tier field sensitivity classification."""
    PUBLIC = "PUBLIC"                     # Name, email, public URLs
    SEMI_SENSITIVE = "SEMI_SENSITIVE"     # Phone, address, resume
    CRITICAL_TAX = "CRITICAL_TAX"         # PAN, SSN, Tax treaty, DOB
    CRITICAL_FINANCIAL = "CRITICAL_FINANCIAL"  # Bank details, Wise ID


class FormContext(str, Enum):
    """Contextual form submission environment."""
    ATS_JOB_APPLICATION = "ATS_JOB_APPLICATION"
    W8BEN_CONTRACTOR_COMPLIANCE = "W8BEN_CONTRACTOR_COMPLIANCE"
    PAYMENT_RECIPIENT_SETUP = "PAYMENT_RECIPIENT_SETUP"


class FieldConsentViolationError(Exception):
    """Raised when an unconsented or context-prohibited attribute is accessed."""
    pass


class UnclassifiedFieldError(Exception):
    """Raised when an unknown profile attribute has no sensitivity tier."""
    pass


class CoreProfile(BaseModel):
    """Master personal and contact details."""
    full_name: str
    email: EmailStr
    phone: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state_province: str
    postal_code: str
    country: str = "India"
    citizenship: str = "India"
    date_of_birth: Optional[str] = None  # YYYY-MM-DD format


class TaxProfile(BaseModel):
    """Tax identity and treaty benefits details."""
    tax_residence_country: str = "India"
    pan: Optional[str] = Field(
        default=None,
        pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$",
        description="Indian 10-char PAN (Permanent Account Number)"
    )
    ssn_itin: Optional[str] = None  # Blocked / None for non-US residents
    has_us_tax_id: bool = False
    tax_treaty_country: str = "India"
    tax_treaty_article: str = "Article 12(2)"
    treaty_withholding_rate: str = "15%"
    treaty_income_type: str = "Royalties / Independent Personal Services"
    claim_treaty_benefits: bool = True


class CareerProfile(BaseModel):
    """Career experience, resume, and portfolio details."""
    headline: str
    years_of_experience: int
    skills: List[str]
    resume_markdown: str
    github_url: str
    linkedin_url: str
    portfolio_url: Optional[str] = None
    custom_qa_pairs: Dict[str, str] = Field(default_factory=dict)


class FinancialProfile(BaseModel):
    """Banking and remittance details for contractor compensation."""
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    routing_ifsc: Optional[str] = None
    swift_bic: Optional[str] = None
    wise_recipient_id: Optional[str] = None


class MasterIdentityProfile(BaseModel):
    """Complete aggregated user profile stored in the encrypted identity vault."""
    core: CoreProfile
    tax: TaxProfile
    career: CareerProfile
    financial: FinancialProfile


# Field sensitivity classification dictionary
FIELD_TIERS: Dict[str, SensitivityTier] = {
    # Core attributes
    "full_name": SensitivityTier.PUBLIC,
    "email": SensitivityTier.PUBLIC,
    "linkedin_url": SensitivityTier.PUBLIC,
    "github_url": SensitivityTier.PUBLIC,
    "portfolio_url": SensitivityTier.PUBLIC,
    "headline": SensitivityTier.PUBLIC,
    "years_of_experience": SensitivityTier.PUBLIC,
    "skills": SensitivityTier.PUBLIC,
    "country": SensitivityTier.PUBLIC,
    "citizenship": SensitivityTier.PUBLIC,
    "phone": SensitivityTier.SEMI_SENSITIVE,
    "address": SensitivityTier.SEMI_SENSITIVE,
    "address_line1": SensitivityTier.SEMI_SENSITIVE,
    "address_line2": SensitivityTier.SEMI_SENSITIVE,
    "city": SensitivityTier.SEMI_SENSITIVE,
    "state_province": SensitivityTier.SEMI_SENSITIVE,
    "postal_code": SensitivityTier.SEMI_SENSITIVE,
    "resume_markdown": SensitivityTier.SEMI_SENSITIVE,
    "custom_qa_pairs": SensitivityTier.SEMI_SENSITIVE,
    "date_of_birth": SensitivityTier.CRITICAL_TAX,

    # Tax attributes
    "pan": SensitivityTier.CRITICAL_TAX,
    "ssn_itin": SensitivityTier.CRITICAL_TAX,
    "ssn": SensitivityTier.CRITICAL_TAX,
    "has_us_tax_id": SensitivityTier.CRITICAL_TAX,
    "tax_residence_country": SensitivityTier.CRITICAL_TAX,
    "tax_treaty_country": SensitivityTier.CRITICAL_TAX,
    "tax_treaty_article": SensitivityTier.CRITICAL_TAX,
    "treaty_withholding_rate": SensitivityTier.CRITICAL_TAX,
    "treaty_income_type": SensitivityTier.CRITICAL_TAX,
    "claim_treaty_benefits": SensitivityTier.CRITICAL_TAX,

    # Financial attributes
    "bank_name": SensitivityTier.CRITICAL_FINANCIAL,
    "account_number": SensitivityTier.CRITICAL_FINANCIAL,
    "routing_ifsc": SensitivityTier.CRITICAL_FINANCIAL,
    "swift_bic": SensitivityTier.CRITICAL_FINANCIAL,
    "wise_recipient_id": SensitivityTier.CRITICAL_FINANCIAL,
}

# Context Policies: which tiers are permissible to release per form context
CONTEXT_POLICIES: Dict[FormContext, List[SensitivityTier]] = {
    FormContext.ATS_JOB_APPLICATION: [
        SensitivityTier.PUBLIC,
        SensitivityTier.SEMI_SENSITIVE,
    ],
    FormContext.W8BEN_CONTRACTOR_COMPLIANCE: [
        SensitivityTier.PUBLIC,
        SensitivityTier.SEMI_SENSITIVE,
        SensitivityTier.CRITICAL_TAX,
    ],
    FormContext.PAYMENT_RECIPIENT_SETUP: [
        SensitivityTier.PUBLIC,
        SensitivityTier.CRITICAL_FINANCIAL,
    ],
}


def get_field_tier(field_name: str) -> SensitivityTier:
    """Retrieve the classification sensitivity tier for a field name.
    
    Raises:
        UnclassifiedFieldError if the field has not been classified.
    """
    clean_name = field_name.lower().strip().replace("-", "_").replace(" ", "_")
    if clean_name in FIELD_TIERS:
        return FIELD_TIERS[clean_name]
    
    # Check for substring matches for common patterns
    if any(k in clean_name for k in ["tax", "pan", "ssn", "tin", "ein"]):
        return SensitivityTier.CRITICAL_TAX
    if any(k in clean_name for k in ["bank", "account", "routing", "ifsc", "swift", "iban", "wise"]):
        return SensitivityTier.CRITICAL_FINANCIAL
    if any(k in clean_name for k in ["phone", "address", "resume", "street", "postal", "zip"]):
        return SensitivityTier.SEMI_SENSITIVE
    if any(k in clean_name for k in ["name", "email", "url", "github", "linkedin", "title", "role"]):
        return SensitivityTier.PUBLIC

    raise UnclassifiedFieldError(f"Field '{field_name}' has no registered sensitivity tier.")


def is_field_allowed(field_name: str, context: FormContext) -> bool:
    """Check whether a field is permissible under the given form context policy."""
    tier = get_field_tier(field_name)
    allowed_tiers = CONTEXT_POLICIES.get(context, [])
    
    # Specific rule: On ATS job applications, tax IDs (PAN/SSN) and banking are strictly blocked
    if context == FormContext.ATS_JOB_APPLICATION and tier in (
        SensitivityTier.CRITICAL_TAX,
        SensitivityTier.CRITICAL_FINANCIAL,
    ):
        return False

    # Specific rule: On W-8BEN contractor compliance forms, SSN is explicitly blocked for foreign contractors
    if context == FormContext.W8BEN_CONTRACTOR_COMPLIANCE:
        clean_name = field_name.lower().strip().replace("-", "_")
        if clean_name in ("ssn", "ssn_itin"):
            return False

    return tier in allowed_tiers


def mask_sensitive_value(field_name: str, value: Any) -> str:
    """Produce a sanitized masked display string for human review."""
    if value is None:
        return "[NOT_SET]"
    
    val_str = str(value)
    if not val_str:
        return ""
        
    try:
        tier = get_field_tier(field_name)
    except UnclassifiedFieldError:
        tier = SensitivityTier.CRITICAL_TAX  # Default to high security

    if tier == SensitivityTier.PUBLIC:
        return val_str
    
    if tier == SensitivityTier.SEMI_SENSITIVE:
        if "phone" in field_name.lower() and len(val_str) > 4:
            return f"{'*' * (len(val_str) - 4)}{val_str[-4:]}"
        if "address" in field_name.lower():
            return f"{val_str[:6]}... [MASKED]"
        return f"{val_str[:20]}..." if len(val_str) > 20 else val_str

    if tier == SensitivityTier.CRITICAL_TAX:
        if len(val_str) == 10:  # Indian PAN format e.g. ABCDE1234F
            return f"{val_str[:5]}****{val_str[-1]}"
        return f"***-**-{val_str[-4:]}" if len(val_str) >= 4 else "[REDACTED_TAX_ID]"

    if tier == SensitivityTier.CRITICAL_FINANCIAL:
        return f"****{val_str[-4:]}" if len(val_str) >= 4 else "[REDACTED_FINANCIAL]"

    return "[REDACTED]"
