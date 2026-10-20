"""Local Encrypted Identity Store with AES-256-GCM AEAD and Context Policy Engine."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings
from app.models.identity_schema import (
    CareerProfile,
    CoreProfile,
    FieldConsentViolationError,
    FinancialProfile,
    FormContext,
    MasterIdentityProfile,
    TaxProfile,
    get_field_tier,
    is_field_allowed,
)


class VaultError(Exception):
    """Base exception for Vault errors."""
    pass


class VaultDecryptionError(VaultError):
    """Raised when ciphertext is tampered, corrupted, or key is invalid."""
    pass


class VaultLockedError(VaultError):
    """Raised when an operation requires an unlocked vault but no key is loaded."""
    pass


class VaultNotFoundError(VaultError):
    """Raised when the persistent vault file does not exist on disk."""
    pass


# Binary Envelope Constants
MAGIC: bytes = b"SLOTHVAULT1"  # 11 bytes header magic
SALT_LEN: int = 16
NONCE_LEN: int = 12
TAG_LEN: int = 16
MIN_ENVELOPE_LEN: int = len(MAGIC) + SALT_LEN + NONCE_LEN + TAG_LEN  # 55 bytes
HKDF_INFO: bytes = b"slothform-identity-vault-v1"


_UNSET = object()


class VaultManager:
    """Manages AES-256-GCM encrypted persistence of identity profiles and context policies."""

    def __init__(self, vault_path: Optional[str] = None, vault_key: Any = _UNSET) -> None:
        settings = get_settings()
        self.vault_path: Path = Path(vault_path or settings.VAULT_FILE_PATH)
        if vault_key is _UNSET:
            self._vault_key: Optional[str] = os.getenv("AUTH0_TOKEN_VAULT_KEY") or settings.AUTH0_TOKEN_VAULT_KEY
        else:
            self._vault_key = vault_key
        self._cached_profile: Optional[MasterIdentityProfile] = None

    @property
    def is_locked(self) -> bool:
        """Return True if no encryption key is currently available."""
        return not bool(self._vault_key)

    def unlock(self, key: str) -> None:
        """Unlock the vault with the provided key."""
        if not key or len(key.strip()) < 8:
            raise ValueError("Vault key must be at least 8 characters long.")
        self._vault_key = key
        # Reset cached profile on new key unlock
        self._cached_profile = None

    def lock(self) -> None:
        """Lock the vault by purging key and cached plaintext from memory."""
        self._vault_key = None
        self._cached_profile = None

    def is_initialized(self) -> bool:
        """Check if the vault file exists and contains the valid magic header."""
        if not self.vault_path.exists():
            return False
        try:
            with open(self.vault_path, "rb") as f:
                header = f.read(len(MAGIC))
            return header == MAGIC
        except Exception:
            return False

    @staticmethod
    def derive_key(master_key: Union[str, bytes], salt: bytes) -> bytes:
        """Derive a 256-bit AES key from master key and salt using HKDF-SHA256."""
        key_bytes = master_key.encode("utf-8") if isinstance(master_key, str) else master_key
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=HKDF_INFO,
        )
        return hkdf.derive(key_bytes)

    def encrypt(self, plaintext: bytes, key: Optional[str] = None) -> bytes:
        """Encrypt plaintext bytes into an authenticated envelope with AES-256-GCM.
        
        Envelope structure:
        [MAGIC (11B)][SALT (16B)][NONCE (12B)][TAG (16B)][RAW_CIPHERTEXT]
        """
        enc_key = key or self._vault_key
        if not enc_key:
            raise VaultLockedError("Vault is locked. Provide a valid vault key to encrypt.")

        salt = os.urandom(SALT_LEN)
        nonce = os.urandom(NONCE_LEN)
        derived_key = self.derive_key(enc_key, salt)

        aesgcm = AESGCM(derived_key)
        # AESGCM.encrypt appends the 16-byte tag to the ciphertext
        encrypted_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data=MAGIC)
        raw_ciphertext = encrypted_with_tag[:-TAG_LEN]
        tag = encrypted_with_tag[-TAG_LEN:]

        return MAGIC + salt + nonce + tag + raw_ciphertext

    def decrypt(self, envelope: bytes, key: Optional[str] = None) -> bytes:
        """Decrypt an authenticated envelope with AES-256-GCM.
        
        Raises:
            VaultDecryptionError if header magic fails, envelope is truncated,
            or ciphertext/tag has been tampered with or key is invalid.
        """
        enc_key = key or self._vault_key
        if not enc_key:
            raise VaultLockedError("Vault is locked. Provide a valid vault key to decrypt.")

        if len(envelope) < MIN_ENVELOPE_LEN:
            raise VaultDecryptionError(
                f"Corrupted vault envelope: length {len(envelope)} is less than minimum {MIN_ENVELOPE_LEN} bytes."
            )

        magic_in = envelope[:len(MAGIC)]
        if magic_in != MAGIC:
            raise VaultDecryptionError(
                f"Invalid vault header magic: expected {MAGIC!r}, got {magic_in!r}."
            )

        offset = len(MAGIC)
        salt = envelope[offset : offset + SALT_LEN]
        offset += SALT_LEN
        nonce = envelope[offset : offset + NONCE_LEN]
        offset += NONCE_LEN
        tag = envelope[offset : offset + TAG_LEN]
        offset += TAG_LEN
        raw_ciphertext = envelope[offset:]

        derived_key = self.derive_key(enc_key, salt)
        aesgcm = AESGCM(derived_key)

        # Recombine raw ciphertext and authentication tag for AESGCM.decrypt
        data_to_verify = raw_ciphertext + tag

        try:
            plaintext = aesgcm.decrypt(nonce, data_to_verify, associated_data=MAGIC)
            return plaintext
        except InvalidTag:
            raise VaultDecryptionError(
                "Vault authentication tag mismatch: data has been tampered with or incorrect vault key."
            )
        except Exception as e:
            raise VaultDecryptionError(f"Vault decryption failed: {e}")

    def save_profile(self, profile: MasterIdentityProfile) -> None:
        """Encrypt and persist the master profile to the configured vault file."""
        if self.is_locked:
            raise VaultLockedError("Cannot save profile: Vault is locked.")

        # Ensure directory exists
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)

        json_bytes = profile.model_dump_json(indent=2).encode("utf-8")
        envelope = self.encrypt(json_bytes)

        # Atomic write to temporary file then replace
        temp_path = self.vault_path.with_suffix(".tmp")
        with open(temp_path, "wb") as f:
            f.write(envelope)
        temp_path.replace(self.vault_path)

        self._cached_profile = profile

    def load_profile(self, force_reload: bool = False) -> MasterIdentityProfile:
        """Load and decrypt the master identity profile from disk."""
        if not force_reload and self._cached_profile is not None:
            return self._cached_profile

        if not self.vault_path.exists():
            raise VaultNotFoundError(f"Vault file not found at '{self.vault_path}'. Initialize the vault first.")

        if self.is_locked:
            raise VaultLockedError("Cannot load profile: Vault is locked.")

        with open(self.vault_path, "rb") as f:
            envelope = f.read()

        decrypted_bytes = self.decrypt(envelope)
        try:
            profile_dict = json.loads(decrypted_bytes.decode("utf-8"))
            profile = MasterIdentityProfile.model_validate(profile_dict)
            self._cached_profile = profile
            return profile
        except Exception as e:
            raise VaultDecryptionError(f"Failed to parse decrypted profile JSON: {e}")

    def get_profile(self, context: Optional[FormContext] = None) -> MasterIdentityProfile:
        """Retrieve identity profile, optionally applying context-aware privacy redactions.
        
        Interface Contract:
            VaultManager.get_profile(context: FormContext) -> MasterIdentityProfile
        """
        master = self.load_profile()
        if context is None:
            return master
        return self.filter_profile_for_context(master, context)

    def filter_profile_for_context(
        self, profile: MasterIdentityProfile, context: FormContext
    ) -> MasterIdentityProfile:
        """Create a sanitized clone of the profile adhering strictly to context policy."""
        # Deep copy via serialization
        raw_dict = profile.model_dump()

        if context == FormContext.ATS_JOB_APPLICATION:
            # ATS Forms (Greenhouse, Lever, Ashby):
            # Only PUBLIC and SEMI_SENSITIVE are permitted.
            # CRITICAL_TAX and CRITICAL_FINANCIAL are strictly redacted/blocked.
            raw_dict["tax"] = {
                "tax_residence_country": raw_dict["core"].get("country", "India"),
                "pan": None,
                "ssn_itin": None,
                "has_us_tax_id": False,
                "tax_treaty_country": raw_dict["core"].get("country", "India"),
                "tax_treaty_article": "",
                "treaty_withholding_rate": "",
                "treaty_income_type": "",
                "claim_treaty_benefits": False,
            }
            raw_dict["financial"] = {
                "bank_name": None,
                "account_number": None,
                "routing_ifsc": None,
                "swift_bic": None,
                "wise_recipient_id": None,
            }
            # Also redact DOB from core profile on ATS job apps to prevent age discrimination
            raw_dict["core"]["date_of_birth"] = None

        elif context == FormContext.W8BEN_CONTRACTOR_COMPLIANCE:
            # W-8BEN Tax Compliance Forms:
            # PUBLIC, SEMI_SENSITIVE, and CRITICAL_TAX (specifically Indian PAN for Box 6a) are permitted.
            # SSN/ITIN is strictly BLOCKED for foreign contractors claiming treaty.
            # CRITICAL_FINANCIAL is blocked.
            raw_dict["tax"]["ssn_itin"] = None
            raw_dict["tax"]["has_us_tax_id"] = False
            raw_dict["financial"] = {
                "bank_name": None,
                "account_number": None,
                "routing_ifsc": None,
                "swift_bic": None,
                "wise_recipient_id": None,
            }

        elif context == FormContext.PAYMENT_RECIPIENT_SETUP:
            # Payment Setup:
            # PUBLIC and CRITICAL_FINANCIAL are permitted.
            # Tax treaty specifics and full resume are scrubbed.
            raw_dict["career"]["resume_markdown"] = ""
            raw_dict["career"]["custom_qa_pairs"] = {}
            raw_dict["tax"]["ssn_itin"] = None

        return MasterIdentityProfile.model_validate(raw_dict)

    def get_field_with_consent_check(
        self, field_name: str, context: FormContext, profile: Optional[MasterIdentityProfile] = None
    ) -> Any:
        """Retrieve a specific field value while verifying context consent policies.
        
        Raises:
            FieldConsentViolationError if the field is prohibited in the given context.
        """
        if not is_field_allowed(field_name, context):
            tier = get_field_tier(field_name)
            raise FieldConsentViolationError(
                f"Field '{field_name}' (tier {tier.value}) is strictly prohibited "
                f"under context '{context.value}'."
            )

        active_profile = profile or self.load_profile()
        flat_fields = self.flatten_profile(active_profile)
        return flat_fields.get(field_name)

    @staticmethod
    def flatten_profile(profile: MasterIdentityProfile) -> Dict[str, Any]:
        """Flatten nested profile into a key-value dictionary for easy field matching."""
        result: Dict[str, Any] = {}
        for section in ("core", "tax", "career", "financial"):
            data = getattr(profile, section).model_dump()
            for k, v in data.items():
                result[k] = v
        # Add composite convenience keys
        result["address"] = f"{profile.core.address_line1}, {profile.core.city}, {profile.core.state_province} {profile.core.postal_code}, {profile.core.country}"
        return result


def create_sample_profile() -> MasterIdentityProfile:
    """Construct a sample Indian tech contractor profile for testing and bootstrap."""
    return MasterIdentityProfile(
        core=CoreProfile(
            full_name="Arjun Sharma",
            email="arjun.sharma@example.com",
            phone="+919876543210",
            address_line1="402 Palm Grove, Indiranagar",
            address_line2="100 Feet Road",
            city="Bengaluru",
            state_province="Karnataka",
            postal_code="560038",
            country="India",
            citizenship="India",
            date_of_birth="1994-08-15",
        ),
        tax=TaxProfile(
            tax_residence_country="India",
            pan="ABCDE1234F",
            ssn_itin=None,
            has_us_tax_id=False,
            tax_treaty_country="India",
            tax_treaty_article="Article 12(2)",
            treaty_withholding_rate="15%",
            treaty_income_type="Royalties / Independent Personal Services",
            claim_treaty_benefits=True,
        ),
        career=CareerProfile(
            headline="Senior Full-Stack & Distributed Systems Engineer",
            years_of_experience=8,
            skills=["Python", "FastAPI", "React", "TypeScript", "PostgreSQL", "Docker", "Kubernetes", "AWS"],
            resume_markdown="# Arjun Sharma\n\nSenior Full-Stack Engineer with 8+ years developing distributed systems...",
            github_url="https://github.com/arjunsharma-dev",
            linkedin_url="https://linkedin.com/in/arjunsharma-dev",
            portfolio_url="https://arjunsharma.dev",
            custom_qa_pairs={
                "why_interested": "Excited by challenging high-scale distributed systems problems and collaborative culture.",
                "work_authorization": "Authorized to work as an independent international contractor (B2B / W-8BEN).",
            },
        ),
        financial=FinancialProfile(
            bank_name="HDFC Bank",
            account_number="50100234567890",
            routing_ifsc="HDFC0000240",
            swift_bic="HDFCINBB",
            wise_recipient_id="wise_recp_98765432",
        ),
    )
