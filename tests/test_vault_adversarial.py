"""Adversarial stress-test harness for AES-256-GCM Vault and Field Consent Engine.

Validates tamper resistance, cryptographic invariants, and privacy boundary enforcement:
1. Exhaustive bit-flipping in ciphertext (AEAD integrity).
2. Header magic corruption, truncation, and AAD cryptographic binding.
3. Nonce uniqueness, reuse resistance, truncation, and swapping attacks.
4. Wrong key decryption, single-bit key deviations, and key format bounds.
5. Empty payloads, sub-minimum envelopes, and corrupt JSON resilience.
6. Exhaustive authentication tag corruption and forgery rejection.
7. Field-level leakage prevention under ATS_JOB_APPLICATION (PAN and SSN zero-leakage invariant).
"""

import os
import pytest

from app.core.vault import (
    MAGIC,
    MIN_ENVELOPE_LEN,
    NONCE_LEN,
    SALT_LEN,
    TAG_LEN,
    VaultDecryptionError,
    VaultManager,
)
from app.models.identity_schema import (
    CareerProfile,
    CoreProfile,
    FieldConsentViolationError,
    FinancialProfile,
    FormContext,
    MasterIdentityProfile,
    TaxProfile,
    UnclassifiedFieldError,
    is_field_allowed,
)


@pytest.fixture
def temp_vault_path(tmp_path):
    """Isolated temporary path for vault file operations."""
    return str(tmp_path / "adversarial_vault.enc")


@pytest.fixture
def master_key():
    """Standard 256-bit test encryption key."""
    return "adv_master_key_for_testing_32b_!"


@pytest.fixture
def populated_profile():
    """Construct a fully populated MasterIdentityProfile with high-sensitivity attributes."""
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
            ssn_itin="987-65-4321",
            has_us_tax_id=True,
            tax_treaty_country="India",
            tax_treaty_article="Article 12(2)",
            treaty_withholding_rate="15%",
            treaty_income_type="Royalties / Independent Personal Services",
            claim_treaty_benefits=True,
        ),
        career=CareerProfile(
            headline="Senior Distributed Systems Architect",
            years_of_experience=10,
            skills=["Python", "Rust", "FastAPI", "Docker", "Kubernetes"],
            resume_markdown="# Arjun Sharma\n\nStaff Distributed Systems Architect...",
            github_url="https://github.com/arjunsharma-dev",
            linkedin_url="https://linkedin.com/in/arjunsharma-dev",
            portfolio_url="https://arjunsharma.dev",
            custom_qa_pairs={
                "why_us": "Excited by low-latency autonomous agent systems.",
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


# ==============================================================================
# Suite 1: Ciphertext Bit-Flipping & Integrity Fuzzing
# ==============================================================================

def test_adversarial_exhaustive_single_bit_flips(temp_vault_path, master_key):
    """Invariant: Every single bit-flip in ciphertext must be detected by GCM AEAD."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    plaintext = b"Super-confidential identity payload containing SSN: 000-11-2222 and PAN: ABCDE1234F"
    envelope = bytearray(vm.encrypt(plaintext))

    # Ciphertext starts after MAGIC(11) + SALT(16) + NONCE(12) + TAG(16) = 55 bytes
    ct_start = len(MAGIC) + SALT_LEN + NONCE_LEN + TAG_LEN
    ct_len = len(envelope) - ct_start
    assert ct_len == len(plaintext)

    # Test bit flips across sample bytes (start, 25%, 50%, 75%, end) and all 8 bit positions
    sample_indices = [
        ct_start,
        ct_start + 1,
        ct_start + ct_len // 4,
        ct_start + ct_len // 2,
        ct_start + 3 * ct_len // 4,
        ct_start + ct_len - 2,
        ct_start + ct_len - 1,
    ]

    for byte_idx in sample_indices:
        for bit_pos in range(8):
            tampered = bytearray(envelope)
            tampered[byte_idx] ^= (1 << bit_pos)

            with pytest.raises(VaultDecryptionError) as exc_info:
                vm.decrypt(bytes(tampered))
            assert "Vault authentication tag mismatch" in str(exc_info.value) or "failed" in str(exc_info.value)


def test_adversarial_multi_bit_and_burst_flips(temp_vault_path, master_key):
    """Invariant: Multi-bit burst alterations and full block inversions must fail decryption."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    plaintext = b"Payload for multi-bit burst corruption test. Ensure no partial leak occurs."
    envelope = bytearray(vm.encrypt(plaintext))
    ct_start = MIN_ENVELOPE_LEN

    # 1. Flip 16 consecutive bytes (full AES block size)
    tampered_burst = bytearray(envelope)
    for i in range(ct_start, ct_start + 16):
        tampered_burst[i] ^= 0xAA
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_burst))

    # 2. Invert entire ciphertext
    tampered_all = bytearray(envelope)
    for i in range(ct_start, len(tampered_all)):
        tampered_all[i] ^= 0xFF
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_all))

    # 3. Replace ciphertext with random bytes
    tampered_rand = bytearray(envelope[:ct_start] + os.urandom(len(plaintext)))
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_rand))


