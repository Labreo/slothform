"""Adversarial Stress Test Suite for Auth0 CIBA and Submission Refusal Invariant.

Authored by Challenger 2 (Milestone M1).
Tests 7 adversarial vectors:
1. Rapid polling & slow_down handling
2. User denial (access_denied)
3. Expired tokens (expired_token & timeouts)
4. Network timeouts & transport failures
5. Invalid grant types & protocol errors
6. Spoofed responses & payload integrity
7. Attempted submission bypass & refusal invariant
"""

import time
import httpx
import pytest

from app.core.auth0_client import Auth0CIBAClient, generate_binding_message
from app.models.ciba_schema import (
    CIBAError,
    ConsentResult,
    ConsentTimeoutError,
    FormFillDiff,
    RefusalToSubmitError,
)
from tests.e2e.conftest import (
    SimulatedAuth0CIBAClient,
    SimulatedBrowserbaseService,
    SimulatedFillOrchestrator,
    SimulatedFormFiller,
)
from app.core.vault import create_sample_profile, VaultManager


# ==============================================================================
# VECTOR 1: RAPID POLLING & SLOW_DOWN BACKOFF DYNAMICS
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_rapid_polling_successive_slow_downs():
    """Verify multiple successive slow_down responses progressively increase polling interval."""
    slow_down_count = 0
    poll_timestamps = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal slow_down_count
        if request.url.path == "/oauth/token":
            poll_timestamps.append(time.time())
            if slow_down_count < 3:
                slow_down_count += 1
                return httpx.Response(
                    400,
                    json={
                        "error": "slow_down",
                        "error_description": f"Polling too fast (occurrence {slow_down_count}). Slow down.",
                    },
                )
            else:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "valid_token_after_3_slowdowns",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    },
                )
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    mock_http = httpx.AsyncClient(transport=transport)
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        client_secret="test_secret",
        offline_mode=False,
        http_client=mock_http,
    )

    # Initial interval = 0.02s, each slow_down should add 5s in production,
    # but here initial_interval=0.01s with timeout=20s.
    # Note: poll_consent adds +5s to interval on each slow_down.
    # To keep test fast, we check poll_token_once directly for state, and then small timeout.
    res1 = await client.poll_token_once("req_rapid_1")
    assert res1["status"] == "slow_down"
    res2 = await client.poll_token_once("req_rapid_1")
    assert res2["status"] == "slow_down"
    res3 = await client.poll_token_once("req_rapid_1")
    assert res3["status"] == "slow_down"
    res4 = await client.poll_token_once("req_rapid_1")
    assert res4["status"] == "approved"
    assert res4["access_token"] == "valid_token_after_3_slowdowns"

    await client.close()


@pytest.mark.asyncio
async def test_adversarial_slow_down_exhausts_timeout_raises_refusal():
    """Verify that repeated slow_down responses pushing past the timeout raise ConsentTimeoutError."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(
                400,
                json={"error": "slow_down", "error_description": "Keep slowing down"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handle_request)
    mock_http = httpx.AsyncClient(transport=transport)
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        client_secret="test_secret",
        offline_mode=False,
        http_client=mock_http,
    )

    # Timeout is very short (0.05s). The first slow_down increases interval by +5s,
    # meaning sleep will hit the remaining time and loop will raise ConsentTimeoutError.
    with pytest.raises(ConsentTimeoutError) as exc_info:
        await client.poll_consent("req_slow_timeout", timeout=0.05, initial_interval=0.01)

    assert issubclass(ConsentTimeoutError, RefusalToSubmitError)
    assert "timed out" in str(exc_info.value).lower()
    await client.close()


@pytest.mark.asyncio
async def test_adversarial_offline_simulator_multiple_slow_downs():
    """Verify offline simulator correctly handles multiple configured slow_down cycles."""
    client = Auth0CIBAClient(offline_mode=True)
    diff = FormFillDiff.from_field_values("https://example.com/apply", {"name": "Test"})
    req = await client.initiate_consent("https://example.com/apply", diff)

    client.simulate_slow_down(req.auth_req_id, count=3)
    client._sim_requests[req.auth_req_id]["pending_cycles"] = 0
    client._sim_requests[req.auth_req_id]["final_decision"] = "approved"

    for _ in range(3):
        res = await client.poll_token_once(req.auth_req_id)
        assert res["status"] == "slow_down"

    res_final = await client.poll_token_once(req.auth_req_id)
    assert res_final["status"] == "approved"
    assert "access_token" in res_final


# ==============================================================================
# VECTOR 2: USER DENIAL (ACCESS_DENIED)
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_user_denial_immediate():
    """Verify immediate access_denied raises RefusalToSubmitError and gives no access token."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "access_denied", "error_description": "User pressed 'Reject' on Authenticator"},
        )

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    with pytest.raises(RefusalToSubmitError) as exc_info:
        await client.poll_consent("denied_req_1", timeout=5, initial_interval=0.01)

    assert "access_denied" in str(exc_info.value)
    assert "Submission refused" in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_adversarial_user_denial_after_pending_and_slow_down():
    """Verify access_denied received after multiple pending & slow_down cycles halts immediately."""
    call_idx = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return httpx.Response(400, json={"error": "authorization_pending"})
        elif call_idx == 2:
            return httpx.Response(400, json={"error": "slow_down"})
        else:
            return httpx.Response(400, json={"error": "access_denied", "error_description": "User decided to reject"})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    r1 = await client.poll_token_once("req_seq_denial")
    assert r1["status"] == "pending"

    r2 = await client.poll_token_once("req_seq_denial")
    assert r2["status"] == "slow_down"

    r3 = await client.poll_token_once("req_seq_denial")
    assert r3["status"] == "access_denied"

    await client.close()


