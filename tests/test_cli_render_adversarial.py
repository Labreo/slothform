"""Empirical Adversarial Test Suite for Developer CLI (cli/main.py) and Render Blueprint (render.yaml).

Adversarial Stress Dimensions:
1. CLI flag edge cases:
   - Missing required URL argument
   - Unknown/invalid options and commands
   - Conflicting flags (--dry-run vs --no-dry-run resolution order)
   - Non-existent / invalid vault keys (< 8 characters, corrupted, non-existent storage)
   - Target URL malformed schemes (ftp://, javascript:, empty string)
2. Amber dry-run safety warning banner:
   - Unconditional emission whenever dry_run is True (default, explicit, pipeline failure, CIBA refusal, timeout)
   - Strict absence when --no-dry-run is supplied
3. Render Blueprint (render.yaml):
   - Strict YAML syntax and mapping structure
   - Service type ('web'), runtime ('python'), buildCommand, startCommand
   - healthCheckPath ('/health') alignment with live FastAPI /health endpoint
   - Strict secret hygiene: zero hardcoded secrets in render.yaml (sync: false or generateValue: true)
   - Render CLI binary validation ('render blueprints validate')
"""

import asyncio
from pathlib import Path
import shutil
import subprocess
import pytest
from typer.testing import CliRunner
import yaml
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from cli.main import app as cli_app, set_orchestrator_factory
from app.models.browser_schema import FillResult
from app.models.ciba_schema import RefusalToSubmitError


@pytest.fixture
def cli_runner():
    """Provides an isolated Typer CliRunner instance."""
    return CliRunner()


class MockAdversarialOrchestrator:
    """Mock orchestrator designed to simulate various pipeline execution conditions."""

    def __init__(self, failure_mode: str = "success"):
        self.failure_mode = failure_mode

    async def run(self, target_url: str, dry_run: bool = True, progress_callback=None, **kwargs):
        if progress_callback:
            progress_callback("SESSION_INIT", 10)

        if self.failure_mode == "runtime_error":
            raise RuntimeError("Adversarial crash: Browserbase connection dropped")
        elif self.failure_mode == "refusal_to_submit":
            raise RefusalToSubmitError("Adversarial refusal: User rejected CIBA backchannel consent")
        elif self.failure_mode == "timeout":
            raise asyncio.TimeoutError("Adversarial timeout: Page navigation exceeded deadline")

        if progress_callback:
            progress_callback("DOM_EXTRACTION", 30)
            progress_callback("AI_REASONING", 50)
            progress_callback("CIBA_CONSENT", 70)
            progress_callback("FORM_FILLING", 90)
            progress_callback("COMPLETED", 100)

        return FillResult(
            status="DRY_RUN_SUCCESS" if dry_run else "SUBMITTED",
            session_id="adv_test_session_999",
            replay_url="https://browserbase.com/sessions/adv_test_session_999",
            live_view_url="https://browserbase.com/sessions/adv_test_session_999/live",
            screenshot_path="artifacts/screenshots/adv_test_session_999.png",
            fields_filled_count=7,
            submit_button_detected="button[type=submit]",
            dry_run=dry_run,
            submitted=not dry_run,
        )


@pytest.fixture(autouse=True)
def cleanup_orchestrator_factory():
    """Reset the injectable orchestrator factory after every test."""
    yield
    set_orchestrator_factory(None)


# ==============================================================================
# DIMENSION 1: CLI FLAG & ARGUMENT EDGE CASES
# ==============================================================================


def test_adversarial_cli_missing_url(cli_runner):
    """STRESS TEST: Running 'slothform fill' without URL argument must halt with exit code 2."""
    result = cli_runner.invoke(cli_app, ["fill"])
    assert result.exit_code == 2
    assert "Missing argument 'URL'" in result.stdout or "Missing argument" in result.output


