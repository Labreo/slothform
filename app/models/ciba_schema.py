"""OIDC CIBA and RFC 9396 Rich Authorization Request (RAR) schemas."""

import hashlib
import json
import time
from enum import Enum
from typing import Any, List, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, Field

from app.models.identity_schema import SensitivityTier, mask_sensitive_value, get_field_tier


class CIBAState(str, Enum):
    """Lifecycle state machine for backchannel authorization."""
    UNINITIALIZED = "UNINITIALIZED"
    INITIATED = "INITIATED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class CIBAError(Exception):
    """Base exception for CIBA protocol errors."""
    pass


class RefusalToSubmitError(CIBAError):
    """Raised when user rejects consent, request times out, or approval is missing.
    Guarantees the inviolable submission refusal invariant.
    """
    pass


class ConsentTimeoutError(RefusalToSubmitError):
    """Raised when a CIBA polling operation exceeds max expiration time."""
    pass


class FormFillDiffItem(BaseModel):
    """Individual form field proposed entry with masking and classification."""
    field_name: str
    selector: Optional[str] = None
    proposed_value: Any = None
    masked_value: str = ""
    tier: SensitivityTier = SensitivityTier.PUBLIC
    consent_required: bool = False


class FormFillDiff(BaseModel):
    """Structured form diff presented to the user during backchannel authentication."""
    target_url: str
    form_domain: str = ""
    items: List[FormFillDiffItem] = Field(default_factory=list)
    digest: str = ""
    fields_requested: List[str] = Field(default_factory=list)
    fields_redacted: List[str] = Field(default_factory=list)
    dry_run: bool = False

    @classmethod
    def from_field_values(
        cls,
        target_url: str,
        field_values: dict[str, Any],
        redacted_fields: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> "FormFillDiff":
        """Factory method to construct a validated FormFillDiff with SHA-256 digest."""
        domain = urlparse(target_url).netloc or "unknown"
        items: List[FormFillDiffItem] = []
        fields_requested: List[str] = []
        redacted = redacted_fields or []

        # Sort keys deterministically for reproducible digest
        for k in sorted(field_values.keys()):
            val = field_values[k]
            tier = get_field_tier(k)
            masked = mask_sensitive_value(k, val)
            items.append(
                FormFillDiffItem(
                    field_name=k,
                    proposed_value=val,
                    masked_value=masked,
                    tier=tier,
                    consent_required=(tier in (SensitivityTier.CRITICAL_TAX, SensitivityTier.CRITICAL_FINANCIAL)),
                )
            )
            fields_requested.append(k)

        # Compute SHA-256 digest over deterministic serialized proposed values
        digest_payload = {
            "target_url": target_url,
            "fields": {item.field_name: str(item.proposed_value) for item in items},
            "redacted": sorted(redacted),
            "dry_run": dry_run,
        }
        digest_bytes = json.dumps(digest_payload, sort_keys=True).encode("utf-8")
        computed_digest = f"sha256:{hashlib.sha256(digest_bytes).hexdigest()}"

        return cls(
            target_url=target_url,
            form_domain=domain,
            items=items,
            digest=computed_digest,
            fields_requested=fields_requested,
            fields_redacted=sorted(redacted),
            dry_run=dry_run,
        )


class RichAuthorizationDetail(BaseModel):
    """RFC 9396 Rich Authorization Request (RAR) structure passed to Auth0."""
    type: str = "slothform_consent"
    actions: List[str] = Field(default_factory=lambda: ["autofill", "submit"])
    target_url: str
    form_domain: str
    diff_digest: str
    fields_requested: List[str] = Field(default_factory=list)
    fields_redacted: List[str] = Field(default_factory=list)
    dry_run: bool = False

    @classmethod
    def from_diff(cls, diff: FormFillDiff) -> "RichAuthorizationDetail":
        """Convert a FormFillDiff into an RFC 9396 RAR object."""
        return cls(
            target_url=diff.target_url,
            form_domain=diff.form_domain,
            diff_digest=diff.digest,
            fields_requested=diff.fields_requested,
            fields_redacted=diff.fields_redacted,
            dry_run=diff.dry_run,
        )


class CIBARequest(BaseModel):
    """Response from Auth0 /bc-authorize initiation."""
    auth_req_id: str
    expires_in: int = 300
    interval: int = 5
    binding_message: str
    target_url: Optional[str] = None
    created_at: float = Field(default_factory=time.time)


class ConsentResult(BaseModel):
    """Result of Auth0 CIBA token polling."""
    approved: bool
    access_token: Optional[str] = None
    id_token: Optional[str] = None
    token_type: Optional[str] = "Bearer"
    expires_in: Optional[int] = None
    scope: Optional[str] = None
    error: Optional[str] = None
    error_description: Optional[str] = None
