"""Comprehensive unit and integration tests for Vault and Field Classification Subsystem."""

import os
import pytest
from pathlib import Path

from app.core.vault import (
    MAGIC,
    VaultDecryptionError,
    VaultLockedError,
    VaultManager,
    VaultNotFoundError,
    create_sample_profile,
)
from app.models.identity_schema import (
    FieldConsentViolationError,
    FormContext,
    SensitivityTier,
    UnclassifiedFieldError,
    get_field_tier,
    mask_sensitive_value,
)


@pytest.fixture
def temp_vault_path(tmp_path):
    """Provide an isolated temporary file path for vault testing."""
    return str(tmp_path / "test_vault.enc")


@pytest.fixture
def vault_key():
    """Consistent 256-bit test encryption key."""
    return "test_auth0_vault_encryption_key_32b!"


@pytest.fixture
def sample_profile():
    """Deterministic sample profile for testing."""
    return create_sample_profile()


# ==============================================================================
# 1. AES-256-GCM AEAD Encryption and Decryption Tests
# ==============================================================================

def test_aes_gcm_encrypt_decrypt_roundtrip(temp_vault_path, vault_key):
    """Verify that plaintext encrypts and decrypts losslessly with valid key."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    plaintext = b'{"pan": "ABCDE1234F", "secret": "confidential_tax_info"}'

    envelope = vm.encrypt(plaintext)
    assert envelope.startswith(MAGIC)
    assert len(envelope) > 55  # Magic(11) + Salt(16) + Nonce(12) + Tag(16) + Ciphertext

    decrypted = vm.decrypt(envelope)
    assert decrypted == plaintext


def test_hkdf_key_derivation_deterministic():
    """Verify HKDF-SHA256 produces predictable 32-byte keys for same salt and master key."""
    salt = os.urandom(16)
    master_key = "my_master_key_12345"
    key1 = VaultManager.derive_key(master_key, salt)
    key2 = VaultManager.derive_key(master_key, salt)
    assert key1 == key2
    assert len(key1) == 32

    # Different salt must yield different derived key
    other_salt = os.urandom(16)
    key3 = VaultManager.derive_key(master_key, other_salt)
    assert key1 != key3


def test_vault_tamper_resistance_fails_on_altered_ciphertext(temp_vault_path, vault_key):
    """Invariant: Flipped bit in ciphertext must fail AES-256-GCM authentication and raise VaultDecryptionError."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    envelope = bytearray(vm.encrypt(b"Top secret user identity data"))

    # Alter the very last byte of the ciphertext
    envelope[-1] ^= 0x01

    with pytest.raises(VaultDecryptionError) as exc_info:
        vm.decrypt(bytes(envelope))
    assert "Vault authentication tag mismatch" in str(exc_info.value)


def test_vault_tamper_resistance_fails_on_altered_tag(temp_vault_path, vault_key):
    """Invariant: Tampered authentication tag must trigger VaultDecryptionError."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    envelope = bytearray(vm.encrypt(b"Sensitive financial attributes"))

    # Tag is located at offset 11 + 16 + 12 = 39 to 55
    tag_offset = len(MAGIC) + 16 + 12
    envelope[tag_offset] ^= 0xFF

    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(envelope))


def test_vault_tamper_resistance_fails_on_corrupted_magic(temp_vault_path, vault_key):
    """Header magic mismatch must be rejected before processing."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    envelope = bytearray(vm.encrypt(b"Profile data"))

    # Corrupt header magic
    envelope[:len(MAGIC)] = b"BADMAGIC001"

    with pytest.raises(VaultDecryptionError) as exc_info:
        vm.decrypt(bytes(envelope))
    assert "Invalid vault header magic" in str(exc_info.value)


def test_vault_tamper_resistance_fails_on_truncated_envelope(temp_vault_path, vault_key):
    """Envelopes shorter than minimum header length must be rejected."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    truncated = b"SLOTHVAULT1tooshort"

    with pytest.raises(VaultDecryptionError) as exc_info:
        vm.decrypt(truncated)
    assert "Corrupted vault envelope" in str(exc_info.value)


def test_vault_fails_with_wrong_key(temp_vault_path, vault_key):
    """Decrypting with an incorrect key fails authentication tag check."""
    vm1 = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    envelope = vm1.encrypt(b"Secret payload")

    vm2 = VaultManager(vault_path=temp_vault_path, vault_key="completely_wrong_vault_key_123456")
    with pytest.raises(VaultDecryptionError):
        vm2.decrypt(envelope)


# ==============================================================================
# 2. Vault Persistence and Lifecycle Tests
# ==============================================================================

def test_vault_lifecycle_save_and_load(temp_vault_path, vault_key, sample_profile):
    """Test saving profile to disk and loading it back cleanly."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    assert not vm.is_initialized()

    vm.save_profile(sample_profile)
    assert vm.is_initialized()
    assert Path(temp_vault_path).exists()

    # Load from disk with fresh manager instance
    vm2 = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    loaded = vm2.load_profile()
    assert loaded.core.full_name == "Arjun Sharma"
    assert loaded.tax.pan == "ABCDE1234F"
    assert loaded.financial.bank_name == "HDFC Bank"
    assert loaded.career.years_of_experience == 8


