"""End-to-End Form Fill Pipeline Orchestrator."""

import asyncio
import inspect
import logging
import os
import uuid
from typing import Any, Callable, Dict, List, Optional

from playwright.async_api import async_playwright

from app.core.auth0_client import Auth0CIBAClient
from app.core.ultramarine_client import UltramarineClient
from app.core.vault import VaultManager, create_sample_profile
from app.models.browser_schema import FieldType, FillPlan, FillResult, FormSchema
from app.models.ciba_schema import (
    ConsentResult,
    FormFillDiff,
    RefusalToSubmitError,
)
from app.models.identity_schema import (
    FormContext,
    MasterIdentityProfile,
    SensitivityTier,
    get_field_tier,
    mask_sensitive_value,
)
from app.services.browserbase_service import BrowserbaseService
from app.services.dom_extractor import DOMExtractor
from app.services.form_filler import FormFiller

logger = logging.getLogger(__name__)


class FillOrchestrator:
    """Full-stack pipeline orchestrator linking Ingestion, Reasoning, CIBA Consent, and Filling.
    
    6-Stage Pipeline:
    - Stage 1: SESSION_INIT (10%) -> Browserbase session provisioning (or local Playwright page).
    - Stage 2: DOM_EXTRACTION (30%) -> DOMExtractor.extract_schema(page).
    - Stage 3: AI_REASONING (50%) -> UltramarineClient.generate_fill_plan(dom_schema, profile, session_id).
    - Stage 4: CIBA_CONSENT (70%) -> Builds FormFillDiff. Evaluates context. Triggers Auth0 CIBA consent.
    - Stage 5: FORM_FILLING (90%) -> FormFiller.fill(page, fill_plan, dry_run). Outlines submit in amber.
    - Stage 6: COMPLETED (100%) -> Teardown and returns FillResult.
    """

    def __init__(
        self,
        vault_manager: Optional[VaultManager] = None,
        ciba_client: Optional[Auth0CIBAClient] = None,
        browserbase_service: Optional[BrowserbaseService] = None,
        form_filler: Optional[FormFiller] = None,
        dom_extractor: Optional[DOMExtractor] = None,
        ultramarine_client: Optional[UltramarineClient] = None,
        auto_approve_ciba: bool = False,
    ) -> None:
        self.vault_manager = vault_manager or VaultManager()
        self.auth0_client = ciba_client or Auth0CIBAClient()
        self.browserbase_service = browserbase_service or BrowserbaseService()
        self.form_filler = form_filler or FormFiller()
        self.dom_extractor = dom_extractor or DOMExtractor()
        self.ultramarine_client = ultramarine_client or UltramarineClient()
        self.auto_approve_ciba = auto_approve_ciba

    async def run(
        self,
        target_url: str,
        dry_run: bool = True,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        page: Optional[Any] = None,
        auto_approve_ciba: Optional[bool] = None,
        html_override: Optional[str] = None,
        timeout: int = 60,
    ) -> FillResult:
        """Execute end-to-end form fill pipeline across all 6 stages."""

        def report_progress(stage: str, percentage: int) -> None:
            if progress_callback:
                try:
                    progress_callback(stage, percentage)
                except Exception as e:
                    logger.debug(f"Progress callback notification error: {e}")

        session_id: Optional[str] = None
        session = None
        owns_page = False
        browser = None
        playwright_cm = None
        active_page = page

        try:
            # ------------------------------------------------------------------
            # Stage 1: SESSION_INIT (10%)
            # ------------------------------------------------------------------
            report_progress("SESSION_INIT", 10)

            if active_page is not None:
                session_id = (
                    getattr(active_page, "_session_id", None)
                    or f"sess_local_{uuid.uuid4().hex[:12]}"
                )
            else:
                owns_page = True
                if hasattr(self.browserbase_service, "create_session"):
                    session = self.browserbase_service.create_session()
                    session_id = session.id
                else:
                    session_id = f"sess_{uuid.uuid4().hex[:12]}"

                playwright_cm = async_playwright()
                p = await playwright_cm.start()

                # Determine if connecting to live Browserbase cloud CDP or local headless
                is_offline = getattr(self.browserbase_service, "offline", True) or not getattr(
                    self.browserbase_service, "client", None
                )

                if is_offline or not session or not getattr(session, "connect_url", None):
                    browser = await p.chromium.launch(headless=True)
                    active_page = await browser.new_page()
                else:
                    browser = await p.chromium.connect_over_cdp(session.connect_url)
                    context = browser.contexts[0] if browser.contexts else await browser.new_context()
                    active_page = context.pages[0] if context.pages else await context.new_page()

                setattr(active_page, "_session_id", session_id)

            # Navigate or load content
            if html_override:
                await active_page.set_content(html_override)
            elif owns_page and target_url and target_url.startswith("http"):
                try:
                    await active_page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                except Exception as e:
                    logger.warning(f"Target page navigation error ({target_url}): {e}")

            # ------------------------------------------------------------------
            # Stage 2: DOM_EXTRACTION (30%)
            # ------------------------------------------------------------------
            report_progress("DOM_EXTRACTION", 30)

            if inspect.iscoroutinefunction(self.dom_extractor.extract_schema):
                dom_schema: FormSchema = await self.dom_extractor.extract_schema(active_page)
            else:
                dom_schema = self.dom_extractor.extract_schema(active_page)

            if not dom_schema.url or dom_schema.url in ("about:blank", ""):
                dom_schema.url = target_url

            # ------------------------------------------------------------------
            # Stage 3: AI_REASONING (50%)
            # ------------------------------------------------------------------
            report_progress("AI_REASONING", 50)

            platform = dom_schema.detected_platform or "generic"
            if (
                platform == "w8ben"
                or "w8ben" in target_url.lower()
                or "w-8ben" in target_url.lower()
                or "tax" in dom_schema.page_title.lower()
            ):
                context = FormContext.W8BEN_CONTRACTOR_COMPLIANCE
            else:
                context = FormContext.ATS_JOB_APPLICATION

            # Retrieve profile scoped strictly to context policy
            profile: MasterIdentityProfile
            try:
                if self.vault_manager.is_initialized() and not self.vault_manager.is_locked:
                    profile = self.vault_manager.get_profile(context=context)
                else:
                    sample = create_sample_profile()
                    profile = self.vault_manager.filter_profile_for_context(sample, context)
            except Exception:
                sample = create_sample_profile()
                profile = self.vault_manager.filter_profile_for_context(sample, context)

            if inspect.iscoroutinefunction(self.ultramarine_client.generate_fill_plan):
                fill_plan: FillPlan = await self.ultramarine_client.generate_fill_plan(
                    dom_schema=dom_schema,
                    user_profile=profile,
                    session_id=session_id,
                )
            else:
                fill_plan = self.ultramarine_client.generate_fill_plan(
                    dom_schema=dom_schema,
                    user_profile=profile,
                    session_id=session_id,
                )

            # ------------------------------------------------------------------
            # Stage 4: CIBA_CONSENT (70%)
            # ------------------------------------------------------------------
            report_progress("CIBA_CONSENT", 70)

            # Map field items to classified attribute names for RFC 9396 RAR diff
            field_dict: Dict[str, Any] = {}
            for item in fill_plan.items:
                fid = item.field_id.lower()
                if "first_name" in fid:
                    k = "full_name"
                elif "last_name" in fid:
                    k = "full_name"
                elif "email" in fid:
                    k = "email"
                elif "phone" in fid or "tel" in fid or "mobile" in fid:
                    k = "phone"
                elif "resume" in fid:
                    k = "resume_markdown"
                elif "linkedin" in fid:
                    k = "linkedin_url"
                elif "github" in fid:
                    k = "github_url"
                elif "portfolio" in fid or "website" in fid:
                    k = "portfolio_url"
                elif "line6a" in fid or "pan" in fid or "ftin" in fid:
                    k = "pan"
                elif "line8" in fid or "dob" in fid or "birth" in fid:
                    k = "date_of_birth"
                elif "article" in fid:
                    k = "tax_treaty_article"
                elif "rate" in fid:
                    k = "treaty_withholding_rate"
                elif "line1_name" in fid or "name" in fid:
                    k = "full_name"
                elif "address" in fid:
                    k = "address"
                elif "city" in fid:
                    k = "city"
                elif "state" in fid:
                    k = "state_province"
                elif "postal" in fid or "zip" in fid:
                    k = "postal_code"
                elif "citizenship" in fid:
                    k = "citizenship"
                elif "country" in fid:
                    k = "country"
                elif "bank" in fid:
                    k = "bank_name"
                elif "account" in fid:
                    k = "account_number"
                else:
                    k = "custom_qa_pairs"
                field_dict[k] = item.value

            diff = FormFillDiff.from_field_values(
                target_url=target_url,
                field_values=field_dict,
                dry_run=dry_run,
            )

            # Initiate CIBA Backchannel Authorization
            try:
                if inspect.iscoroutinefunction(self.auth0_client.initiate_consent):
                    ciba_req = await self.auth0_client.initiate_consent(
                        target_url=target_url,
                        diff=diff,
                        dry_run=dry_run,
                    )
                else:
                    ciba_req = self.auth0_client.initiate_consent(
                        target_url=target_url,
                        diff=diff,
                    )
            except Exception as ciba_init_err:
                if hasattr(self.auth0_client, "initiate_local_fallback"):
                    logger.warning(
                        f"Live Auth0 /bc-authorize unavailable on tenant ({ciba_init_err}); "
                        "falling back to in-app CIBA consent gate."
                    )
                    ciba_req = self.auth0_client.initiate_local_fallback(
                        target_url=target_url,
                        diff=diff,
                        dry_run=dry_run,
                    )
                else:
                    raise

            self.current_auth_req_id = ciba_req.auth_req_id

            # Auto-approval handling if configured
            effective_auto_approve = (
                self.auto_approve_ciba if auto_approve_ciba is None else auto_approve_ciba
            )
            if effective_auto_approve:
                if hasattr(self.auth0_client, "simulate_approval"):
                    self.auth0_client.simulate_approval(ciba_req.auth_req_id)
                elif hasattr(self.auth0_client, "set_user_action"):
                    self.auth0_client.set_user_action(ciba_req.auth_req_id, "approve")

            # Poll for consent: raises RefusalToSubmitError on rejection or timeout
            if inspect.iscoroutinefunction(self.auth0_client.poll_consent):
                consent: ConsentResult = await self.auth0_client.poll_consent(
                    auth_req_id=ciba_req.auth_req_id,
                    timeout=timeout,
                    initial_interval=1,
                )
            else:
                consent = self.auth0_client.poll_consent(
                    auth_req_id=ciba_req.auth_req_id,
                )

            if not consent.approved:
                raise RefusalToSubmitError(
                    f"CIBA Consent refused: {consent.error or 'Consent not approved by user'}"
                )

            # ------------------------------------------------------------------
            # Stage 5: FORM_FILLING (90%)
            # ------------------------------------------------------------------
            report_progress("FORM_FILLING", 90)

            # Handle both FormFiller and SimulatedFormFiller signatures flexibly
            fill_sig = inspect.signature(self.form_filler.fill)
            params = list(fill_sig.parameters.keys())

            if len(params) > 0 and params[0] == "form_schema":
                # SimulatedFormFiller signature: (form_schema, fill_plan, session_id, dry_run=...)
                if inspect.iscoroutinefunction(self.form_filler.fill):
                    result = await self.form_filler.fill(
                        dom_schema, fill_plan, session_id or "sess_local", dry_run=dry_run
                    )
                else:
                    result = self.form_filler.fill(
                        dom_schema, fill_plan, session_id or "sess_local", dry_run=dry_run
                    )
            else:
                # Production FormFiller signature: (page, fill_plan, dry_run=..., session_id=...)
                if inspect.iscoroutinefunction(self.form_filler.fill):
                    result = await self.form_filler.fill(
                        page=active_page,
                        fill_plan=fill_plan,
                        dry_run=dry_run,
                        session_id=session_id,
                    )
                else:
                    result = self.form_filler.fill(
                        page=active_page,
                        fill_plan=fill_plan,
                        dry_run=dry_run,
                        session_id=session_id,
                    )

            # Build dynamic form field diff entries
            diff_entries: List[Dict[str, Any]] = []
            fields_by_sel = {f.selector: f for f in dom_schema.fields if f.selector}
            fields_by_id = {f.field_id: f for f in dom_schema.fields if f.field_id}
            diff_items_by_name = {d.field_name.lower(): d for d in diff.items}

            for item in fill_plan.items:
                matched_field = fields_by_sel.get(item.selector) or fields_by_id.get(item.field_id)
                label = (
                    matched_field.label
                    if matched_field and matched_field.label
                    else item.field_id.replace("_", " ").title()
                )
                fid = item.field_id.lower()
                diff_match = (
                    diff_items_by_name.get(fid)
                    or next((d for k, d in diff_items_by_name.items() if k in fid or fid in k), None)
                )

                field_type_val = (
                    item.field_type.value
                    if hasattr(item.field_type, "value")
                    else str(item.field_type)
                )

                if field_type_val == "file" or item.field_type == FieldType.FILE:
                    val_str = os.path.basename(str(item.value))
                    status_str = "Uploaded"
                    tier_str = SensitivityTier.SEMI_SENSITIVE.value
                elif field_type_val in ("checkbox", "radio") or item.field_type in (FieldType.CHECKBOX, FieldType.RADIO):
                    is_checked = str(item.value).lower() in ("true", "1", "yes")
                    val_str = "Selected" if is_checked else "Unchecked"
                    status_str = "Selected" if is_checked else "Unchecked"
                    tier_str = SensitivityTier.PUBLIC.value
                else:
                    if diff_match and diff_match.masked_value:
                        val_str = diff_match.masked_value
                        tier_str = (
                            diff_match.tier.value
                            if hasattr(diff_match.tier, "value")
                            else str(diff_match.tier)
                        )
                    else:
                        try:
                            tier_obj = get_field_tier(item.field_id)
                            tier_str = (
                                tier_obj.value if hasattr(tier_obj, "value") else str(tier_obj)
                            )
                        except Exception:
                            clean_fid = item.field_id.lower()
                            if any(k in clean_fid for k in ["tax", "pan", "ssn", "tin", "ein"]):
                                tier_str = SensitivityTier.CRITICAL_TAX.value
                            elif any(k in clean_fid for k in ["bank", "account", "routing", "ifsc"]):
                                tier_str = SensitivityTier.CRITICAL_FINANCIAL.value
                            elif any(k in clean_fid for k in ["phone", "address", "resume", "street", "dob", "birth", "essay", "cover"]):
                                tier_str = SensitivityTier.SEMI_SENSITIVE.value
                            else:
                                tier_str = SensitivityTier.PUBLIC.value

                        try:
                            val_str = mask_sensitive_value(item.field_id, str(item.value))
                        except Exception:
                            val_str = str(item.value)
                    status_str = "Filled"

                diff_entries.append(
                    {
                        "field": label,
                        "selector": item.selector,
                        "field_type": field_type_val,
                        "value": val_str,
                        "tier": tier_str,
                        "status": status_str,
                    }
                )

            # Append policy-redacted attributes to diff for transparency
            for rf in getattr(diff, "fields_redacted", []):
                try:
                    tier_obj = get_field_tier(rf)
                    tier_str = tier_obj.value if hasattr(tier_obj, "value") else str(tier_obj)
                except Exception:
                    tier_str = SensitivityTier.CRITICAL_TAX.value
                diff_entries.append(
                    {
                        "field": rf.replace("_", " ").title(),
                        "selector": "n/a",
                        "field_type": "n/a",
                        "value": "REDACTED (Context Protected)",
                        "tier": tier_str,
                        "status": "Protected",
                    }
                )

            if hasattr(result, "diff"):
                result.diff = diff_entries

            # ------------------------------------------------------------------
            # Stage 6: COMPLETED (100%)
            # ------------------------------------------------------------------
            report_progress("COMPLETED", 100)
            return result

        finally:
            # Cleanup local browser sandbox if created by orchestrator
            if owns_page and browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if owns_page and playwright_cm:
                try:
                    await playwright_cm.stop()
                except Exception:
                    pass

            # Mandatory Browserbase session release to stop cloud billing and finalize replay
            if session_id and hasattr(self.browserbase_service, "release_session"):
                try:
                    self.browserbase_service.release_session(session_id)
                except Exception as e:
                    logger.warning(f"Error releasing Browserbase session {session_id}: {e}")

    def run_sync(self, *args, **kwargs) -> FillResult:
        """Synchronous wrapper for run."""
        return asyncio.run(self.run(*args, **kwargs))
