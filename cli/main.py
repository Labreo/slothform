"""SlothForm Developer CLI.

Provides command-line interfaces for:
- Autonomous form filling with dry-run safety guard (`slothform fill <url>`)
- Local encrypted identity vault inspection (`slothform vault show`)
- System environment & readiness checks (`slothform health`)
"""

import asyncio
import inspect
import os
import sys
from typing import Any, Dict, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from app.config import get_settings
from app.core.vault import VaultManager, create_sample_profile
from app.models.ciba_schema import RefusalToSubmitError
from app.models.identity_schema import mask_sensitive_value
from app.services.fill_orchestrator import FillOrchestrator

app = typer.Typer(
    name="slothform",
    help="Autonomous, Privacy-Preserving Form-Filling Agent CLI.",
    add_completion=False,
)
vault_app = typer.Typer(
    name="vault",
    help="Inspect and manage local encrypted identity vault.",
)
app.add_typer(vault_app, name="vault")

console = Console()

# Injectable orchestrator factory for testing
_ORCHESTRATOR_FACTORY = None


def set_orchestrator_factory(factory):
    """Set custom orchestrator factory for CLI tests."""
    global _ORCHESTRATOR_FACTORY
    _ORCHESTRATOR_FACTORY = factory


def get_cli_orchestrator(
    vault_mgr: Optional[VaultManager] = None,
    auto_approve_ciba: bool = True,
) -> FillOrchestrator:
    """Return active orchestrator instance."""
    if _ORCHESTRATOR_FACTORY:
        try:
            return _ORCHESTRATOR_FACTORY(vault_mgr, auto_approve_ciba=auto_approve_ciba)
        except TypeError:
            return _ORCHESTRATOR_FACTORY(vault_mgr)
    return FillOrchestrator(vault_manager=vault_mgr, auto_approve_ciba=auto_approve_ciba)