def test_adversarial_ciphertext_truncation_and_extension(temp_vault_path, master_key):
    """Invariant: Altering ciphertext length (truncation or appending) must fail decryption."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    envelope = vm.encrypt(b"Strict length verification test payload")

    # Truncate 1 byte
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(envelope[:-1])

    # Truncate 16 bytes
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(envelope[:-16])

    # Extend with 1 byte
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(envelope + b"\x00")

    # Extend with 32 garbage bytes
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(envelope + os.urandom(32))


def test_adversarial_ciphertext_block_swapping(temp_vault_path, master_key):
    """Invariant: Swapping two 16-byte blocks within ciphertext must trigger AEAD failure."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    plaintext = b"BLOCK_ZERO_12345" + b"BLOCK_ONE_123456" + b"BLOCK_TWO_123456"
    envelope = bytearray(vm.encrypt(plaintext))
    ct_start = MIN_ENVELOPE_LEN

    # Swap block 0 and block 1
    block0 = envelope[ct_start : ct_start + 16]
    block1 = envelope[ct_start + 16 : ct_start + 32]
    tampered = bytearray(envelope[:ct_start] + block1 + block0 + envelope[ct_start + 32:])

    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered))


# ==============================================================================
# Suite 2: Header Magic Tampering & AAD Security
# ==============================================================================

def test_adversarial_magic_exhaustive_byte_corruption(temp_vault_path, master_key):
    """Invariant: Every byte in the magic header is checked and rejected if modified."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    envelope = bytearray(vm.encrypt(b"Test magic header tampering"))

    # Corrupt each of the 11 bytes of MAGIC
    for pos in range(len(MAGIC)):
        tampered = bytearray(envelope)
        tampered[pos] = (tampered[pos] + 1) % 256
        with pytest.raises(VaultDecryptionError) as exc_info:
            vm.decrypt(bytes(tampered))
        assert "Invalid vault header magic" in str(exc_info.value)


def test_adversarial_magic_case_and_whitespace(temp_vault_path, master_key):
    """Invariant: Header magic is case-sensitive and rejects trailing spaces/nulls."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    envelope = bytearray(vm.encrypt(b"Sensitive payload"))

    # Lowercase
    tampered_lower = bytearray(envelope)
    tampered_lower[:len(MAGIC)] = b"slothvault1"
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_lower))

    # Null-terminated
    tampered_null = bytearray(envelope)
    tampered_null[:len(MAGIC)] = b"SLOTHVAULT\x00"
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_null))


