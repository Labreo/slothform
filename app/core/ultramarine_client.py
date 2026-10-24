"""Paper Instruments Ultramarine 1 Flash Client with Sticky Caching and Heuristic Fallback."""

import hashlib
import json
import logging
import os
from typing import Any, List, Optional

import httpx
from openai import AsyncOpenAI

from app.config import get_settings
from app.models.browser_schema import (
    FieldType,
    FillPlan,
    FillPlanItem,
    FormSchema,
)
from app.models.identity_schema import MasterIdentityProfile
logger = logging.getLogger(__name__)


class UltramarineClient:
    """Native asynchronous client for Paper Instruments Ultramarine 1 Flash reasoning engine.
    
    Features:
    - Target: https://api.paperinstruments.com/v1 (model ultramarine-1-flash).
    - Sticky prompt caching: sends x-session-id computed deterministically from target form URL.
    - Pydantic structured output validation: parses model completions into validated FillPlan.
    - Deterministic offline fallback engine: handles zero-credential environments, CI runs,
      and remote API errors without external network dependencies.
    """

    DEFAULT_BASE_URL = "https://api.paperinstruments.com/v1"
    DEFAULT_MODEL = "ultramarine-1-flash"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        offline_mode: Optional[bool] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or os.getenv("PAPER_INSTRUMENTS_API_KEY") or settings.PAPER_INSTRUMENTS_API_KEY
        self.model = model or os.getenv("ULTRAMARINE_MODEL") or settings.ULTRAMARINE_MODEL or self.DEFAULT_MODEL
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")

        # Determine offline mode
        if offline_mode is not None:
            self.offline_mode = offline_mode
        else:
            self.offline_mode = bool(
                not self.api_key
                or self.api_key.startswith("pi_live_dummy")
                or self.api_key in ("dummy", "test", "offline", "pi_live_your_")
            )

        from app.services.essay_synthesizer import EssaySynthesizer, W8BENResolver
        self.w8ben_resolver = W8BENResolver()
        self.essay_synthesizer = EssaySynthesizer()

        if not self.offline_mode:
            try:
                self.client: Optional[AsyncOpenAI] = AsyncOpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    http_client=http_client,
                )
            except Exception as e:
                logger.warning(f"Could not initialize AsyncOpenAI client for Ultramarine: {e}")
                self.client = None
                self.offline_mode = True
        else:
            self.client = None

    @staticmethod
    def compute_session_id(target_url: str) -> str:
        """Compute deterministic sticky session ID from the target form URL hash.
        
        Format: sess_{sha256(url)[:12]}
        """
        digest = hashlib.sha256(target_url.encode("utf-8")).hexdigest()[:12]
        return f"sess_{digest}"

    def build_system_prompt(self) -> str:
        """Construct the authoritative document reasoning system prompt for Ultramarine 1 Flash."""
        return (
            "You are the SlothForm Ultramarine Document Reasoning Engine, powered by Paper Instruments "
            "Ultramarine 1 Flash. You are given an interactive DOM schema extracted from a target web form "
            "and a verified MasterIdentityProfile from the user's encrypted identity vault.\n\n"
            "Your objective is to reason over the schema and emit a strictly validated JSON FillPlan adhering "
            "to these mandatory domain rules:\n"
            "1. Ground Truth Invariant: Never hallucinate skills, metrics, certifications, or past employers "
            "not explicitly present in the candidate's verified career profile.\n"
            "2. IRS Form W-8BEN Tax Rules:\n"
            "   - Line 1: Full legal name.\n"
            "   - Line 2: Country of citizenship ('India').\n"
            "   - Line 3: Permanent residence street address.\n"
            "   - Line 3 City/State/Postal: Formatted city, state/province, and postal code.\n"
            "   - Line 6a: Foreign Tax Identifying Number strictly mapped to Indian PAN ([A-Z]{5}[0-9]{4}[A-Z]).\n"
            "   - Line 6b: 'Check if FTIN not legally required' MUST be unchecked ('false'). India legally mandates PAN.\n"
            "   - Line 8: Date of birth strictly formatted to MM-DD-YYYY per IRS rules.\n"
            "   - Line 9: Country of residence for tax purposes ('India').\n"
            "   - Line 10: US-India DTAA Article 12(2) claiming 15% withholding rate for technical services/royalties.\n"
            "   - Signature: Full legal name; Capacity: 'Self'.\n"
            "3. Essay Synthesis: Tailor rich, compelling technical responses (150-250 words) strictly grounded "
            "in the candidate's actual years of experience and verified skillset.\n"
            "4. Output Format: Emit only valid JSON conforming strictly to the FillPlan Pydantic schema: "
            "{\"target_url\": str, \"items\": [{\"field_id\": str, \"selector\": str, \"field_type\": str, "
            "\"value\": any, \"frame_index\": int}], \"resume_path\": str or null}."
        )

    def build_user_prompt(self, dom_schema: FormSchema, user_profile: MasterIdentityProfile) -> str:
        """Construct the serialized payload prompt containing the target schema and profile."""
        payload = {
            "target_form": dom_schema.model_dump(),
            "candidate_profile": {
                "core": user_profile.core.model_dump(),
                "tax": user_profile.tax.model_dump(),
                "career": {
                    "headline": user_profile.career.headline,
                    "years_of_experience": user_profile.career.years_of_experience,
                    "skills": user_profile.career.skills,
                    "github_url": user_profile.career.github_url,
                    "linkedin_url": user_profile.career.linkedin_url,
                    "portfolio_url": user_profile.career.portfolio_url,
                    "work_history": user_profile.career.work_history,
                    "education_degree": user_profile.career.education_degree,
                    "education_university": user_profile.career.education_university,
                    "education_grad_year": user_profile.career.education_grad_year,
                    "education_gpa": user_profile.career.education_gpa,
                    "bio": user_profile.career.bio,
                    "custom_qa_pairs": user_profile.career.custom_qa_pairs,
                },
            },
        }
        return json.dumps(payload, indent=2)

    async def generate_fill_plan(
        self,
        dom_schema: FormSchema,
        user_profile: MasterIdentityProfile,
        session_id: Optional[str] = None,
    ) -> FillPlan:
        """Generate a validated FillPlan using Ultramarine 1 Flash with sticky caching and offline fallback."""
        effective_session_id = session_id or self.compute_session_id(dom_schema.url)

        if self.offline_mode or not self.client:
            logger.info(f"Using deterministic offline heuristic engine for {dom_schema.url}")
            return self.heuristic_fallback(dom_schema, user_profile, effective_session_id)

        try:
            extra_headers = {"x-session-id": effective_session_id}
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.build_system_prompt()},
                    {"role": "user", "content": self.build_user_prompt(dom_schema, user_profile)},
                ],
                response_format={"type": "json_object"},
                extra_headers=extra_headers,
            )

            raw_content = response.choices[0].message.content
            if not raw_content:
                raise ValueError("Received empty content from Ultramarine API")

            data = json.loads(raw_content)
            if "target_url" not in data or not data["target_url"]:
                data["target_url"] = dom_schema.url

            plan = FillPlan.model_validate(data)
            if len(plan.items) == 0 and len(dom_schema.fields) > 0:
                logger.warning(
                    f"Ultramarine returned empty plan items ({len(plan.items)}) "
                    f"despite schema having {len(dom_schema.fields)} fields. "
                    "Treating as model schema deviation / incomplete plan and falling back."
                )
                return self.heuristic_fallback(dom_schema, user_profile, effective_session_id)

            logger.info(
                f"Generated FillPlan via live Ultramarine API: {len(plan.items)} items "
                f"(session: {effective_session_id})"
            )
            return plan

        except Exception as e:
            logger.warning(
                f"Live Ultramarine API reasoning failed ({e}). Falling back to heuristic fallback engine."
            )
            return self.heuristic_fallback(dom_schema, user_profile, effective_session_id)

    def heuristic_fallback(
        self,
        dom_schema: FormSchema,
        user_profile: MasterIdentityProfile,
        session_id: Optional[str] = None,
    ) -> FillPlan:
        """Deterministic rule-based reasoning engine implementing exact domain and schema mappings."""
        platform = dom_schema.detected_platform or "generic"
        is_tax_form = (
            platform == "w8ben"
            or "w8ben" in dom_schema.url.lower()
            or "w-8ben" in dom_schema.url.lower()
            or "tax" in dom_schema.page_title.lower()
        )

        items: List[FillPlanItem] = []

        if is_tax_form:
            # Delegate directly to IRS Form W-8BEN domain resolver
            items = self.w8ben_resolver.resolve_tax_fields(
                dom_schema=dom_schema,
                tax_profile=user_profile.tax,
                core_profile=user_profile.core,
                strict_pan=False,
            )
            return FillPlan(
                target_url=dom_schema.url,
                items=items,
                resume_path="/tmp/synthetic_w8ben.pdf",
            )

        # ATS Job Applications (Greenhouse, Lever, Ashby, Generic)
        for field in dom_schema.fields:
            fid = field.field_id.lower()
            fname = (field.name_attr or "").lower()
            flabel = field.label.lower()
            fsel = field.selector.lower()
            fctx = f"{fid} {fname} {flabel} {fsel}"

            val: Any = None

            # First Name
            if (
                "first_name" in fid
                or "first_name" in fname
                or "first-name" in fid
                or "first name" in flabel
            ):
                parts = user_profile.core.full_name.split(" ", 1)
                val = parts[0]

            # Last Name
            elif (
                "last_name" in fid
                or "last_name" in fname
                or "last-name" in fid
                or "last name" in flabel
            ):
                parts = user_profile.core.full_name.split(" ", 1)
                val = parts[1] if len(parts) > 1 else ""

            # Full Name
            elif (
                fid in ("name", "full_name", "_systemfield_name")
                or fname in ("name", "full_name")
                or "full name" in flabel
                or flabel.strip().lower() == "name"
                or "your name" in flabel
            ):
                val = user_profile.core.full_name

            # Email
            elif (
                field.field_type == FieldType.EMAIL
                or "email" in fid
                or "email" in fname
                or "email" in flabel
            ):
                val = user_profile.core.email

            # Phone
            elif (
                field.field_type == FieldType.TEL
                or "phone" in fid
                or "phone" in fname
                or "mobile" in flabel
                or "phone" in flabel
            ):
                val = user_profile.core.phone

            # LinkedIn
            elif "linkedin" in fctx:
                val = user_profile.career.linkedin_url

            # GitHub
            elif "github" in fctx:
                val = user_profile.career.github_url

            # Portfolio / Website
            elif (
                "portfolio" in fctx
                or "website" in fctx
                or "personal website" in flabel
                or "blog" in flabel
            ):
                val = user_profile.career.portfolio_url or ""

            # Current Employer / Company / Org
            elif "company" in flabel or "org" in fid or "current employer" in flabel or fname == "org":
                val = "Self-Employed / Independent Contractor"

            # Work History / Past Experience
            elif (
                "work_history" in fctx
                or "work history" in flabel
                or "employment history" in flabel
                or "past employers" in flabel
                or "experience" in flabel
            ):
                val = user_profile.career.work_history or user_profile.career.headline

            # Professional Bio / Summary
            elif (
                "bio" in fctx
                or "summary" in fctx
                or "about you" in flabel
                or "about yourself" in flabel
            ):
                val = user_profile.career.bio or user_profile.career.headline

            # Education / Degree / University
            elif "university" in fctx or "school" in fctx or "college" in fctx:
                val = user_profile.career.education_university or ""
            elif "degree" in fctx:
                val = user_profile.career.education_degree or ""
            elif "graduation" in fctx or "grad_year" in fctx:
                val = user_profile.career.education_grad_year or ""
            elif "gpa" in fctx:
                val = user_profile.career.education_gpa or ""

            # Street Address
            elif "address" in flabel or "address_line1" in fid or "street" in flabel:
                val = user_profile.core.address_line1

            # City
            elif "city" in flabel or "city" in fid:
                val = user_profile.core.city

            # State / Province
            elif "state" in flabel or "province" in flabel or "state" in fid:
                val = user_profile.core.state_province

            # Postal / Zip Code
            elif "postal" in flabel or "zip" in flabel or "postal" in fid or "zip" in fid:
                val = user_profile.core.postal_code

            # Country
            elif "country" in flabel or "country" in fid:
                val = user_profile.core.country

            # File Uploads (Resume)
            elif field.field_type == FieldType.FILE:
                val = "/tmp/synthetic_resume.pdf"

            # Textareas / Essays
            elif field.field_type == FieldType.TEXTAREA:
                val = self.essay_synthesizer.synthesize_essay(
                    prompt=field.label or field.field_id,
                    career_profile=user_profile.career,
                )

            # Combobox / Autocomplete
            elif field.field_type == FieldType.COMBOBOX:
                val = user_profile.core.country

            # Select Dropdowns
            elif field.field_type == FieldType.SELECT:
                # Match options against profile if available
                matched_val = None
                country_clean = (user_profile.core.country or "").strip().lower()
                if field.options:
                    for opt in field.options:
                        olabel = opt.label.lower()
                        oval = opt.value.lower()
                        if country_clean and (country_clean in olabel or country_clean in oval):
                            matched_val = opt.value
                            break
                        if any(skill.lower() in olabel for skill in user_profile.career.skills):
                            matched_val = opt.value
                            break
                    if not matched_val:
                        non_empty = [o.value for o in field.options if o.value]
                        matched_val = non_empty[0] if non_empty else "true"
                val = matched_val or "true"

            # Checkbox
            elif field.field_type == FieldType.CHECKBOX:
                # Terms, agreements, and work authorizations are consented
                val = True

            # Radios
            elif field.field_type == FieldType.RADIO:
                val = True

            if val is not None:
                items.append(
                    FillPlanItem(
                        field_id=field.field_id,
                        selector=field.selector,
                        field_type=field.field_type,
                        value=val,
                        frame_index=field.frame_index,
                    )
                )

        return FillPlan(
            target_url=dom_schema.url,
            items=items,
            resume_path="/tmp/synthetic_resume.pdf",
        )

    def generate_fill_plan_sync(
        self,
        dom_schema: FormSchema,
        user_profile: MasterIdentityProfile,
        session_id: Optional[str] = None,
    ) -> FillPlan:
        """Synchronous convenience wrapper for generate_fill_plan (invokes heuristic fallback)."""
        effective_session_id = session_id or self.compute_session_id(dom_schema.url)
        return self.heuristic_fallback(dom_schema, user_profile, effective_session_id)

    # Alias for private invocation compatibility
    _heuristic_fallback = heuristic_fallback