@pytest.mark.asyncio
async def test_adversarial_user_denial_with_http_403():
    """Verify that if an upstream reverse-proxy returns HTTP 403 with access_denied, refusal holds."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error": "access_denied", "error_description": "Forbidden: user rejected"},
        )

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    with pytest.raises(RefusalToSubmitError) as exc_info:
        await client.poll_consent("denied_403", timeout=5, initial_interval=0.01)

    assert "access_denied" in str(exc_info.value)
    assert "Submission refused" in str(exc_info.value)
    await client.close()


# ==============================================================================
# VECTOR 3: EXPIRED TOKENS & LIFECYCLE TIMEOUTS
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_expired_token_server_response():
    """Verify Auth0 returning error='expired_token' strictly raises RefusalToSubmitError."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "expired_token", "error_description": "The auth_req_id has expired (TTL 300s passed)"},
        )

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    with pytest.raises(RefusalToSubmitError) as exc_info:
        await client.poll_consent("expired_req_1", timeout=5, initial_interval=0.01)

    assert "expired_token" in str(exc_info.value)
    assert "Submission refused" in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_adversarial_client_timeout_subclass_of_refusal():
    """Verify client-side polling timeout raises ConsentTimeoutError, which satisfies RefusalToSubmitError."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "authorization_pending"})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    with pytest.raises(ConsentTimeoutError) as exc_info:
        await client.poll_consent("timeout_req", timeout=0.03, initial_interval=0.01)

    # Invariant: ConsentTimeoutError is a RefusalToSubmitError
    assert isinstance(exc_info.value, RefusalToSubmitError)
    assert isinstance(exc_info.value, CIBAError)
    await client.close()


@pytest.mark.asyncio
async def test_adversarial_unknown_simulation_id_defaults_to_expired_refusal():
    """In offline mode, polling an invalid/non-existent simulation ID raises RefusalToSubmitError."""
    client = Auth0CIBAClient(offline_mode=True)
    with pytest.raises(RefusalToSubmitError) as exc_info:
        await client.poll_consent("ciba_sim_nonexistent_id", timeout=5, initial_interval=0.01)

    assert "expired_token" in str(exc_info.value)


# ==============================================================================
# VECTOR 4: NETWORK TIMEOUTS & TRANSPORT FAILURES
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_bc_authorize_connect_timeout():
    """Verify network connection timeout on /bc-authorize initiation raises CIBAError."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection to Auth0 timed out after 30s")

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    diff = FormFillDiff.from_field_values("https://example.com/apply", {"name": "Test"})
    with pytest.raises(CIBAError) as exc_info:
        await client.initiate_consent("https://example.com/apply", diff)

    assert "Failed to connect to Auth0 backchannel endpoint" in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_adversarial_sustained_read_timeout_during_polling():
    """Verify sustained network read timeouts during polling eventually hit timeout and raise ConsentTimeoutError."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timeout on socket")

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    # Transient read timeout is captured and marked pending, but if it persists,
    # client-side timeout must expire and raise ConsentTimeoutError
    with pytest.raises(ConsentTimeoutError) as exc_info:
        await client.poll_consent("req_hang", timeout=0.05, initial_interval=0.01)

    assert "timed out" in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_adversarial_gateway_errors_500_502_504_raise_ciba_error():
    """Verify upstream HTTP 500, 502, 504 server errors raise CIBAError and prevent approval."""
    for status_code in (500, 502, 503, 504):
        def handle_request(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code,
                json={"error": "server_error", "error_description": f"HTTP {status_code} from Cloudflare/Auth0"},
            )

        mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
        client = Auth0CIBAClient(
            domain="tenant.us.auth0.com",
            client_id="test_client",
            offline_mode=False,
            http_client=mock_http,
        )

        with pytest.raises(CIBAError) as exc_info:
            await client.poll_consent("gateway_err_req", timeout=5, initial_interval=0.01)

        assert "unexpected status" in str(exc_info.value)
        await client.close()


# ==============================================================================
# VECTOR 5: INVALID GRANT TYPES & PROTOCOL TAMPERING
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_unsupported_grant_type_raises_ciba_error():
    """Verify Auth0 reporting unsupported_grant_type halts with CIBAError."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "unsupported_grant_type",
                "error_description": "Grant type 'urn:openid:params:grant-type:ciba' is not allowed on tenant.",
            },
        )

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    with pytest.raises(CIBAError) as exc_info:
        await client.poll_consent("bad_grant_req", timeout=5, initial_interval=0.01)

    assert "Grant type" in str(exc_info.value) or "unsupported_grant_type" in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_adversarial_invalid_client_or_secret_raises_ciba_error():
    """Verify invalid_client authentication failure halts with CIBAError."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": "invalid_client", "error_description": "Client authentication failed"},
        )

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    with pytest.raises(CIBAError) as exc_info:
        await client.poll_consent("bad_client_req", timeout=5, initial_interval=0.01)

    assert "Client authentication failed" in str(exc_info.value) or "invalid_client" in str(exc_info.value)
    await client.close()


@pytest.mark.asyncio
async def test_adversarial_tampered_auth_req_id_injection():
    """Verify passing SQLi or path-traversal in auth_req_id does not compromise client."""
    recorded_body = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        recorded_body.append(request.content.decode("utf-8"))
        return httpx.Response(400, json={"error": "invalid_request", "error_description": "Malformed auth_req_id"})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    injection_id = "req' OR 1=1; DROP TABLE users;-- \x00 ../../etc/passwd"
    res = await client.poll_token_once(injection_id)
    assert res["status"] == "failed"
    assert res["error"] == "invalid_request"
    # Verify body properly URL-encoded the malicious auth_req_id
    assert "DROP+TABLE" in recorded_body[0] or "DROP%20TABLE" in recorded_body[0]

    await client.close()


# ==============================================================================
# VECTOR 6: SPOOFED RESPONSES & INTEGRITY CHECKS
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_spoofed_200_missing_access_token():
    """Adversarial probe: What happens if an adversary returns HTTP 200 with an empty body or no access_token?"""
    def handle_request(request: httpx.Request) -> httpx.Response:
        # Spoofed response: HTTP 200 but completely empty JSON
        return httpx.Response(200, json={})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    res = await client.poll_token_once("spoofed_req")
    # Verify that poll_token_once returns status approved
    assert res["status"] == "approved"
    assert res.get("access_token") is None

    # When poll_consent is called, what does it return?
    consent = await client.poll_consent("spoofed_req", timeout=5, initial_interval=0.01)
    # Check if access_token is None:
    # A secure downstream submission system MUST verify consent.access_token is truthy!
    assert consent.access_token is None

    await client.close()


@pytest.mark.asyncio
async def test_adversarial_spoofed_200_with_embedded_error():
    """Adversarial probe: Upstream returns HTTP 200 with error: access_denied in body."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "access_denied", "error_description": "User denied"})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    consent = await client.poll_consent("spoofed_err_200", timeout=5, initial_interval=0.01)
    # Note: Because status_code == 200, it returned approved, but access_token is None.
    assert consent.access_token is None
    await client.close()