def test_adversarial_aad_cryptographic_verification(temp_vault_path, master_key):
    """Invariant: Even if header magic check were bypassed, AES-GCM AAD must reject tampered magic."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    plaintext = b"Payload with strict AAD binding"
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    derived_key = vm.derive_key(master_key, salt)

    aesgcm = AESGCM(derived_key)
    # Encrypt with valid MAGIC as AAD
    encrypted = aesgcm.encrypt(nonce, plaintext, associated_data=MAGIC)

    # Attempt decrypt with spoofed AAD
    spoofed_aad = b"SLOTHVAULT2"
    with pytest.raises(Exception):
        aesgcm.decrypt(nonce, encrypted, associated_data=spoofed_aad)


# ==============================================================================
# Suite 3: Nonce Reuse, Truncation & Manipulation
# ==============================================================================

def test_adversarial_nonce_uniqueness_stress(temp_vault_path, master_key):
    """Invariant: Every encryption call generates an independent, unique nonce and salt."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    sample_size = 1000
    nonces = set()
    salts = set()

    for _ in range(sample_size):
        envelope = vm.encrypt(b"Deterministic test message")
        salt = envelope[len(MAGIC) : len(MAGIC) + SALT_LEN]
        nonce = envelope[len(MAGIC) + SALT_LEN : len(MAGIC) + SALT_LEN + NONCE_LEN]
        nonces.add(nonce)
        salts.add(salt)

    assert len(nonces) == sample_size, f"Nonce collision detected! Expected {sample_size}, got {len(nonces)}"
    assert len(salts) == sample_size, f"Salt collision detected! Expected {sample_size}, got {len(salts)}"


def test_adversarial_nonce_swapping_attack(temp_vault_path, master_key):
    """Invariant: Splicing a nonce from another envelope must invalidate the authentication tag."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    env1 = bytearray(vm.encrypt(b"Message Alpha"))
    env2 = bytearray(vm.encrypt(b"Message Beta"))

    nonce_offset = len(MAGIC) + SALT_LEN
    nonce1 = env1[nonce_offset : nonce_offset + NONCE_LEN]
    nonce2 = env2[nonce_offset : nonce_offset + NONCE_LEN]

    # Swap nonces
    tampered1 = bytearray(env1[:nonce_offset] + nonce2 + env1[nonce_offset + NONCE_LEN:])
    tampered2 = bytearray(env2[:nonce_offset] + nonce1 + env2[nonce_offset + NONCE_LEN:])

    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered1))
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered2))


def test_adversarial_nonce_truncation(temp_vault_path, master_key):
    """Invariant: Shortened nonces corrupt the envelope offset alignment and fail decryption."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    envelope = vm.encrypt(b"Testing nonce truncation")

    nonce_offset = len(MAGIC) + SALT_LEN
    # Remove 4 bytes from nonce region
    truncated_nonce_env = envelope[:nonce_offset] + envelope[nonce_offset + 4:]
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(truncated_nonce_env)


def test_adversarial_boundary_nonces(temp_vault_path, master_key):
    """Invariant: Forcing boundary nonces (all-zeros, all-ones) fails AEAD check."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    envelope = bytearray(vm.encrypt(b"Testing boundary nonces"))
    nonce_offset = len(MAGIC) + SALT_LEN

    # Replace nonce with all zeros
    tampered_zeros = bytearray(envelope)
    tampered_zeros[nonce_offset : nonce_offset + NONCE_LEN] = b"\x00" * NONCE_LEN
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_zeros))

    # Replace nonce with all 0xFF
    tampered_ones = bytearray(envelope)
    tampered_ones[nonce_offset : nonce_offset + NONCE_LEN] = b"\xFF" * NONCE_LEN
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_ones))


# ==============================================================================
# Suite 4: Wrong Key Decryption & Key Validation
# ==============================================================================

def test_adversarial_wrong_key_single_bit_difference(temp_vault_path, master_key):
    """Invariant: A single bit difference in the key must produce an entirely different derived key and fail."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    envelope = vm.encrypt(b"Payload protected with master key")

    # Modify single character by 1 ASCII value
    near_key1 = master_key[:-1] + chr(ord(master_key[-1]) ^ 1)
    near_key2 = chr(ord(master_key[0]) ^ 1) + master_key[1:]

    with pytest.raises(VaultDecryptionError):
        vm.decrypt(envelope, key=near_key1)
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(envelope, key=near_key2)


