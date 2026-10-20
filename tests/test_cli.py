"""Test suite for Developer CLI (cli/main.py)."""

from typer.testing import CliRunner
import pytest

from cli.main import app, set_orchestrator_factory
from app.models.browser_schema import FillResult


@pytest.fixture
def cli_runner():
    """Provides a Typer CLI test runner."""
    return CliRunner()


class MockCLIOrchestrator:
    """Mock orchestrator simulating pipeline execution for fast CLI unit tests."""

    def __init__(self, vault_manager=None, auto_approve_ciba=True):
        self.vault_manager = vault_manager
        self.auto_approve_ciba = auto_approve_ciba

    async def run(self, target_url: str, dry_run: bool = True, progress_callback=None, **kwargs):
        if progress_callback:
            progress_callback("SESSION_INIT", 10)
            progress_callback("DOM_EXTRACTION", 30)
            progress_callback("AI_REASONING", 50)
            progress_callback("CIBA_CONSENT", 70)
            progress_callback("FORM_FILLING", 90)
            progress_callback("COMPLETED", 100)

        return FillResult(
            status="DRY_RUN_SUCCESS" if dry_run else "SUBMITTED",
            session_id="cli_test_session_123",
            replay_url="https://browserbase.com/sessions/cli_test_session_123",
            live_view_url="https://browserbase.com/sessions/cli_test_session_123/live",
            screenshot_path="artifacts/screenshots/cli_test_session_123_dry_run.png",
            fields_filled_count=8,
            submit_button_detected="button#submit-application",
            dry_run=dry_run,
            submitted=not dry_run,
            diff=[
                {
                    "field": "Full Name",
                    "selector": "input#name",
                    "field_type": "text",
                    "value": "Arjun Sharma",
                    "tier": "PUBLIC",
                    "status": "Filled",
                },
                {
                    "field": "Email",
                    "selector": "input#email",
                    "field_type": "email",
                    "value": "arjun.sharma@example.com",
                    "tier": "PUBLIC",
                    "status": "Filled",
                },
                {
                    "field": "Phone",
                    "selector": "input#phone",
                    "field_type": "tel",
                    "value": "******3210",
                    "tier": "SEMI_SENSITIVE",
                    "status": "Filled",
                },
                {
                    "field": "Resume File",
                    "selector": "input#resume",
                    "field_type": "file",
                    "value": "synthetic_resume.pdf",
                    "tier": "SEMI_SENSITIVE",
                    "status": "Uploaded",
                },
            ],
        )


@pytest.fixture(autouse=True)
def inject_mock_orchestrator():
    """Ensure mock orchestrator is used during CLI tests."""
    set_orchestrator_factory(lambda vm=None, auto_approve_ciba=True: MockCLIOrchestrator(vm, auto_approve_ciba=auto_approve_ciba))
    yield
    set_orchestrator_factory(None)


def test_cli_help(cli_runner):
    """Verify root CLI help displays available commands."""
    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "fill" in result.stdout
    assert "vault" in result.stdout
    assert "health" in result.stdout


def test_cli_health_command(cli_runner):
    """Verify 'slothform health' command verifies subsystems and returns 0."""
    result = cli_runner.invoke(app, ["health"])
    assert result.exit_code == 0
    assert "Subsystem Readiness Check" in result.stdout
    assert "Python Runtime" in result.stdout
    assert "Identity Vault" in result.stdout
    assert "Browserbase Cloud" in result.stdout
    assert "Ultramarine Reasoning" in result.stdout


def test_cli_vault_show_command(cli_runner):
    """Verify 'slothform vault show' displays masked profiles and sensitivity tiers."""
    result = cli_runner.invoke(app, ["vault", "show"])
    assert result.exit_code == 0
    assert "SlothForm Encrypted Identity Vault" in result.stdout
    assert "Personal & Contact Details" in result.stdout
    assert "Tax Treaty Compliance Details" in result.stdout
    assert "Financial Remittance Details" in result.stdout
    assert "Field Sensitivity Engine Classification" in result.stdout
    # Verify masking
    assert "ABCDE****F" in result.stdout  # Masked PAN
    assert "****7890" in result.stdout   # Masked Account Number


def test_cli_fill_dry_run_active(cli_runner):
    """Verify 'slothform fill <url> --dry-run' outputs amber safety banner and summary table."""
    test_url = "https://boards.greenhouse.io/stripe/jobs/456"
    result = cli_runner.invoke(app, ["fill", test_url, "--dry-run"])

    assert result.exit_code == 0
    # Amber safety warning banner
    assert "DRY-RUN SAFETY ACTIVE" in result.stdout
    assert "Submissions are blocked" in result.stdout
    assert "outlined in amber" in result.stdout
    assert "Target URL:" in result.stdout
    assert test_url in result.stdout
    # Summary table
    assert "Form Field Population & Sensitivity Classification" in result.stdout
    assert "DRY_RUN_SUCCESS" in result.stdout
    assert "https://browserbase.com/sessions/cli_test_session_123" in result.stdout


def test_cli_fill_no_dry_run_warning(cli_runner):
    """Verify 'slothform fill <url> --no-dry-run' displays live submission warning."""
    test_url = "https://jobs.lever.co/postman/789"
    result = cli_runner.invoke(app, ["fill", test_url, "--no-dry-run"])

    assert result.exit_code == 0
    assert "LIVE SUBMISSION MODE" in result.stdout
    assert "Dry-run safety guard is DISABLED" in result.stdout
    assert "SUBMITTED" in result.stdout


def test_cli_fill_options_specification(cli_runner):
    """Verify 'slothform fill --help' lists required arguments and options."""
    result = cli_runner.invoke(app, ["fill", "--help"])
    assert result.exit_code == 0
    assert "URL" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--no-dry-run" in result.stdout
    assert "--auto-approve-ciba" in result.stdout
    assert "--no-auto-approve" in result.stdout
    assert "--vault-key" in result.stdout
    assert "--verbose" in result.stdout


def test_cli_fill_ciba_refusal_displays_panel(cli_runner):
    """Verify CLI displays red refusal panel when CIBA consent is denied."""
    from app.models.ciba_schema import RefusalToSubmitError

    class RefusalOrchestrator:
        async def run(self, *args, **kwargs):
            raise RefusalToSubmitError("User rejected CIBA backchannel authorization")

    set_orchestrator_factory(lambda vm=None, auto_approve_ciba=True: RefusalOrchestrator())
    result = cli_runner.invoke(app, ["fill", "https://example.com/form", "--no-auto-approve-ciba"])
    assert result.exit_code == 1
    assert "SUBMISSION REFUSED" in result.stdout
    assert "CIBA Consent Refusal" in result.stdout
    assert "User rejected CIBA backchannel authorization" in result.stdout