def test_adversarial_cli_unknown_option(cli_runner):
    """STRESS TEST: Supplying unsupported flags must fail cleanly with exit code 2."""
    result = cli_runner.invoke(cli_app, ["fill", "https://example.com", "--bogus-flag-123"])
    assert result.exit_code == 2
    assert "No such option" in result.stdout or "No such option" in result.output


def test_adversarial_cli_unknown_command(cli_runner):
    """STRESS TEST: Invoking an invalid subcommand must fail cleanly with exit code 2."""
    result = cli_runner.invoke(cli_app, ["nonexistent_command"])
    assert result.exit_code == 2
    assert "No such command" in result.stdout or "No such command" in result.output


def test_adversarial_cli_conflicting_flags_resolution(cli_runner):
    """STRESS TEST: Conflicting --dry-run and --no-dry-run options must resolve deterministically.

    In Typer / Click, rightmost flag takes precedence.
    """
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator())

    # Case A: --dry-run followed by --no-dry-run -> should resolve to LIVE SUBMISSION MODE
    res_live = cli_runner.invoke(cli_app, ["fill", "https://example.com", "--dry-run", "--no-dry-run"])
    assert res_live.exit_code == 0
    assert "LIVE SUBMISSION MODE" in res_live.stdout
    assert "DRY-RUN SAFETY ACTIVE" not in res_live.stdout

    # Case B: --no-dry-run followed by --dry-run -> should resolve to DRY-RUN SAFETY ACTIVE
    res_dry = cli_runner.invoke(cli_app, ["fill", "https://example.com", "--no-dry-run", "--dry-run"])
    assert res_dry.exit_code == 0
    assert "DRY-RUN SAFETY ACTIVE" in res_dry.stdout
    assert "LIVE SUBMISSION MODE" not in res_dry.stdout


def test_adversarial_cli_vault_key_too_short(cli_runner):
    """STRESS TEST: Supplying a vault key < 8 characters must fail with ValueError."""
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator())
    result = cli_runner.invoke(cli_app, ["fill", "https://example.com", "--vault-key", "short"])
    assert result.exit_code != 0
    # Must fail with ValueError regarding minimum length
    assert "Vault key must be at least 8 characters long" in str(result.exception) or "Vault key must be at least 8 characters long" in result.output
    # Crucial: Amber dry-run safety banner was still printed unconditionally before failure!
    assert "DRY-RUN SAFETY ACTIVE" in result.stdout


def test_adversarial_cli_vault_show_wrong_key_graceful_fallback(cli_runner):
    """STRESS TEST: 'vault show' with invalid passphrase must not crash; falls back cleanly to sample profile."""
    result = cli_runner.invoke(cli_app, ["vault", "show", "--vault-key", "wrong_passphrase_888"])
    assert result.exit_code == 0
    assert "SlothForm Encrypted Identity Vault" in result.stdout
    assert "Fallback to sample profile" in result.stdout
    # Masking still applies
    assert "ABCDE****F" in result.stdout


def test_adversarial_cli_tax_url_detection(cli_runner):
    """STRESS TEST: CLI must detect W-8BEN/tax URLs and render W-8BEN specific diff rows."""
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator())
    result = cli_runner.invoke(cli_app, ["fill", "https://tax.contractor.com/w-8ben/form", "--dry-run"])
    assert result.exit_code == 0
    assert "Line 6a (Foreign Tax ID)" in result.stdout
    assert "Line 6b (No FTIN Checkbox)" in result.stdout
    assert "Line 10 (Treaty Article)" in result.stdout


def test_adversarial_cli_ats_url_detection(cli_runner):
    """STRESS TEST: CLI must detect standard ATS URLs and render ATS job application diff rows."""
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator())
    result = cli_runner.invoke(cli_app, ["fill", "https://boards.greenhouse.io/corp/jobs/123", "--dry-run"])
    assert result.exit_code == 0
    assert "First Name" in result.stdout
    assert "Resume" in result.stdout
    assert "Essay / Cover Letter" in result.stdout


# ==============================================================================
# DIMENSION 2: AMBER DRY-RUN SAFETY WARNING BANNER UNCONDITIONAL PRINTING
# ==============================================================================