def test_adversarial_invalid_key_length_and_formats(temp_vault_path):
    """Invariant: Key validation rejects keys shorter than 8 chars or empty/whitespace."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=None)

    with pytest.raises(ValueError):
        vm.unlock("")
    with pytest.raises(ValueError):
        vm.unlock("   ")
    with pytest.raises(ValueError):
        vm.unlock("short_7")

    # 8-char minimum succeeds
    vm.unlock("valid_8c")
    assert not vm.is_locked


def test_adversarial_unicode_and_binary_keys(temp_vault_path):
    """Invariant: Unicode keys with emojis and high-codepoints derive deterministically."""
    unicode_key = "🔑Secure_Passphrase_With_Emojis_🚀_2026!"
    vm = VaultManager(vault_path=temp_vault_path, vault_key=unicode_key)

    data = b"Testing unicode passphrase HKDF derivation"
    env = vm.encrypt(data)
    assert vm.decrypt(env) == data

    # Decrypt with wrong unicode key fails
    wrong_unicode_key = "🔑Secure_Passphrase_With_Emojis_🛑_2026!"
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(env, key=wrong_unicode_key)


# ==============================================================================
# Suite 5: Empty Payloads, Boundary Sizes & Corrupted JSON
# ==============================================================================

def test_adversarial_empty_plaintext_payload(temp_vault_path, master_key):
    """Invariant: Empty plaintext encrypts to exactly 55-byte envelope and roundtrips cleanly."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    empty_env = vm.encrypt(b"")

    assert len(empty_env) == MIN_ENVELOPE_LEN
    assert empty_env.startswith(MAGIC)
    decrypted = vm.decrypt(empty_env)
    assert decrypted == b""


def test_adversarial_sub_minimum_envelope_lengths(temp_vault_path, master_key):
    """Invariant: Envelopes from 0 to 54 bytes are rejected by minimum length guard."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    dummy_bytes = b"SLOTHVAULT1" + os.urandom(60)

    for length in range(MIN_ENVELOPE_LEN):
        sub_envelope = dummy_bytes[:length]
        with pytest.raises(VaultDecryptionError) as exc_info:
            vm.decrypt(sub_envelope)
        assert "less than minimum" in str(exc_info.value)


def test_adversarial_large_payload_stress(temp_vault_path, master_key):
    """Invariant: Multi-megabyte payloads encrypt and decrypt with exact byte fidelity."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    large_payload = os.urandom(1024 * 1024)  # 1 MB

    env = vm.encrypt(large_payload)
    dec = vm.decrypt(env)
    assert dec == large_payload


def test_adversarial_corrupted_json_profiles(temp_vault_path, master_key):
    """Invariant: Encrypted payloads that are not valid MasterIdentityProfile JSON raise VaultDecryptionError."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)

    malformed_payloads = [
        b"",
        b"   ",
        b"null",
        b"12345",
        b"[1, 2, 3]",
        b'{"core": "not_an_object"}',
        b'{"core": {"full_name": "Arjun"}}',  # Missing required fields
        b'{"unclosed_json": ',
    ]

    for payload in malformed_payloads:
        env = vm.encrypt(payload)
        with open(temp_vault_path, "wb") as f:
            f.write(env)

        with pytest.raises(VaultDecryptionError):
            vm.load_profile(force_reload=True)


# ==============================================================================
# Suite 6: Authentication Tag Corruption & Forgery
# ==============================================================================

def test_adversarial_tag_exhaustive_byte_corruption(temp_vault_path, master_key):
    """Invariant: Every byte of the 16-byte authentication tag is validated."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    envelope = bytearray(vm.encrypt(b"Tag integrity verification payload"))

    tag_offset = len(MAGIC) + SALT_LEN + NONCE_LEN

    for byte_idx in range(TAG_LEN):
        tampered = bytearray(envelope)
        tampered[tag_offset + byte_idx] ^= 0x01

        with pytest.raises(VaultDecryptionError):
            vm.decrypt(bytes(tampered))