def test_vault_load_nonexistent_raises_not_found(tmp_path, vault_key):
    """Attempting to load from an uninitialized path raises VaultNotFoundError."""
    non_existent = str(tmp_path / "does_not_exist.enc")
    vm = VaultManager(vault_path=non_existent, vault_key=vault_key)
    with pytest.raises(VaultNotFoundError):
        vm.load_profile()


def test_vault_locked_state_enforcement(temp_vault_path):
    """Operations without a key raise VaultLockedError."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=None)
    assert vm.is_locked

    with pytest.raises(VaultLockedError):
        vm.encrypt(b"data")

    with pytest.raises(VaultLockedError):
        vm.decrypt(b"data")

    with pytest.raises(VaultLockedError):
        vm.save_profile(create_sample_profile())

    # Unlock and verify operations succeed
    vm.unlock("new_unlocked_key_12345678")
    assert not vm.is_locked
    env = vm.encrypt(b"valid test data")
    assert vm.decrypt(env) == b"valid test data"

    # Lock again and verify state is cleared
    vm.lock()
    assert vm.is_locked


# ==============================================================================
# 3. 4-Tier Field Sensitivity Classification Engine Tests
# ==============================================================================

def test_field_tier_classification():
    """Verify accurate 4-tier classification for all core, tax, and financial fields."""
    # PUBLIC tier
    assert get_field_tier("full_name") == SensitivityTier.PUBLIC
    assert get_field_tier("email") == SensitivityTier.PUBLIC
    assert get_field_tier("linkedin_url") == SensitivityTier.PUBLIC
    assert get_field_tier("github_url") == SensitivityTier.PUBLIC

    # SEMI_SENSITIVE tier
    assert get_field_tier("phone") == SensitivityTier.SEMI_SENSITIVE
    assert get_field_tier("address") == SensitivityTier.SEMI_SENSITIVE
    assert get_field_tier("resume_markdown") == SensitivityTier.SEMI_SENSITIVE

    # CRITICAL_TAX tier
    assert get_field_tier("pan") == SensitivityTier.CRITICAL_TAX
    assert get_field_tier("ssn") == SensitivityTier.CRITICAL_TAX
    assert get_field_tier("ssn_itin") == SensitivityTier.CRITICAL_TAX
    assert get_field_tier("date_of_birth") == SensitivityTier.CRITICAL_TAX
    assert get_field_tier("tax_treaty_article") == SensitivityTier.CRITICAL_TAX

    # CRITICAL_FINANCIAL tier
    assert get_field_tier("bank_name") == SensitivityTier.CRITICAL_FINANCIAL
    assert get_field_tier("account_number") == SensitivityTier.CRITICAL_FINANCIAL
    assert get_field_tier("routing_ifsc") == SensitivityTier.CRITICAL_FINANCIAL
    assert get_field_tier("wise_recipient_id") == SensitivityTier.CRITICAL_FINANCIAL


def test_unclassified_field_raises_error():
    """Unmapped and unrecognized field keys raise UnclassifiedFieldError."""
    with pytest.raises(UnclassifiedFieldError):
        get_field_tier("completely_random_xyz_field_9876")


def test_field_masking():
    """Verify masking outputs for human review in diffs."""
    assert mask_sensitive_value("full_name", "Arjun Sharma") == "Arjun Sharma"
    assert mask_sensitive_value("pan", "ABCDE1234F") == "ABCDE****F"
    assert mask_sensitive_value("phone", "+919876543210") == "*********" + "3210"
    assert mask_sensitive_value("account_number", "50100234567890") == "****7890"
    assert mask_sensitive_value("ssn", "123456789") == "***-**-6789"


# ==============================================================================
# 4. Context-Aware Consent Policy Enforcement Tests
# ==============================================================================

def test_ats_context_policy_blocks_tax_and_financial(temp_vault_path, vault_key, sample_profile):
    """ATS Job applications strictly redact tax identifiers, banking details, and DOB."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    vm.save_profile(sample_profile)

    ats_profile = vm.get_profile(context=FormContext.ATS_JOB_APPLICATION)

    # Core public and semi-sensitive fields intact
    assert ats_profile.core.full_name == "Arjun Sharma"
    assert ats_profile.core.email == "arjun.sharma@example.com"
    assert ats_profile.core.phone == "+919876543210"
    assert ats_profile.career.years_of_experience == 8

    # CRITICAL_TAX must be scrubbed
    assert ats_profile.tax.pan is None
    assert ats_profile.tax.ssn_itin is None
    assert ats_profile.core.date_of_birth is None
    assert ats_profile.tax.claim_treaty_benefits is False

    # CRITICAL_FINANCIAL must be scrubbed
    assert ats_profile.financial.bank_name is None
    assert ats_profile.financial.account_number is None
    assert ats_profile.financial.routing_ifsc is None