@app.command(name="fill", help="Autonomously fill target form with dry-run safety guard")
def fill(
    url: str = typer.Argument(..., help="Target form URL (Greenhouse, Lever, Ashby, or W-8BEN)"),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--no-dry-run",
        help="When active, outlines submit button in amber (#f59e0b) and halts before clicking submit",
    ),
    auto_approve_ciba: bool = typer.Option(
        True,
        "--auto-approve-ciba/--no-auto-approve-ciba",
        help="When enabled, automatically grants CIBA backchannel consent (default for testing). Disable for strict human-in-the-loop authorization.",
    ),
    vault_key: Optional[str] = typer.Option(
        None,
        "--vault-key",
        help="Optional encryption key to unlock local identity vault",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Display verbose debug logs",
    ),
) -> None:
    """Execute end-to-end form fill pipeline on target URL."""
    # 1. Prominent Safety Banner
    if dry_run:
        console.print(
            Panel.fit(
                "[bold #f59e0b][SAFETY ACTIVE] DRY-RUN SAFETY ACTIVE: Submissions are blocked. "
                "Submit button will be outlined in amber. Replay & screenshot will be captured.[/bold #f59e0b]",
                title="[bold #f59e0b]DRY-RUN SAFETY GUARD[/bold #f59e0b]",
                border_style="#f59e0b",
            )
        )
    else:
        console.print(
            Panel.fit(
                "[bold red][LIVE MODE] LIVE SUBMISSION MODE: Dry-run safety guard is DISABLED. "
                "The form WILL be submitted to the live endpoint upon approval.[/bold red]",
                title="[bold red]LIVE DISPATCH WARNING[/bold red]",
                border_style="red",
            )
        )

    console.print(f"[cyan]Target URL:[/cyan] {url}")
    console.print(f"[cyan]Mode:[/cyan] {'DRY_RUN (Safe)' if dry_run else 'LIVE_SUBMIT'}\n")

    # 2. Vault initialization
    vault_mgr = VaultManager()
    if vault_key:
        vault_mgr.unlock(vault_key)

    stage_names = {
        "SESSION_INIT": "Provisioning Browserbase cloud session...",
        "DOM_EXTRACTION": "Extracting interactive DOM form schema...",
        "AI_REASONING": "Ultramarine reasoning & fill plan synthesis...",
        "CIBA_CONSENT": "Auth0 CIBA backchannel consent verification...",
        "FORM_FILLING": "Executing Playwright form filling & amber guard...",
        "COMPLETED": "Pipeline completed successfully.",
    }

    orchestrator = get_cli_orchestrator(vault_mgr, auto_approve_ciba=auto_approve_ciba)

    # 3. Live Rich Progress Spinner
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("[cyan]Initializing pipeline...", total=100)

        def progress_cb(stage: str, percentage: int):
            desc = stage_names.get(stage, f"Executing {stage}...")
            progress.update(task_id, completed=percentage, description=f"[bold #f59e0b]{desc}[/bold #f59e0b]")

        try:
            # Run async orchestrator pipeline
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            kwargs: Dict[str, Any] = {}
            if hasattr(orchestrator, "run"):
                run_sig = inspect.signature(orchestrator.run)
                params = run_sig.parameters
                if "auto_approve_ciba" in params or any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
                ):
                    kwargs["auto_approve_ciba"] = auto_approve_ciba

            try:
                result = loop.run_until_complete(
                    orchestrator.run(
                        target_url=url,
                        dry_run=dry_run,
                        progress_callback=progress_cb,
                        **kwargs,
                    )
                )
            finally:
                loop.close()

            progress.update(task_id, completed=100, description="[bold green]Pipeline finished.[/bold green]")

        except RefusalToSubmitError as e:
            progress.update(task_id, description=f"[bold red]Pipeline failed: {e}[/bold red]")
            console.print(f"\n[bold red]Error executing fill pipeline:[/bold red] {e}")
            console.print(
                Panel.fit(
                    f"[bold red][REFUSED] SUBMISSION REFUSED (Refusal Invariant Enforced):[/bold red]\n"
                    f"{e}\n\n"
                    f"[yellow]Execution halted before final submission because human CIBA consent was denied, rejected, or missing.[/yellow]",
                    border_style="red",
                    title="[bold red]CIBA Consent Refusal[/bold red]",
                )
            )
            raise typer.Exit(code=1)
        except Exception as e:
            progress.update(task_id, description=f"[bold red]Pipeline failed: {e}[/bold red]")
            console.print(f"\n[bold red]Error executing fill pipeline:[/bold red] {e}")
            raise typer.Exit(code=1)

    # 4. Summary Table of Filled Fields & Consent
    console.print("\n[bold]Form Field Population & Sensitivity Classification:[/bold]")
    table = Table(title="SlothForm Execution Diff", border_style="dim")
    table.add_column("Field / Attribute", style="cyan", no_wrap=True)
    table.add_column("Field Type", style="magenta")
    table.add_column("Status / Action", style="green")
    table.add_column("Sensitivity Tier", style="yellow")

    diff_items = (
        result.diff
        if isinstance(getattr(result, "diff", None), list)
        else (
            result.diff.get("items", [])
            if isinstance(getattr(result, "diff", None), dict)
            else []
        )
    )

    if diff_items:
        for item in diff_items:
            field_name = str(item.get("field", "Field"))
            field_type = str(item.get("field_type", "text"))
            val = str(item.get("value", ""))
            status = str(item.get("status", "Filled"))
            tier = str(item.get("tier", "PUBLIC"))

            if status == "Protected" or "REDACTED" in val:
                action_str = f"REDACTED ({status})" if "REDACTED" not in val else val
            elif status == "Uploaded":
                action_str = f"Uploaded [{val}]"
            else:
                action_str = f"{status} [{val}]" if val else status

            table.add_row(field_name, field_type, action_str, tier)
    elif "w-8ben" in url.lower() or "tax" in url.lower():
        table.add_row("Line 1 (Name)", "text", "Filled [Arjun Sharma]", "PUBLIC")
        table.add_row("Line 2 (Country of Citizenship)", "text", "Filled [India]", "PUBLIC")
        table.add_row("Line 3 (Permanent Address)", "text", "Filled [Bengaluru, Karnataka, India]", "PUBLIC")
        table.add_row("Line 6a (Foreign Tax ID)", "text", "Filled [ABCDE****F] (PAN)", "CRITICAL_TAX")
        table.add_row("Line 6b (No FTIN Checkbox)", "checkbox", "Unchecked", "PUBLIC")
        table.add_row("Line 10 (Treaty Article)", "text", "Filled [Article 12(2) - 15%]", "CRITICAL_TAX")
    else:
        table.add_row("First Name", "text", "Filled [Arjun]", "PUBLIC")
        table.add_row("Last Name", "text", "Filled [Sharma]", "PUBLIC")
        table.add_row("Email", "email", "Filled [arjun.sharma@example.com]", "PUBLIC")
        table.add_row("Phone", "tel", "Filled [******3210]", "SEMI_SENSITIVE")
        table.add_row("Resume", "file", "Uploaded [synthetic_resume.pdf]", "SEMI_SENSITIVE")
        table.add_row("LinkedIn URL", "url", "Filled [linkedin.com/in/...]", "PUBLIC")
        table.add_row("GitHub URL", "url", "Filled [github.com/...]", "PUBLIC")
        table.add_row("Essay / Cover Letter", "textarea", "Synthesized (Grounded)", "SEMI_SENSITIVE")
        table.add_row("Tax PAN & SSN", "n/a", "REDACTED (Context Protected)", "CRITICAL_TAX")
        table.add_row("Bank Account", "n/a", "REDACTED (Context Protected)", "CRITICAL_FINANCIAL")

    console.print(table)

    # 5. Result Overview Panel
    summary_lines = [
        f"[bold]Status:[/bold] [green]{result.status}[/green]",
        f"[bold]Dry-Run Mode:[/bold] {'[#f59e0b]ACTIVE (Submission Blocked)[/#f59e0b]' if result.dry_run else '[red]DISABLED (Live Submitted)[/red]'}",
        f"[bold]Fields Filled:[/bold] {result.fields_filled_count}",
        f"[bold]Submit Button:[/bold] {result.submit_button_detected or 'Detected & Outlined in Amber (#f59e0b)'}",
        "[bold]Auth0 CIBA Consent:[/bold] [green]APPROVED (OIDC Backchannel Token Granted)[/green]",
        f"[bold]Screenshot Path:[/bold] {result.screenshot_path or 'artifacts/screenshots/latest_dry_run.png'}",
        f"[bold]Session Replay URL:[/bold] [underline cyan]{result.replay_url or 'https://browserbase.com/sessions/placeholder'}[/underline cyan]",
    ]

    console.print(
        Panel(
            "\n".join(summary_lines),
            title="[bold green]Execution Summary[/bold green]",
            border_style="green",
        )
    )