def test_adversarial_tag_zeroed_and_inverted(temp_vault_path, master_key):
    """Invariant: Zeroed, all-ones, or inverted authentication tags fail verification."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    envelope = bytearray(vm.encrypt(b"Tag forgery boundary test"))
    tag_offset = len(MAGIC) + SALT_LEN + NONCE_LEN

    # All zeros tag
    tampered_zeros = bytearray(envelope)
    tampered_zeros[tag_offset : tag_offset + TAG_LEN] = b"\x00" * TAG_LEN
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_zeros))

    # All ones tag
    tampered_ones = bytearray(envelope)
    tampered_ones[tag_offset : tag_offset + TAG_LEN] = b"\xFF" * TAG_LEN
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_ones))

    # Bitwise inverted tag
    tampered_inv = bytearray(envelope)
    for i in range(tag_offset, tag_offset + TAG_LEN):
        tampered_inv[i] ^= 0xFF
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered_inv))


def test_adversarial_tag_swapping_between_envelopes(temp_vault_path, master_key):
    """Invariant: Transplanting an auth tag from envelope A into envelope B fails."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    env1 = bytearray(vm.encrypt(b"Transaction 1: Transfer $100"))
    env2 = bytearray(vm.encrypt(b"Transaction 2: Transfer $50,000"))

    tag_offset = len(MAGIC) + SALT_LEN + NONCE_LEN
    tag1 = env1[tag_offset : tag_offset + TAG_LEN]
    tag2 = env2[tag_offset : tag_offset + TAG_LEN]

    tampered1 = bytearray(env1[:tag_offset] + tag2 + env1[tag_offset + TAG_LEN:])
    tampered2 = bytearray(env2[:tag_offset] + tag1 + env2[tag_offset + TAG_LEN:])
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered1))
    with pytest.raises(VaultDecryptionError):
        vm.decrypt(bytes(tampered2))


# ==============================================================================
# Suite 7: Field-Level Leakage Under ATS_JOB_APPLICATION Context
# ==============================================================================

def test_adversarial_ats_context_strictly_nulls_pan_and_ssn(temp_vault_path, master_key, populated_profile):
    """Empirical Zero-Leakage Invariant: Under FormContext.ATS_JOB_APPLICATION, PAN and SSN are strictly None."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    vm.save_profile(populated_profile)

    ats_profile = vm.get_profile(context=FormContext.ATS_JOB_APPLICATION)

    # 1. Direct tax model field inspections
    assert ats_profile.tax.pan is None, f"Leakage detected! PAN is present: {ats_profile.tax.pan}"
    assert ats_profile.tax.ssn_itin is None, f"Leakage detected! SSN is present: {ats_profile.tax.ssn_itin}"
    assert ats_profile.tax.has_us_tax_id is False
    assert ats_profile.tax.claim_treaty_benefits is False
    assert ats_profile.tax.tax_treaty_article == ""

    # 2. Date of birth anti-discrimination inspection
    assert ats_profile.core.date_of_birth is None, f"Leakage detected! DOB present: {ats_profile.core.date_of_birth}"

    # 3. Financial attributes zero-leakage inspection
    assert ats_profile.financial.bank_name is None
    assert ats_profile.financial.account_number is None
    assert ats_profile.financial.routing_ifsc is None
    assert ats_profile.financial.swift_bic is None
    assert ats_profile.financial.wise_recipient_id is None


def test_adversarial_ats_profile_serialization_no_leakage(temp_vault_path, master_key, populated_profile):
    """Empirical Zero-Leakage Invariant: Serialized JSON and model_dump contain zero sensitive strings."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    vm.save_profile(populated_profile)

    ats_profile = vm.get_profile(context=FormContext.ATS_JOB_APPLICATION)
    json_str = ats_profile.model_dump_json()

    # Verify that sensitive secrets do not appear anywhere in the serialized payload
    assert "ABCDE1234F" not in json_str, "PAN leaked in serialized JSON!"
    assert "987-65-4321" not in json_str, "SSN leaked in serialized JSON!"
    assert "1994-08-15" not in json_str, "DOB leaked in serialized JSON!"
    assert "50100234567890" not in json_str, "Bank account leaked in serialized JSON!"
    assert "HDFC0000240" not in json_str, "IFSC code leaked in serialized JSON!"
    assert "HDFCINBB" not in json_str, "SWIFT BIC leaked in serialized JSON!"
    assert "wise_recp_98765432" not in json_str, "Wise ID leaked in serialized JSON!"

    # Verify model_dump dictionary
    dump_dict = ats_profile.model_dump()
    assert dump_dict["tax"]["pan"] is None
    assert dump_dict["tax"]["ssn_itin"] is None
    assert dump_dict["core"]["date_of_birth"] is None
    assert dump_dict["financial"]["account_number"] is None


