"""SlothForm FastAPI Application Backend.

Features:
- REST API endpoints for triggers, task inspection, and vault management
- Server-Sent Events (SSE) live telemetry stream (/api/tasks/{task_id}/events)
- Health check with subsystem readiness assessment (/health)
- Dark luxury Jinja2 web dashboard (/ and /tasks/{task_id})
"""

import asyncio
from contextlib import asynccontextmanager
import inspect
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import get_settings
from app.core.vault import VaultManager, create_sample_profile
from app.models.ciba_schema import RefusalToSubmitError
from app.models.identity_schema import (
    MasterIdentityProfile,
    mask_sensitive_value,
)
from app.services.fill_orchestrator import FillOrchestrator

logger = logging.getLogger("slothform.app")

# Track server start time for uptime reporting
SERVER_START_TIME = time.time()

# In-memory storage for background task state and SSE broadcast queues
tasks_db: Dict[str, Dict[str, Any]] = {}
task_events: Dict[str, List[Dict[str, Any]]] = {}
task_subscribers: Dict[str, Set[asyncio.Queue]] = {}

# In-memory storage for active task orchestrators
task_orchestrators: Dict[str, Any] = {}

# Injectable orchestrator factory for deterministic testing
_ORCHESTRATOR_FACTORY: Optional[Callable[..., Any]] = None


def set_fill_orchestrator(factory: Optional[Callable[..., Any]]) -> None:
    """Set custom orchestrator factory for testing."""
    global _ORCHESTRATOR_FACTORY
    _ORCHESTRATOR_FACTORY = factory


def get_fill_orchestrator(auto_approve_ciba: Optional[bool] = None) -> Any:
    """Retrieve active orchestrator instance with configurable CIBA consent."""
    if _ORCHESTRATOR_FACTORY:
        try:
            return _ORCHESTRATOR_FACTORY(auto_approve_ciba=auto_approve_ciba)
        except TypeError:
            return _ORCHESTRATOR_FACTORY()
    settings = get_settings()
    effective_auto_approve = (
        auto_approve_ciba
        if auto_approve_ciba is not None
        else (settings.AUTH0_CIBA_AUTO_APPROVE or settings.AUTH0_OFFLINE_MODE)
    )
    return FillOrchestrator(auto_approve_ciba=effective_auto_approve)