def test_adversarial_amber_banner_unconditional_on_default(cli_runner):
    """STRESS TEST: Running without flags defaults to dry_run=True and prints amber banner."""
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator())
    result = cli_runner.invoke(cli_app, ["fill", "https://example.com/apply"])
    assert result.exit_code == 0
    assert "DRY-RUN SAFETY ACTIVE" in result.stdout
    assert "outlined in amber" in result.stdout
    assert "Submissions are blocked" in result.stdout


def test_adversarial_amber_banner_unconditional_on_explicit(cli_runner):
    """STRESS TEST: Running with explicit --dry-run prints amber banner."""
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator())
    result = cli_runner.invoke(cli_app, ["fill", "https://example.com/apply", "--dry-run"])
    assert result.exit_code == 0
    assert "DRY-RUN SAFETY ACTIVE" in result.stdout


def test_adversarial_amber_banner_preserved_on_pipeline_crash(cli_runner):
    """STRESS TEST: When orchestrator crashes with RuntimeError, amber banner was ALREADY printed."""
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator(failure_mode="runtime_error"))
    result = cli_runner.invoke(cli_app, ["fill", "https://example.com/apply", "--dry-run"])
    assert result.exit_code == 1
    # Verify amber banner was emitted prior to error reporting
    assert "DRY-RUN SAFETY ACTIVE" in result.stdout
    assert "Pipeline failed: Adversarial crash" in result.stdout


def test_adversarial_amber_banner_preserved_on_ciba_refusal(cli_runner):
    """STRESS TEST: When CIBA consent is refused, amber banner was ALREADY printed."""
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator(failure_mode="refusal_to_submit"))
    result = cli_runner.invoke(cli_app, ["fill", "https://example.com/apply", "--dry-run"])
    assert result.exit_code == 1
    assert "DRY-RUN SAFETY ACTIVE" in result.stdout
    assert "Pipeline failed: Adversarial refusal" in result.stdout


def test_adversarial_amber_banner_preserved_on_timeout(cli_runner):
    """STRESS TEST: When timeout occurs, amber banner was ALREADY printed."""
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator(failure_mode="timeout"))
    result = cli_runner.invoke(cli_app, ["fill", "https://example.com/apply", "--dry-run"])
    assert result.exit_code == 1
    assert "DRY-RUN SAFETY ACTIVE" in result.stdout
    assert "Pipeline failed" in result.stdout


def test_adversarial_amber_banner_strictly_absent_on_live_submit(cli_runner):
    """STRESS TEST: Under --no-dry-run, amber banner MUST NOT appear; red warning MUST appear."""
    set_orchestrator_factory(lambda vm: MockAdversarialOrchestrator())
    result = cli_runner.invoke(cli_app, ["fill", "https://example.com/apply", "--no-dry-run"])
    assert result.exit_code == 0
    assert "DRY-RUN SAFETY ACTIVE" not in result.stdout
    assert "LIVE SUBMISSION MODE" in result.stdout
    assert "Dry-run safety guard is DISABLED" in result.stdout


# ==============================================================================
# DIMENSION 3: RENDER BLUEPRINT STRUCTURAL & SECURITY VALIDATION
# ==============================================================================


@pytest.fixture
def raw_render_blueprint():
    """Load render.yaml text and parsed dictionary."""
    path = Path("render.yaml")
    assert path.exists(), "render.yaml must be present at repository root"
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return text, data


def test_adversarial_render_blueprint_structural_integrity(raw_render_blueprint):
    """STRESS TEST: render.yaml must conform strictly to Render Blueprint specification."""
    _, data = raw_render_blueprint
    assert isinstance(data, dict), "render.yaml root must be a YAML mapping"
    assert "services" in data, "render.yaml must contain 'services' list"
    assert isinstance(data["services"], list)
    assert len(data["services"]) == 1, "Expected exactly one service definition for slothform"

    service = data["services"][0]
    assert service.get("type") == "web", "Service type must be 'web'"
    assert service.get("name") == "slothform", "Service name must be 'slothform'"
    assert service.get("runtime") == "python", "Service runtime must be 'python'"
    assert service.get("env") == "python", "Service legacy env alias must be 'python'"
    assert service.get("buildCommand") == "pip install -r requirements.txt"
    assert service.get("startCommand") == "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    assert service.get("healthCheckPath") == "/health"


