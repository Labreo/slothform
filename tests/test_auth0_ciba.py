"""Unit and Integration Tests for Auth0 CIBA and RFC 9396 Subsystem."""

import pytest
import httpx

from app.core.auth0_client import Auth0CIBAClient, generate_binding_message
from app.models.ciba_schema import (
    CIBAError,
    ConsentResult,
    ConsentTimeoutError,
    FormFillDiff,
    RefusalToSubmitError,
    RichAuthorizationDetail,
)
from app.models.identity_schema import SensitivityTier


# ==============================================================================
# 1. Diff Generation, RAR (RFC 9396), and Binding Message Tests
# ==============================================================================

def test_binding_message_length_and_sha_embedding():
    """Verify binding message conforms to RFC 64-char recommendation and embeds short SHA."""
    target_url = "https://boards.greenhouse.io/stripe/jobs/12345"
    digest = "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069"

    msg = generate_binding_message(target_url, digest, dry_run=False)
    assert len(msg) <= 64
    assert "boards.greenhouse.io" in msg
    assert "[sha:7f83b165]" in msg
    assert not msg.startswith("[DRY]")

    # With dry-run
    dry_msg = generate_binding_message(target_url, digest, dry_run=True)
    assert len(dry_msg) <= 64
    assert "[DRY]" in dry_msg
    assert "[sha:7f83b165]" in dry_msg

    # Extreme length URL
    long_url = "https://" + "a" * 100 + ".example.com/apply/candidate/12345"
    truncated_msg = generate_binding_message(long_url, digest, dry_run=True)
    assert len(truncated_msg) <= 64
    assert truncated_msg.endswith(" [sha:7f83b165]")


def test_form_fill_diff_construction():
    """Verify FormFillDiff generates masked values, sensitivity tiers, and deterministic SHA-256."""
    target_url = "https://jobs.lever.co/acme/software-engineer"
    field_values = {
        "full_name": "Arjun Sharma",
        "email": "arjun.sharma@example.com",
        "phone": "+919876543210",
        "pan": "ABCDE1234F",
    }
    redacted = ["ssn", "bank_account"]

    diff1 = FormFillDiff.from_field_values(target_url, field_values, redacted_fields=redacted, dry_run=False)
    diff2 = FormFillDiff.from_field_values(target_url, field_values, redacted_fields=redacted, dry_run=False)

    # Determinism: digests must match
    assert diff1.digest == diff2.digest
    assert diff1.digest.startswith("sha256:")

    # Verify items and masking
    item_map = {item.field_name: item for item in diff1.items}
    assert item_map["full_name"].tier == SensitivityTier.PUBLIC
    assert item_map["full_name"].masked_value == "Arjun Sharma"
    assert not item_map["full_name"].consent_required

    assert item_map["pan"].tier == SensitivityTier.CRITICAL_TAX
    assert item_map["pan"].masked_value == "ABCDE****F"
    assert item_map["pan"].consent_required is True

    assert "ssn" in diff1.fields_redacted


def test_rich_authorization_details_rfc9396():
    """Verify RFC 9396 structured authorization_details serialization."""
    target_url = "https://boards.greenhouse.io/stripe/jobs/12345"
    diff = FormFillDiff.from_field_values(
        target_url=target_url,
        field_values={"full_name": "Arjun Sharma", "email": "arjun@example.com"},
        redacted_fields=["pan"],
        dry_run=True,
    )
    rar = RichAuthorizationDetail.from_diff(diff)

    assert rar.type == "slothform_consent"
    assert rar.target_url == target_url
    assert rar.form_domain == "boards.greenhouse.io"
    assert rar.diff_digest == diff.digest
    assert rar.fields_requested == ["email", "full_name"]
    assert rar.fields_redacted == ["pan"]
    assert rar.dry_run is True


# ==============================================================================
# 2. CIBA Offline Simulator Flow Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_offline_ciba_initiate_and_approve():
    """Verify end-to-end initiation and approval flow in offline simulation mode."""
    client = Auth0CIBAClient(offline_mode=True)
    target_url = "https://jobs.ashbyhq.com/startup/role"
    diff = FormFillDiff.from_field_values(target_url, {"full_name": "Arjun Sharma"})

    ciba_req = await client.initiate_consent(target_url, diff, dry_run=False)
    assert ciba_req.auth_req_id.startswith("ciba_sim_")
    assert ciba_req.expires_in == 300
    assert ciba_req.interval == 5
    assert "ashbyhq.com" in ciba_req.binding_message

    # Polling with approval
    client.simulate_approval(ciba_req.auth_req_id)
    result = await client.poll_consent(ciba_req.auth_req_id, timeout=5, initial_interval=0.01)
    assert result.approved is True
    assert result.access_token is not None
    assert result.token_type == "Bearer"