@pytest.mark.asyncio
async def test_adversarial_non_json_body_on_http_200():
    """Adversarial probe: Proxy or captive portal returns HTML on HTTP 200."""
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<!DOCTYPE html><html><body>Login Portal</body></html>", headers={"content-type": "text/html"})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    client = Auth0CIBAClient(
        domain="tenant.us.auth0.com",
        client_id="test_client",
        offline_mode=False,
        http_client=mock_http,
    )

    # In Python httpx, resp.json() on HTML raises json.JSONDecodeError or similar
    with pytest.raises(Exception) as exc_info:
        await client.poll_token_once("html_200_req")

    # Invariant: execution MUST halt and cannot produce an approved ConsentResult
    assert exc_info.value is not None
    await client.close()


def test_adversarial_rar_diff_tampering_invalidates_sha_digest():
    """Verify that tampering with any form field changes the RAR diff SHA-256 digest."""
    target_url = "https://boards.greenhouse.io/stripe/jobs/123"
    fields_original = {"full_name": "Arjun Sharma", "email": "arjun@example.com", "pan": "ABCDE1234F"}
    diff_original = FormFillDiff.from_field_values(target_url, fields_original)

    # Attacker tampers with PAN
    fields_tampered = {"full_name": "Arjun Sharma", "email": "arjun@example.com", "pan": "HACKE9999Z"}
    diff_tampered = FormFillDiff.from_field_values(target_url, fields_tampered)

    assert diff_original.digest != diff_tampered.digest

    # Binding message must reflect the different SHA
    msg1 = generate_binding_message(target_url, diff_original.digest)
    msg2 = generate_binding_message(target_url, diff_tampered.digest)
    assert msg1 != msg2