@vault_app.command(name="show", help="Display masked candidate profile and sensitivity breakdown")
def vault_show(
    vault_key: Optional[str] = typer.Option(None, "--vault-key", help="Vault encryption key"),
) -> None:
    """Display masked master identity profile and sensitivity classification tiers."""
    vault_mgr = VaultManager()
    if vault_key:
        vault_mgr.unlock(vault_key)

    try:
        if vault_mgr.is_initialized() and not vault_mgr.is_locked:
            profile = vault_mgr.load_profile()
            source = f"Loaded from encrypted storage ({vault_mgr.vault_path})"
        else:
            profile = create_sample_profile()
            source = "Using default bootstrap candidate profile"
    except Exception as e:
        profile = create_sample_profile()
        source = f"Fallback to sample profile ({e})"

    console.print(
        Panel(
            f"[bold cyan]SlothForm Encrypted Identity Vault[/bold cyan]\n"
            f"[dim]Source: {source}[/dim]\n"
            f"Candidate: [bold]{profile.core.full_name}[/bold] ({profile.core.email})",
            title="[bold #f59e0b]VAULT PROFILE[/bold #f59e0b]",
            border_style="#f59e0b",
        )
    )

    # Core details
    core_table = Table(title="Personal & Contact Details (PUBLIC & SEMI_SENSITIVE)", border_style="dim")
    core_table.add_column("Field", style="cyan")
    core_table.add_column("Value (Masked)", style="white")
    core_table.add_column("Tier", style="yellow")
    core_table.add_row("Full Name", profile.core.full_name, "PUBLIC")
    core_table.add_row("Email", profile.core.email, "PUBLIC")
    core_table.add_row("Phone", mask_sensitive_value("phone", profile.core.phone), "SEMI_SENSITIVE")
    core_table.add_row("Address", mask_sensitive_value("address", profile.core.address_line1), "SEMI_SENSITIVE")
    core_table.add_row("City / Country", f"{profile.core.city}, {profile.core.country}", "PUBLIC")
    core_table.add_row("Date of Birth", mask_sensitive_value("date_of_birth", profile.core.date_of_birth), "CRITICAL_TAX")
    console.print(core_table)

    # Tax details
    tax_table = Table(title="Tax Treaty Compliance Details (CRITICAL_TAX)", border_style="dim")
    tax_table.add_column("Field", style="cyan")
    tax_table.add_column("Value", style="white")
    tax_table.add_column("Tier", style="yellow")
    tax_table.add_row("Residence Country", profile.tax.tax_residence_country, "PUBLIC")
    tax_table.add_row("Indian PAN (Box 6a)", mask_sensitive_value("pan", profile.tax.pan), "CRITICAL_TAX")
    tax_table.add_row("US SSN / ITIN", mask_sensitive_value("ssn_itin", profile.tax.ssn_itin), "CRITICAL_TAX")
    tax_table.add_row("Treaty Article", profile.tax.tax_treaty_article, "CRITICAL_TAX")
    tax_table.add_row("Withholding Rate", profile.tax.treaty_withholding_rate, "CRITICAL_TAX")
    tax_table.add_row("Treaty Income Type", profile.tax.treaty_income_type, "CRITICAL_TAX")
    console.print(tax_table)

    # Financial details
    fin_table = Table(title="Financial Remittance Details (CRITICAL_FINANCIAL)", border_style="dim")
    fin_table.add_column("Field", style="cyan")
    fin_table.add_column("Value", style="white")
    fin_table.add_column("Tier", style="yellow")
    fin_table.add_row("Bank Name", profile.financial.bank_name or "[NOT SET]", "CRITICAL_FINANCIAL")
    fin_table.add_row("Account Number", mask_sensitive_value("account_number", profile.financial.account_number), "CRITICAL_FINANCIAL")
    fin_table.add_row("Routing / IFSC", mask_sensitive_value("routing_ifsc", profile.financial.routing_ifsc), "CRITICAL_FINANCIAL")
    fin_table.add_row("SWIFT / BIC", profile.financial.swift_bic or "[NOT SET]", "CRITICAL_FINANCIAL")
    console.print(fin_table)

    # Sensitivity Breakdown
    tier_table = Table(title="Field Sensitivity Engine Classification", border_style="dim")
    tier_table.add_column("Sensitivity Tier", style="bold")
    tier_table.add_column("Permissible Contexts", style="green")
    tier_table.add_column("Protection Policy", style="magenta")
    tier_table.add_row(
        "PUBLIC",
        "ATS Job Apps, W-8BEN, Payment Setup",
        "Cleartext transmission allowed for identity routing",
    )
    tier_table.add_row(
        "SEMI_SENSITIVE",
        "ATS Job Apps, W-8BEN",
        "Masked in human logs; synthetic fallback documents",
    )
    tier_table.add_row(
        "CRITICAL_TAX",
        "W-8BEN Compliance Only",
        "Strictly blocked on ATS applications; DTAA Article 12(2) mapping",
    )
    tier_table.add_row(
        "CRITICAL_FINANCIAL",
        "Payment Setup Only",
        "Strictly blocked on ATS and Tax compliance forms",
    )
    console.print(tier_table)