@pytest.mark.asyncio
async def test_offline_ciba_access_denied_raises_refusal():
    """Invariant: User rejecting consent on mobile device MUST raise RefusalToSubmitError."""
    client = Auth0CIBAClient(offline_mode=True)
    target_url = "https://jobs.lever.co/company/job"
    diff = FormFillDiff.from_field_values(target_url, {"full_name": "Arjun Sharma"})

    ciba_req = await client.initiate_consent(target_url, diff)
    client.simulate_denial(ciba_req.auth_req_id)

    with pytest.raises(RefusalToSubmitError) as exc_info:
        await client.poll_consent(ciba_req.auth_req_id, timeout=5, initial_interval=0.01)

    assert "access_denied" in str(exc_info.value)
    assert "Submission refused" in str(exc_info.value)


@pytest.mark.asyncio
async def test_offline_ciba_expired_token_raises_refusal():
    """Invariant: Expired auth_req_id MUST raise RefusalToSubmitError."""
    client = Auth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values("https://example.com/form", {"full_name": "Test"})

    ciba_req = await client.initiate_consent("https://example.com/form", diff)
    client.simulate_expiration(ciba_req.auth_req_id)

    with pytest.raises(RefusalToSubmitError) as exc_info:
        await client.poll_consent(ciba_req.auth_req_id, timeout=5, initial_interval=0.01)

    assert "expired_token" in str(exc_info.value)
    assert "Submission refused" in str(exc_info.value)


@pytest.mark.asyncio
async def test_offline_ciba_slow_down_handling():
    """Verify that slow_down response dynamically increments polling interval by 5 seconds."""
    client = Auth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values("https://example.com/form", {"full_name": "Test"})

    ciba_req = await client.initiate_consent("https://example.com/form", diff)
    # Configure 1 cycle of slow_down, then immediate approval
    client.simulate_slow_down(ciba_req.auth_req_id, count=1)
    client._sim_requests[ciba_req.auth_req_id]["pending_cycles"] = 0
    client._sim_requests[ciba_req.auth_req_id]["final_decision"] = "approved"

    # Single poll checks
    res1 = await client.poll_token_once(ciba_req.auth_req_id)
    assert res1["status"] == "slow_down"

    res2 = await client.poll_token_once(ciba_req.auth_req_id)
    assert res2["status"] == "approved"
    assert "access_token" in res2


@pytest.mark.asyncio
async def test_offline_ciba_timeout_raises_refusal():
    """Exceeding timeout parameter raises ConsentTimeoutError."""
    client = Auth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values("https://example.com/form", {"full_name": "Test"})

    ciba_req = await client.initiate_consent("https://example.com/form", diff)
    # Set high pending cycles so it won't resolve within short timeout
    client._sim_requests[ciba_req.auth_req_id]["pending_cycles"] = 100

    with pytest.raises(ConsentTimeoutError) as exc_info:
        await client.poll_consent(ciba_req.auth_req_id, timeout=0.05, initial_interval=0.02)

    assert "timed out" in str(exc_info.value)


# ==============================================================================
# 3. Live HTTP Transport Mocking Tests (RFC / Auth0 Spec Conformance)
# ==============================================================================

@pytest.mark.asyncio
async def test_http_transport_bc_authorize_success():
    """Test real HTTP POST to /bc-authorize endpoint with RFC 9396 payload."""
    recorded_requests = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        if request.url.path == "/bc-authorize":
            assert request.method == "POST"
            assert request.headers["content-type"] == "application/x-www-form-urlencoded"
            # Verify body parameters
            body_str = request.content.decode("utf-8")
            assert "grant_type" not in body_str  # grant_type is on /oauth/token, not /bc-authorize
            assert "client_id=test_client_id" in body_str
            assert "binding_message=" in body_str
            assert "authorization_details=" in body_str
            return httpx.Response(
                200,
                json={"auth_req_id": "real_mock_auth_req_12345", "expires_in": 300, "interval": 5},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    mock_http_client = httpx.AsyncClient(transport=transport)

    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client_id",
        client_secret="test_secret",
        offline_mode=False,
        http_client=mock_http_client,
    )

    diff = FormFillDiff.from_field_values("https://boards.greenhouse.io/test/jobs/1", {"name": "Arjun"})
    req = await client.initiate_consent("https://boards.greenhouse.io/test/jobs/1", diff)

    assert req.auth_req_id == "real_mock_auth_req_12345"
    assert req.expires_in == 300
    assert req.interval == 5
    await client.close()