STAGE_DESCRIPTIONS = {
    "SESSION_INIT": "Provisioning Browserbase cloud session with residential proxies...",
    "DOM_EXTRACTION": "Extracting interactive DOM form inputs, selects, and textareas...",
    "AI_REASONING": "Paper Instruments Ultramarine synthesizing grounded fill plan...",
    "CIBA_CONSENT": "Verifying Auth0 CIBA backchannel consent (RFC 9396 RAR diff)...",
    "FORM_FILLING": "Executing Playwright form filling & amber safety guard...",
    "COMPLETED": "Form fill execution finalized successfully.",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI application lifespan manager."""
    global SERVER_START_TIME
    SERVER_START_TIME = time.time()
    # Ensure vault storage directory exists
    settings = get_settings()
    vault_path = os.path.dirname(settings.VAULT_FILE_PATH)
    if vault_path:
        os.makedirs(vault_path, exist_ok=True)
    vault_mgr = VaultManager()
    if not vault_mgr.is_locked and not vault_mgr.is_initialized():
        try:
            vault_mgr.save_profile(create_sample_profile())
        except Exception as e:
            logger.warning(f"Could not bootstrap default vault on startup: {e}")
    yield


app = FastAPI(
    title="SlothForm API",
    version="1.0.0",
    description="Autonomous Privacy-Preserving Form-Filling Agent API",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and Jinja2 templates
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
templates = Jinja2Templates(directory="app/web/templates")


# ------------------------------------------------------------------------------
# Request / Response Models
# ------------------------------------------------------------------------------

class FillRequest(BaseModel):
    """Payload for submitting a target form to the fill pipeline."""
    url: str
    dry_run: bool = True
    auto_approve_ciba: Optional[bool] = None


class ConsentDecisionRequest(BaseModel):
    """Payload for approving or rejecting a task's CIBA consent request."""
    approved: bool


class FillResponse(BaseModel):
    """Response returned upon successfully initiating a form fill task."""
    task_id: str
    status: str
    dry_run: bool


# ------------------------------------------------------------------------------
# Event Broadcasting Helpers
# ------------------------------------------------------------------------------

def broadcast_event(task_id: str, event_data: Dict[str, Any]) -> None:
    """Record event in task history and push to all active SSE subscriber queues."""
    if task_id not in task_events:
        task_events[task_id] = []

    if "event_id" not in event_data:
        event_data["event_id"] = f"{task_id}:{len(task_events[task_id])}"

    task_events[task_id].append(event_data)

    if task_id in task_subscribers:
        for q in list(task_subscribers[task_id]):
            try:
                q.put_nowait(event_data)
            except Exception:
                pass


async def run_fill_pipeline(
    task_id: str,
    url: str,
    dry_run: bool,
    auto_approve_ciba: Optional[bool] = None,
) -> None:
    """Execute fill orchestrator in background task and broadcast SSE telemetry."""
    if task_id not in tasks_db:
        return

    tasks_db[task_id]["status"] = "running"

    def progress_callback(stage: str, percentage: int) -> None:
        now = time.time()
        desc = STAGE_DESCRIPTIONS.get(stage, f"Executing {stage}...")
        event = {
            "stage": stage,
            "percentage": percentage,
            "message": desc,
            "timestamp": now,
        }
        if task_id in tasks_db:
            tasks_db[task_id]["current_stage"] = stage
            tasks_db[task_id]["progress_percentage"] = percentage
            tasks_db[task_id]["updated_at"] = now
        broadcast_event(task_id, event)

    try:
        orchestrator = get_fill_orchestrator(auto_approve_ciba=auto_approve_ciba)
        task_orchestrators[task_id] = orchestrator

        kwargs: Dict[str, Any] = {}
        if hasattr(orchestrator, "run"):
            run_sig = inspect.signature(orchestrator.run)
            params = run_sig.parameters
            if "auto_approve_ciba" in params or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            ):
                kwargs["auto_approve_ciba"] = auto_approve_ciba

        # Support both async run and sync run
        if asyncio.iscoroutinefunction(orchestrator.run):
            result = await orchestrator.run(
                target_url=url,
                dry_run=dry_run,
                progress_callback=progress_callback,
                **kwargs,
            )
        else:
            result = orchestrator.run(
                target_url=url,
                dry_run=dry_run,
                progress_callback=progress_callback,
                **kwargs,
            )

        # Convert result to dict
        result_dict = result.model_dump() if hasattr(result, "model_dump") else result.__dict__

        now = time.time()
        tasks_db[task_id]["status"] = "completed"
        tasks_db[task_id]["current_stage"] = "COMPLETED"
        tasks_db[task_id]["progress_percentage"] = 100
        tasks_db[task_id]["result"] = result_dict
        tasks_db[task_id]["diff"] = result_dict.get("diff", [])
        tasks_db[task_id]["screenshot_path"] = result_dict.get("screenshot_path")
        tasks_db[task_id]["replay_url"] = result_dict.get("replay_url")
        tasks_db[task_id]["updated_at"] = now

        final_event = {
            "stage": "COMPLETED",
            "percentage": 100,
            "message": "Form filling completed successfully.",
            "timestamp": now,
            "result": result_dict,
        }
        broadcast_event(task_id, final_event)

    except RefusalToSubmitError as e:
        now = time.time()
        tasks_db[task_id]["status"] = "refused"
        tasks_db[task_id]["error"] = str(e)
        tasks_db[task_id]["updated_at"] = now
        err_event = {
            "stage": "REFUSED",
            "percentage": tasks_db[task_id].get("progress_percentage", 0),
            "message": f"CIBA Consent refused: {e}",
            "timestamp": now,
            "error": str(e),
        }
        broadcast_event(task_id, err_event)

    except Exception as e:
        now = time.time()
        logger.exception(f"Error executing task {task_id}: {e}")
        tasks_db[task_id]["status"] = "failed"
        tasks_db[task_id]["error"] = str(e)
        tasks_db[task_id]["updated_at"] = now
        err_event = {
            "stage": "FAILED",
            "percentage": tasks_db[task_id].get("progress_percentage", 0),
            "message": f"Pipeline failure: {e}",
            "timestamp": now,
            "error": str(e),
        }
        broadcast_event(task_id, err_event)


# ------------------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Health check endpoint returning system status and subsystem readiness."""
    settings = get_settings()
    vault_mgr = VaultManager()

    # Determine vault readiness
    vault_status = "ready" if vault_mgr.is_initialized() else "uninitialized"
    if vault_mgr.is_locked:
        vault_status = "locked"

    # Determine cloud API readiness
    bb_key = settings.BROWSERBASE_API_KEY
    bb_ready = bool(bb_key and bb_key != "bb_live_dummy")

    pi_key = settings.PAPER_INSTRUMENTS_API_KEY
    pi_ready = bool(pi_key and pi_key != "pi_live_dummy")

    return {
        "status": "healthy",
        "service": "slothform",
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0",
        "timestamp": time.time(),
        "uptime_seconds": round(time.time() - SERVER_START_TIME, 2),
        "subsystems": {
            "vault": vault_status,
            "browserbase": "ready" if bb_ready else "offline_fallback",
            "ultramarine": "ready" if pi_ready else "offline_fallback",
        },
    }