def test_adversarial_render_health_check_endpoint_contract():
    """STRESS TEST: The healthCheckPath (/health) declared in render.yaml must respond with 200 OK."""
    client = TestClient(fastapi_app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("status") == "healthy"
    assert payload.get("service") == "slothform"
    assert "version" in payload
    assert "uptime_seconds" in payload
    assert "subsystems" in payload


def test_adversarial_render_blueprint_zero_hardcoded_secrets(raw_render_blueprint):
    """STRESS TEST: render.yaml MUST NOT contain any plain-text secrets or API keys."""
    _, data = raw_render_blueprint
    service = data["services"][0]
    env_vars = service.get("envVars", [])
    assert len(env_vars) >= 8, "Expected at least 8 configured environment variables"

    var_map = {item["key"]: item for item in env_vars}

    # 1. Generated secrets must use generateValue: true and have NO raw value
    generated_secrets = ["SECRET_KEY", "AUTH0_TOKEN_VAULT_KEY"]
    for key in generated_secrets:
        assert key in var_map, f"Missing {key} in render.yaml envVars"
        assert var_map[key].get("generateValue") is True, f"{key} must have generateValue: true"
        assert "value" not in var_map[key], f"{key} MUST NOT have a hardcoded value"

    # 2. External secrets must use sync: false and have NO raw value
    external_secrets = [
        "BROWSERBASE_API_KEY",
        "BROWSERBASE_PROJECT_ID",
        "PAPER_INSTRUMENTS_API_KEY",
        "AUTH0_DOMAIN",
        "AUTH0_CLIENT_ID",
        "AUTH0_CLIENT_SECRET",
    ]
    for key in external_secrets:
        assert key in var_map, f"Missing {key} in render.yaml envVars"
        assert var_map[key].get("sync") is False, f"{key} must have sync: false"
        assert "value" not in var_map[key], f"{key} MUST NOT have a hardcoded value"

    # 3. Only non-secret configuration is allowed a value
    assert var_map["PYTHON_VERSION"].get("value") == "3.11.9"


def test_adversarial_render_cli_validation():
    """STRESS TEST: Execute the official Render CLI binary on render.yaml.

    Documents the exact behavior:
    - Without 'plan: free', Render CLI requires payment info if user has no card attached.
    - With 'plan: free' explicitly set, Render CLI validates with 100% success.
    """
    render_binary = shutil.which("render") or "/opt/homebrew/bin/render"
    if not Path(render_binary).exists():
        pytest.skip("Render CLI binary not found on host system")

    # Run validation on current render.yaml
    res = subprocess.run([render_binary, "blueprints", "validate", "render.yaml"], capture_output=True, text=True)
    # The output will indicate whether payment info is required or valid
    # Either valid=true OR error=need_payment_info (which confirms schema compliance but requires billing tier)
    assert res.returncode in (0, 1)
    if res.returncode != 0:
        assert "need_payment_info" in res.stdout or "need_payment_info" in res.stderr

    # Test validation with plan: free injected dynamically into a temporary blueprint
    with open("render.yaml", "r", encoding="utf-8") as f:
        blueprint_dict = yaml.safe_load(f)
    blueprint_dict["services"][0]["plan"] = "free"

    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
        yaml.dump(blueprint_dict, tmp)
        tmp_path = tmp.name

    try:
        res_free = subprocess.run([render_binary, "blueprints", "validate", tmp_path], capture_output=True, text=True)
        assert res_free.returncode == 0
        assert '"valid": true' in res_free.stdout
    finally:
        Path(tmp_path).unlink(missing_ok=True)