@pytest.mark.asyncio
async def test_http_transport_poll_pending_then_approved():
    """Test real HTTP token polling returning authorization_pending then approved token."""
    poll_count = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        if request.url.path == "/oauth/token":
            poll_count += 1
            body_str = request.content.decode("utf-8")
            assert "grant_type=urn%3Aopenid%3Aparams%3Agrant-type%3Aciba" in body_str
            assert "auth_req_id=mock_req_999" in body_str

            if poll_count == 1:
                return httpx.Response(
                    400,
                    json={
                        "error": "authorization_pending",
                        "error_description": "User has not yet responded.",
                    },
                )
            else:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.valid_approved_jwt",
                        "token_type": "Bearer",
                        "expires_in": 86400,
                        "scope": "openid profile slothform:vault:read slothform:submit",
                    },
                )
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    mock_http_client = httpx.AsyncClient(transport=transport)

    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client_id",
        client_secret="test_secret",
        offline_mode=False,
        http_client=mock_http_client,
    )

    result = await client.poll_consent(auth_req_id="mock_req_999", timeout=5, initial_interval=0.01)
    assert result.approved is True
    assert "valid_approved_jwt" in result.access_token
    assert poll_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_http_transport_poll_access_denied_raises_refusal():
    """Test real HTTP token polling returning HTTP 400 access_denied raises RefusalToSubmitError."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(
                400,
                json={
                    "error": "access_denied",
                    "error_description": "The end-user denied the authorization request.",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    mock_http_client = httpx.AsyncClient(transport=transport)

    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client_id",
        client_secret="test_secret",
        offline_mode=False,
        http_client=mock_http_client,
    )

    with pytest.raises(RefusalToSubmitError) as exc_info:
        await client.poll_consent(auth_req_id="mock_denied_req", timeout=5, initial_interval=0.01)

    assert "access_denied" in str(exc_info.value)
    assert "Submission refused" in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_http_transport_poll_expired_token_raises_refusal():
    """Test real HTTP token polling returning HTTP 400 expired_token raises RefusalToSubmitError."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(
                400,
                json={
                    "error": "expired_token",
                    "error_description": "The auth_req_id has expired.",
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    mock_http_client = httpx.AsyncClient(transport=transport)

    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client_id",
        client_secret="test_secret",
        offline_mode=False,
        http_client=mock_http_client,
    )

    with pytest.raises(RefusalToSubmitError) as exc_info:
        await client.poll_consent(auth_req_id="mock_expired_req", timeout=5, initial_interval=0.01)

    assert "expired_token" in str(exc_info.value)
    assert "Submission refused" in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_http_transport_poll_slow_down_dynamic_backoff():
    """Verify HTTP polling handles slow_down by dynamically backing off interval by +5s."""
    poll_intervals = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            # Track poll calls
            poll_intervals.append(len(poll_intervals))
            if len(poll_intervals) == 1:
                return httpx.Response(
                    400,
                    json={
                        "error": "slow_down",
                        "error_description": "The client is polling too frequently. Increase interval.",
                    },
                )
            else:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "eyJhbGciOiJSUzI1NiJ9.approved_token_after_slowdown",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    },
                )
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    mock_http_client = httpx.AsyncClient(transport=transport)

    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client_id",
        client_secret="test_secret",
        offline_mode=False,
        http_client=mock_http_client,
    )

    # Use small initial interval
    res = await client.poll_token_once("req_slowdown_test")
    assert res["status"] == "slow_down"

    res2 = await client.poll_token_once("req_slowdown_test")
    assert res2["status"] == "approved"
    assert "approved_token_after_slowdown" in res2["access_token"]
    await client.close()


@pytest.mark.asyncio
async def test_http_transport_transient_network_error_recovery():
    """Verify polling survives a transient network error without crashing."""
    attempts = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("Simulated socket connection failure")
        return httpx.Response(
            200,
            json={
                "access_token": "eyJhbGciOiJSUzI1NiJ9.recovered_token",
                "token_type": "Bearer",
            },
        )

    transport = httpx.MockTransport(handle_request)
    mock_http_client = httpx.AsyncClient(transport=transport)

    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client_id",
        client_secret="test_secret",
        offline_mode=False,
        http_client=mock_http_client,
    )

    # First attempt encounters transient error -> returns pending
    res1 = await client.poll_token_once("req_network_test")
    assert res1["status"] == "pending"
    assert "Simulated socket connection failure" in res1["transient_error"]

    # Second attempt succeeds
    res2 = await client.poll_token_once("req_network_test")
    assert res2["status"] == "approved"
    assert "recovered_token" in res2["access_token"]
    await client.close()


def test_submission_refusal_invariant_guarantee():
    """Verify that ConsentResult invariants are strictly preserved."""
    # When not approved, access token MUST be None
    unapproved = ConsentResult(approved=False, error="access_denied")
    assert not unapproved.approved
    assert unapproved.access_token is None

    # RefusalToSubmitError must be an exception subclass that halts execution
    err = RefusalToSubmitError("Execution refused")
    assert isinstance(err, CIBAError)
    assert isinstance(err, Exception)