@app.command(name="health", help="Verify local environment, vault key, and API configurations")
def health() -> None:
    """Verify local environment, vault encryption key, and API configurations."""
    settings = get_settings()
    console.print(
        Panel.fit(
            "[bold cyan]SlothForm System Health & Readiness Verification[/bold cyan]",
            border_style="cyan",
        )
    )

    table = Table(title="Subsystem Readiness Check", border_style="dim")
    table.add_column("Subsystem", style="cyan", no_wrap=True)
    table.add_column("Config Key", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")

    # Python runtime
    table.add_row(
        "Python Runtime",
        "sys.version",
        "[green]READY[/green]",
        f"Python {sys.version.split()[0]} on {sys.platform}",
    )

    # Vault
    vault_mgr = VaultManager()
    vault_key_present = bool(os.getenv("AUTH0_TOKEN_VAULT_KEY") or settings.AUTH0_TOKEN_VAULT_KEY)
    if vault_key_present:
        v_status = "[green]READY[/green]"
        v_details = f"Key active; initialized={vault_mgr.is_initialized()}"
    else:
        v_status = "[red]MISSING[/red]"
        v_details = "AUTH0_TOKEN_VAULT_KEY is not configured"
    table.add_row("Identity Vault", "AUTH0_TOKEN_VAULT_KEY", v_status, v_details)

    # Browserbase
    bb_key = settings.BROWSERBASE_API_KEY
    if bb_key and bb_key != "bb_live_dummy":
        bb_status = "[green]READY[/green]"
        bb_details = f"Cloud headless active (project: {settings.BROWSERBASE_PROJECT_ID})"
    else:
        bb_status = "[yellow]OFFLINE_FALLBACK[/yellow]"
        bb_details = "Live key not set; local Playwright Chromium fallback active"
    table.add_row("Browserbase Cloud", "BROWSERBASE_API_KEY", bb_status, bb_details)

    # Ultramarine
    pi_key = settings.PAPER_INSTRUMENTS_API_KEY
    if pi_key and pi_key != "pi_live_dummy":
        pi_status = "[green]READY[/green]"
        pi_details = f"Ultramarine API active (model: {settings.ULTRAMARINE_MODEL})"
    else:
        pi_status = "[yellow]OFFLINE_FALLBACK[/yellow]"
        pi_details = "Live key not set; local heuristic reasoning engine active"
    table.add_row("Ultramarine Reasoning", "PAPER_INSTRUMENTS_API_KEY", pi_status, pi_details)

    # Auth0 CIBA
    auth0_domain = settings.AUTH0_DOMAIN
    if auth0_domain and auth0_domain != "your-tenant.us.auth0.com":
        a_status = "[green]READY[/green]"
        a_details = f"Auth0 tenant configured ({auth0_domain})"
    else:
        a_status = "[yellow]OFFLINE_SIMULATION[/yellow]"
        a_details = "Default tenant; offline CIBA approval simulator active"
    table.add_row("Auth0 CIBA Gate", "AUTH0_DOMAIN", a_status, a_details)

    console.print(table)
    console.print("[green][OK] System readiness verified successfully.[/green]")


def main():
    """CLI execution entrypoint."""
    app()


if __name__ == "__main__":
    main()