def test_w8ben_context_policy_permits_pan_and_blocks_ssn(temp_vault_path, vault_key, sample_profile):
    """W-8BEN compliance permits Indian PAN for Box 6a, but blocks SSN/ITIN and banking."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    vm.save_profile(sample_profile)

    w8_profile = vm.get_profile(context=FormContext.W8BEN_CONTRACTOR_COMPLIANCE)

    # Indian PAN is permitted and preserved
    assert w8_profile.tax.pan == "ABCDE1234F"
    assert w8_profile.tax.tax_treaty_country == "India"
    assert w8_profile.tax.tax_treaty_article == "Article 12(2)"

    # SSN/ITIN must be blocked
    assert w8_profile.tax.ssn_itin is None

    # Financial details must be blocked
    assert w8_profile.financial.bank_name is None
    assert w8_profile.financial.account_number is None


def test_field_consent_violation_error_on_blocked_access(temp_vault_path, vault_key, sample_profile):
    """Requesting a blocked attribute under a restrictive context raises FieldConsentViolationError."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    vm.save_profile(sample_profile)

    # ATS form context: requesting 'pan' or 'account_number' must raise error
    with pytest.raises(FieldConsentViolationError) as exc_info:
        vm.get_field_with_consent_check("pan", FormContext.ATS_JOB_APPLICATION)
    assert "strictly prohibited" in str(exc_info.value)

    with pytest.raises(FieldConsentViolationError):
        vm.get_field_with_consent_check("account_number", FormContext.ATS_JOB_APPLICATION)

    # Permitted field succeeds
    name = vm.get_field_with_consent_check("full_name", FormContext.ATS_JOB_APPLICATION)
    assert name == "Arjun Sharma"


def test_payment_recipient_context_policy(temp_vault_path, vault_key, sample_profile):
    """Payment Recipient Setup preserves financial info while scrubbing unrelated resume and tax treaty."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    vm.save_profile(sample_profile)

    pay_profile = vm.get_profile(context=FormContext.PAYMENT_RECIPIENT_SETUP)

    # Financial details must be preserved
    assert pay_profile.financial.bank_name == "HDFC Bank"
    assert pay_profile.financial.account_number == "50100234567890"
    assert pay_profile.financial.routing_ifsc == "HDFC0000240"
    assert pay_profile.financial.wise_recipient_id == "wise_recp_98765432"

    # Core identity preserved
    assert pay_profile.core.full_name == "Arjun Sharma"

    # Resume markdown and custom QA pairs scrubbed
    assert pay_profile.career.resume_markdown == ""
    assert pay_profile.career.custom_qa_pairs == {}


def test_vault_corrupted_json_content_fails(temp_vault_path, vault_key):
    """Valid AES envelope with non-JSON payload raises VaultDecryptionError."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=vault_key)
    # Encrypt raw invalid non-json bytes
    envelope = vm.encrypt(b"This is NOT valid JSON data: {[[[[}")
    with open(temp_vault_path, "wb") as f:
        f.write(envelope)

    with pytest.raises(VaultDecryptionError) as exc_info:
        vm.load_profile()
    assert "Failed to parse decrypted profile JSON" in str(exc_info.value)


def test_flatten_profile_convenience_keys(sample_profile):
    """Verify VaultManager.flatten_profile generates complete dictionary including composite address."""
    flat = VaultManager.flatten_profile(sample_profile)
    assert flat["full_name"] == "Arjun Sharma"
    assert flat["email"] == "arjun.sharma@example.com"
    assert flat["pan"] == "ABCDE1234F"
    assert flat["bank_name"] == "HDFC Bank"
    assert "Bengaluru" in flat["address"]
    assert "560038" in flat["address"]