@app.post("/api/fill", response_model=FillResponse, status_code=status.HTTP_200_OK)
async def submit_fill_task(req: FillRequest):
    """Validate target URL and launch asynchronous form-filling background task."""
    url = req.url.strip() if req.url else ""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid URL. Target form URL must start with http:// or https://",
        )

    task_id = str(uuid.uuid4())
    now = time.time()

    tasks_db[task_id] = {
        "task_id": task_id,
        "url": url,
        "dry_run": req.dry_run,
        "auto_approve_ciba": req.auto_approve_ciba,
        "status": "pending",
        "current_stage": "PENDING",
        "progress_percentage": 0,
        "created_at": now,
        "updated_at": now,
        "result": None,
        "diff": [],
        "screenshot_path": None,
        "replay_url": None,
        "error": None,
    }
    task_events[task_id] = []
    task_subscribers[task_id] = set()

    # Trigger async execution in event loop background
    asyncio.create_task(
        run_fill_pipeline(
            task_id, url, req.dry_run, auto_approve_ciba=req.auto_approve_ciba
        )
    )

    return FillResponse(
        task_id=task_id,
        status="pending",
        dry_run=req.dry_run,
    )


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Return task metadata, current stage, progress percentage, and results."""
    if task_id not in tasks_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID '{task_id}' not found.",
        )
    return tasks_db[task_id]


@app.post("/api/tasks/{task_id}/consent")
async def record_task_consent(task_id: str, req: ConsentDecisionRequest):
    """Approve or reject a pending CIBA backchannel consent request for a task."""
    if task_id not in tasks_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID '{task_id}' not found.",
        )

    orch = task_orchestrators.get(task_id)
    auth_req_id = getattr(orch, "current_auth_req_id", None) if orch else None

    if orch and hasattr(orch, "auth0_client"):
        client = orch.auth0_client
        if (
            auth_req_id
            and hasattr(client, "_sim_requests")
            and auth_req_id in client._sim_requests
        ):
            if req.approved:
                client.simulate_approval(auth_req_id)
            else:
                client.simulate_denial(auth_req_id)
        elif hasattr(client, "simulate_approval"):
            for req_id in list(getattr(client, "_sim_requests", {}).keys()):
                if req.approved:
                    client.simulate_approval(req_id)
                else:
                    client.simulate_denial(req_id)

    tasks_db[task_id]["consent_decision"] = req.approved
    return {
        "task_id": task_id,
        "approved": req.approved,
        "status": "approved" if req.approved else "rejected",
    }


@app.get("/api/tasks/{task_id}/events")
async def stream_task_events(task_id: str, request: Request):
    """Server-Sent Events (SSE) streaming endpoint emitting real-time progress events."""
    if task_id not in tasks_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID '{task_id}' not found.",
        )

    queue: asyncio.Queue = asyncio.Queue()
    if task_id not in task_subscribers:
        task_subscribers[task_id] = set()
    task_subscribers[task_id].add(queue)

    async def event_generator():
        seen_events: Set[str] = set()
        try:
            # 1. Replay historical events
            past_events = list(task_events.get(task_id, []))
            for evt in past_events:
                evt_key = evt.get("event_id") or f"{evt.get('stage')}:{evt.get('percentage')}:{evt.get('timestamp')}:{evt.get('message')}"
                seen_events.add(evt_key)
                yield f"data: {json.dumps(evt)}\n\n"

            # If task is already finished, complete stream
            if tasks_db[task_id]["status"] in ("completed", "failed", "refused"):
                return

            # 2. Stream new live events with deduplication
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=1.0)
                    evt_key = evt.get("event_id") or f"{evt.get('stage')}:{evt.get('percentage')}:{evt.get('timestamp')}:{evt.get('message')}"
                    if evt_key in seen_events:
                        continue
                    seen_events.add(evt_key)
                    yield f"data: {json.dumps(evt)}\n\n"
                    if evt.get("stage") in ("COMPLETED", "FAILED", "REFUSED"):
                        break
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    # Check if task finished in meantime
                    if tasks_db[task_id]["status"] in ("completed", "failed", "refused"):
                        break
                    # Send periodic keep-alive comment
                    yield ": keepalive\n\n"
        finally:
            if task_id in task_subscribers and queue in task_subscribers[task_id]:
                task_subscribers[task_id].remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def mask_profile(profile: MasterIdentityProfile) -> Dict[str, Any]:
    """Produce masked identity profile dictionary for safe client exposure."""
    return {
        "core": {
            "full_name": profile.core.full_name,
            "email": profile.core.email,
            "phone": mask_sensitive_value("phone", profile.core.phone),
            "address_line1": mask_sensitive_value("address", profile.core.address_line1),
            "address_line2": mask_sensitive_value("address", profile.core.address_line2) if profile.core.address_line2 else None,
            "city": profile.core.city,
            "state_province": profile.core.state_province,
            "postal_code": profile.core.postal_code,
            "country": profile.core.country,
            "citizenship": profile.core.citizenship,
            "date_of_birth": mask_sensitive_value("date_of_birth", profile.core.date_of_birth) if profile.core.date_of_birth else None,
        },
        "tax": {
            "tax_residence_country": profile.tax.tax_residence_country,
            "pan": mask_sensitive_value("pan", profile.tax.pan) if profile.tax.pan else None,
            "ssn_itin": mask_sensitive_value("ssn_itin", profile.tax.ssn_itin) if profile.tax.ssn_itin else None,
            "has_us_tax_id": profile.tax.has_us_tax_id,
            "tax_treaty_country": profile.tax.tax_treaty_country,
            "tax_treaty_article": profile.tax.tax_treaty_article,
            "treaty_withholding_rate": profile.tax.treaty_withholding_rate,
            "treaty_income_type": profile.tax.treaty_income_type,
            "claim_treaty_benefits": profile.tax.claim_treaty_benefits,
        },
        "career": {
            "headline": profile.career.headline,
            "years_of_experience": profile.career.years_of_experience,
            "skills": profile.career.skills,
            "resume_markdown": profile.career.resume_markdown[:120] + "... [TRUNCATED]" if profile.career.resume_markdown else "",
            "github_url": profile.career.github_url,
            "linkedin_url": profile.career.linkedin_url,
            "portfolio_url": profile.career.portfolio_url,
            "custom_qa_pairs": profile.career.custom_qa_pairs,
        },
        "financial": {
            "bank_name": profile.financial.bank_name,
            "account_number": mask_sensitive_value("account_number", profile.financial.account_number) if profile.financial.account_number else None,
            "routing_ifsc": mask_sensitive_value("routing_ifsc", profile.financial.routing_ifsc) if profile.financial.routing_ifsc else None,
            "swift_bic": profile.financial.swift_bic,
            "wise_recipient_id": mask_sensitive_value("wise_recipient_id", profile.financial.wise_recipient_id) if profile.financial.wise_recipient_id else None,
        },
    }


@app.get("/api/vault")
async def get_vault_profile():
    """Retrieve masked MasterIdentityProfile from local encrypted vault."""
    vault = VaultManager()
    try:
        if vault.is_initialized() and not vault.is_locked:
            profile = vault.load_profile()
        else:
            profile = create_sample_profile()
    except Exception:
        profile = create_sample_profile()

    return mask_profile(profile)


@app.post("/api/vault")
async def update_vault_profile(profile: MasterIdentityProfile):
    """Encrypt and store updated MasterIdentityProfile in local vault."""
    vault = VaultManager()
    if vault.is_locked:
        settings = get_settings()
        key = os.getenv("AUTH0_TOKEN_VAULT_KEY") or settings.AUTH0_TOKEN_VAULT_KEY
        if key:
            vault.unlock(key)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vault is locked and no AUTH0_TOKEN_VAULT_KEY is configured.",
            )

    try:
        vault.save_profile(profile)
        return {
            "status": "saved",
            "message": "Master identity profile encrypted and stored successfully.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to encrypt and persist profile: {e}",
        )


# ------------------------------------------------------------------------------
# HTML Template Routes
# ------------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request):
    """Render main SlothForm web dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "SlothForm — Autonomous Privacy-Preserving Form-Filling Agent",
        },
    )


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail_view(request: Request, task_id: str):
    """Render task detail view with live EventSource telemetry connection."""
    task = tasks_db.get(task_id, {})
    return templates.TemplateResponse(
        request=request,
        name="task_detail.html",
        context={
            "task_id": task_id,
            "target_url": task.get("url", ""),
            "title": f"SlothForm Task — {task_id[:8]}",
        },
    )