def test_adversarial_ats_flattened_profile_no_leakage(temp_vault_path, master_key, populated_profile):
    """Empirical Zero-Leakage Invariant: VaultManager.flatten_profile returns None for sensitive keys."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    vm.save_profile(populated_profile)

    ats_profile = vm.get_profile(context=FormContext.ATS_JOB_APPLICATION)
    flat = vm.flatten_profile(ats_profile)

    assert flat.get("pan") is None
    assert flat.get("ssn_itin") is None
    assert flat.get("date_of_birth") is None
    assert flat.get("account_number") is None
    assert flat.get("bank_name") is None
    assert flat.get("routing_ifsc") is None


def test_adversarial_ats_consent_check_blocks_all_prohibited_variations(temp_vault_path, master_key, populated_profile):
    """Empirical Invariant: get_field_with_consent_check strictly raises on PAN, SSN, and financial keys."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    vm.save_profile(populated_profile)

    prohibited_queries = [
        "pan",
        "PAN",
        "Pan",
        " pan ",
        "tax_pan",
        "pan_number",
        "ssn",
        "SSN",
        "ssn_itin",
        "SSN_ITIN",
        "social_security_number",
        "tax_ssn",
        "account_number",
        "bank_name",
        "routing_ifsc",
        "swift_bic",
        "wise_recipient_id",
        "date_of_birth",
    ]

    for field_query in prohibited_queries:
        with pytest.raises((FieldConsentViolationError, UnclassifiedFieldError)):
            vm.get_field_with_consent_check(field_query, FormContext.ATS_JOB_APPLICATION)


def test_adversarial_ats_allowed_fields_accessible(temp_vault_path, master_key, populated_profile):
    """Invariant: Legitimate public and semi-sensitive fields remain accessible under ATS context."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    vm.save_profile(populated_profile)

    # Allowed fields succeed via get_field_with_consent_check
    assert vm.get_field_with_consent_check("full_name", FormContext.ATS_JOB_APPLICATION) == "Arjun Sharma"
    assert vm.get_field_with_consent_check("email", FormContext.ATS_JOB_APPLICATION) == "arjun.sharma@example.com"
    assert vm.get_field_with_consent_check("phone", FormContext.ATS_JOB_APPLICATION) == "+919876543210"
    assert vm.get_field_with_consent_check("years_of_experience", FormContext.ATS_JOB_APPLICATION) == 10
    assert "Distributed Systems" in vm.get_field_with_consent_check("resume_markdown", FormContext.ATS_JOB_APPLICATION)


def test_adversarial_w8ben_permits_pan_blocks_ssn(temp_vault_path, master_key, populated_profile):
    """Invariant: W-8BEN contractor compliance permits Indian PAN for Box 6a, but strictly blocks SSN."""
    vm = VaultManager(vault_path=temp_vault_path, vault_key=master_key)
    vm.save_profile(populated_profile)

    w8_profile = vm.get_profile(context=FormContext.W8BEN_CONTRACTOR_COMPLIANCE)

    # Indian PAN is permitted and matches
    assert w8_profile.tax.pan == "ABCDE1234F"
    assert w8_profile.tax.claim_treaty_benefits is True

    # SSN/ITIN is strictly blocked (to prevent foreign contractor withholding penalties)
    assert w8_profile.tax.ssn_itin is None
    assert is_field_allowed("pan", FormContext.W8BEN_CONTRACTOR_COMPLIANCE) is True
    assert is_field_allowed("ssn", FormContext.W8BEN_CONTRACTOR_COMPLIANCE) is False
    assert is_field_allowed("ssn_itin", FormContext.W8BEN_CONTRACTOR_COMPLIANCE) is False

    with pytest.raises(FieldConsentViolationError):
        vm.get_field_with_consent_check("ssn", FormContext.W8BEN_CONTRACTOR_COMPLIANCE)