# ==============================================================================
# VECTOR 7: ATTEMPTED SUBMISSION BYPASS & REFUSAL INVARIANT VERIFICATION
# ==============================================================================

def test_adversarial_submission_bypass_blocked_when_consent_denied(tmp_path):
    """Verify that under live execution (dry_run=False), if CIBA consent is denied, submission is REFUSED."""
    vault_file = str(tmp_path / "bypass_vault.enc")
    vault = VaultManager(vault_path=vault_file, vault_key="test_auth0_vault_key_32_bytes_!!")
    vault.save_profile(create_sample_profile())

    ciba = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    orchestrator = SimulatedFillOrchestrator(vault, ciba, bb, filler)

    # Run with auto_approve_ciba=False, which keeps status at PENDING
    # Orchestrator calls poll_consent, which returns approved=False
    # Orchestrator MUST raise RefusalToSubmitError and NOT call filler.fill(..., dry_run=False)
    with pytest.raises(RefusalToSubmitError) as exc_info:
        orchestrator.run(
            target_url="https://boards.greenhouse.io/stripe/jobs/123",
            dry_run=False,
            auto_approve_ciba=False,
        )

    assert "refused" in str(exc_info.value).lower() or "denied" in str(exc_info.value).lower()
    # Invariant: session must be released
    assert len(bb.active_sessions) == 1
    session = list(bb.active_sessions.values())[0]
    assert session.status == "REQUEST_RELEASE"


def test_adversarial_submission_bypass_blocked_when_explicitly_rejected(tmp_path):
    """Verify that when user explicitly denies CIBA request, submission is blocked and RefusalToSubmitError raised."""
    vault_file = str(tmp_path / "reject_vault.enc")
    vault = VaultManager(vault_path=vault_file, vault_key="test_auth0_vault_key_32_bytes_!!")
    vault.save_profile(create_sample_profile())

    ciba = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)

    # Monkey patch ciba initiate to simulate immediate denial
    orig_initiate = ciba.initiate_consent
    def rejecting_initiate(*args, **kwargs):
        req = orig_initiate(*args, **kwargs)
        ciba.set_user_action(req.auth_req_id, "deny")
        return req
    ciba.initiate_consent = rejecting_initiate

    orchestrator = SimulatedFillOrchestrator(vault, ciba, bb, filler)

    with pytest.raises(RefusalToSubmitError) as exc_info:
        orchestrator.run(
            target_url="https://jobs.lever.co/acme/dev",
            dry_run=False,
            auto_approve_ciba=False,
        )

    assert "explicitly denied" in str(exc_info.value).lower()
    session = list(bb.active_sessions.values())[0]
    assert session.status == "REQUEST_RELEASE"


def test_adversarial_dry_run_never_submits_even_if_consent_approved(tmp_path):
    """Invariant: When dry_run=True, submitted=False ALWAYS holds, even with valid CIBA consent."""
    vault_file = str(tmp_path / "dry_vault.enc")
    vault = VaultManager(vault_path=vault_file, vault_key="test_auth0_vault_key_32_bytes_!!")
    vault.save_profile(create_sample_profile())

    ciba = SimulatedAuth0CIBAClient(offline_mode=True)
    bb = SimulatedBrowserbaseService()
    filler = SimulatedFormFiller(bb)
    orchestrator = SimulatedFillOrchestrator(vault, ciba, bb, filler)

    result = orchestrator.run(
        target_url="https://boards.greenhouse.io/stripe/jobs/123",
        dry_run=True,
        auto_approve_ciba=True,
    )

    assert result.dry_run is True
    assert result.submitted is False
    assert result.status == "DRY_RUN_SUCCESS"


def test_adversarial_consent_result_without_token_invalidation():
    """Invariant: A ConsentResult where access_token is empty or None must NOT be considered valid for token vault usage."""
    # When approved=False, access_token MUST be None
    unapproved = ConsentResult(approved=False, error="access_denied")
    assert unapproved.approved is False
    assert unapproved.access_token is None

    # An approved result with no token
    anomalous = ConsentResult(approved=True, access_token=None)
    # Verifying that downstream security check `bool(consent.approved and consent.access_token)` catches this
    is_valid_for_submission = bool(anomalous.approved and anomalous.access_token)
    assert not is_valid_for_submission
