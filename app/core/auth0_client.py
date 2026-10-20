"""Auth0 CIBA (Client-Initiated Backchannel Authentication) and RAR Security Subsystem."""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.models.ciba_schema import (
    CIBAError,
    CIBARequest,
    CIBAState,
    ConsentResult,
    ConsentTimeoutError,
    FormFillDiff,
    RefusalToSubmitError,
    RichAuthorizationDetail,
)

logger = logging.getLogger("slothform.ciba")


def generate_binding_message(target_url: str, digest: str, dry_run: bool = False) -> str:
    """Generate a human-readable binding message bounded to 64 characters (RFC recommendation).
    
    Format: SlothForm: [DRY] Apply to {domain} [sha:{digest[:8]}]
    """
    domain = urlparse(target_url).netloc.replace("www.", "") or "target"
    prefix = "[DRY] " if dry_run else ""
    short_sha = digest.split(":")[-1][:8] if ":" in digest else digest[:8]
    suffix = f" [sha:{short_sha}]"
    base = f"SlothForm: {prefix}Apply to {domain}"
    
    # 64 characters hard limit
    if len(base) + len(suffix) > 64:
        allowed_base_len = 64 - len(suffix) - 3
        base = base[:allowed_base_len] + "..."
    msg = f"{base}{suffix}"
    return msg[:64]


class Auth0CIBAClient:
    """Asynchronous client for Auth0 CIBA flow with RFC 9396 Rich Authorization Requests."""

    CIBA_GRANT_TYPE = "urn:openid:params:grant-type:ciba"
    DEFAULT_TIMEOUT_SEC = 300
    DEFAULT_POLL_INTERVAL_SEC = 5

    def __init__(
        self,
        domain: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        audience: Optional[str] = None,
        login_hint: Optional[str] = None,
        offline_mode: Optional[bool] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        settings = get_settings()
        self.domain = (domain or settings.AUTH0_DOMAIN).replace("https://", "").rstrip("/")
        self.client_id = client_id or settings.AUTH0_CLIENT_ID
        self.client_secret = client_secret or settings.AUTH0_CLIENT_SECRET
        self.audience = audience or settings.AUTH0_AUDIENCE
        self.login_hint = login_hint or "user@slothform.internal"

        # Determine offline mode: if explicitly passed, use it; otherwise check settings or dummy domain
        if offline_mode is not None:
            self.offline_mode = offline_mode
        else:
            self.offline_mode = (
                settings.AUTH0_OFFLINE_MODE
                or "your-tenant" in self.domain
                or "dummy" in self.client_id
            )

        self._http_client = http_client
        self._owns_http_client = http_client is None

        # In-memory simulator registry for offline deterministic execution
        self._sim_requests: Dict[str, Dict[str, Any]] = {}

    async def get_http_client(self) -> httpx.AsyncClient:
        """Retrieve or construct the shared async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
            self._owns_http_client = True
        return self._http_client

    async def close(self) -> None:
        """Close underlying HTTP client session."""
        if self._owns_http_client and self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def initiate_consent(
        self, target_url: str, diff: FormFillDiff, dry_run: bool = False
    ) -> CIBARequest:
        """Initiate asynchronous backchannel authentication for proposed form fill.
        
        Interface Contract:
            Auth0CIBAClient.initiate_consent(target_url: str, diff: FormFillDiff, dry_run: bool) -> CIBARequest
        """
        binding_msg = generate_binding_message(target_url, diff.digest, dry_run=dry_run)
        rar_detail = RichAuthorizationDetail.from_diff(diff)
        rar_json = json.dumps([rar_detail.model_dump()])

        if self.offline_mode:
            auth_req_id = f"ciba_sim_{uuid.uuid4().hex[:16]}"
            self._sim_requests[auth_req_id] = {
                "state": CIBAState.PENDING,
                "poll_count": 0,
                "pending_cycles": 1,
                "slow_down_cycles": 0,
                "final_decision": "approved",
                "diff": diff,
                "target_url": target_url,
                "created_at": time.time(),
                "expires_in": 300,
                "interval": self.DEFAULT_POLL_INTERVAL_SEC,
                "binding_message": binding_msg,
                "access_token": f"eyJhbGciOiJSUzI1NiJ9.simulated_token_{uuid.uuid4().hex[:12]}",
            }
            logger.info("CIBA Simulator initiated request: %s (binding: %s)", auth_req_id, binding_msg)
            return CIBARequest(
                auth_req_id=auth_req_id,
                expires_in=300,
                interval=self.DEFAULT_POLL_INTERVAL_SEC,
                binding_message=binding_msg,
                target_url=target_url,
            )

        # Real Auth0 Backchannel Authentication endpoint
        bc_url = f"https://{self.domain}/bc-authorize"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "audience": self.audience,
            "scope": "openid profile slothform:vault:read slothform:submit",
            "login_hint": self.login_hint,
            "binding_message": binding_msg,
            "authorization_details": rar_json,
        }

        client = await self.get_http_client()
        try:
            resp = await client.post(bc_url, data=payload, headers=headers)
        except Exception as e:
            raise CIBAError(f"Failed to connect to Auth0 backchannel endpoint ({bc_url}): {e}")

        if resp.status_code != 200:
            error_data = {}
            try:
                error_data = resp.json()
            except Exception:
                pass
            err_msg = error_data.get("error_description") or error_data.get("error") or resp.text
            raise CIBAError(f"Auth0 /bc-authorize failed [HTTP {resp.status_code}]: {err_msg}")

        data = resp.json()
        return CIBARequest(
            auth_req_id=data["auth_req_id"],
            expires_in=data.get("expires_in", 300),
            interval=data.get("interval", self.DEFAULT_POLL_INTERVAL_SEC),
            binding_message=binding_msg,
            target_url=target_url,
        )

    async def poll_token_once(self, auth_req_id: str) -> Dict[str, Any]:
        """Perform a single poll check against Auth0 /oauth/token or offline simulator.
        
        Returns a dict with either:
        - {"status": "approved", "access_token": "...", ...}
        - {"status": "pending"}
        - {"status": "slow_down"}
        - {"status": "access_denied", "error_description": "..."}
        - {"status": "expired_token", "error_description": "..."}
        """
        if self.offline_mode:
            sim = self._sim_requests.get(auth_req_id)
            if not sim:
                return {"status": "expired_token", "error_description": "Unknown or expired simulation ID"}

            sim["poll_count"] += 1

            # Handle simulated slow_down
            if sim["slow_down_cycles"] > 0:
                sim["slow_down_cycles"] -= 1
                return {"status": "slow_down", "error_description": "Simulation slow down"}

            # Handle pending cycles
            if sim["pending_cycles"] > 0:
                sim["pending_cycles"] -= 1
                return {"status": "pending", "error_description": "Simulation pending user action"}

            # Deliver final decision
            decision = sim.get("final_decision", "approved")
            if decision == "approved":
                sim["state"] = CIBAState.APPROVED
                return {
                    "status": "approved",
                    "access_token": sim["access_token"],
                    "token_type": "Bearer",
                    "expires_in": 86400,
                    "scope": "openid profile slothform:vault:read slothform:submit",
                }
            elif decision in ("access_denied", "deny", "rejected"):
                sim["state"] = CIBAState.REJECTED
                return {"status": "access_denied", "error_description": "The user denied the authorization request."}
            elif decision in ("expired_token", "expired", "timeout"):
                sim["state"] = CIBAState.EXPIRED
                return {"status": "expired_token", "error_description": "The auth_req_id has expired."}
            else:
                sim["state"] = CIBAState.FAILED
                return {"status": "failed", "error_description": f"Simulation unknown outcome: {decision}"}

        # Real Auth0 Token polling endpoint
        token_url = f"https://{self.domain}/oauth/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "grant_type": self.CIBA_GRANT_TYPE,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "auth_req_id": auth_req_id,
        }

        client = await self.get_http_client()
        try:
            resp = await client.post(token_url, data=payload, headers=headers)
        except Exception as e:
            logger.warning("Transient error connecting to Auth0 token endpoint: %s", e)
            return {"status": "pending", "transient_error": str(e)}

        if resp.status_code == 200:
            data = resp.json()
            data["status"] = "approved"
            return data

        # Auth0 error responses (HTTP 400 Bad Request)
        try:
            err_data = resp.json()
        except Exception:
            err_data = {"error": "unknown_error", "error_description": resp.text}

        err_code = err_data.get("error", "unknown_error")
        err_desc = err_data.get("error_description", "")

        if err_code == "authorization_pending":
            return {"status": "pending", "error_description": err_desc}
        elif err_code == "slow_down":
            return {"status": "slow_down", "error_description": err_desc}
        elif err_code == "access_denied":
            return {"status": "access_denied", "error_description": err_desc}
        elif err_code == "expired_token":
            return {"status": "expired_token", "error_description": err_desc}
        else:
            return {"status": "failed", "error": err_code, "error_description": err_desc}

    async def poll_consent(
        self,
        auth_req_id: str,
        timeout: int = DEFAULT_TIMEOUT_SEC,
        initial_interval: int = DEFAULT_POLL_INTERVAL_SEC,
    ) -> ConsentResult:
        """Poll Auth0 CIBA token endpoint until approved, rejected, or expired.
        
        Strict approval gatekeeper:
        - Raises RefusalToSubmitError on access_denied, expired_token, or timeout.
        - Guarantees execution cannot proceed without valid approved consent token.
        
        Interface Contract:
            Auth0CIBAClient.poll_consent(auth_req_id: str, timeout: int = 300) -> ConsentResult
        """
        start_time = time.time()
        current_interval = initial_interval

        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.error("CIBA Consent polling timed out after %d seconds.", timeout)
                raise ConsentTimeoutError(
                    f"CIBA consent polling timed out after {timeout} seconds without user approval. Execution refused."
                )

            res = await self.poll_token_once(auth_req_id)
            status = res.get("status")

            if status == "approved":
                logger.info("CIBA Consent APPROVED for request: %s", auth_req_id)
                return ConsentResult(
                    approved=True,
                    access_token=res.get("access_token"),
                    id_token=res.get("id_token"),
                    token_type=res.get("token_type", "Bearer"),
                    expires_in=res.get("expires_in"),
                    scope=res.get("scope"),
                )

            elif status == "access_denied":
                err_desc = res.get("error_description", "User rejected authorization request.")
                logger.warning("CIBA Consent REJECTED: %s", err_desc)
                raise RefusalToSubmitError(
                    f"Consent explicitly denied by user (access_denied): {err_desc}. Submission refused."
                )

            elif status == "expired_token":
                err_desc = res.get("error_description", "Auth request expired.")
                logger.warning("CIBA Consent EXPIRED: %s", err_desc)
                raise RefusalToSubmitError(
                    f"Consent request has expired (expired_token): {err_desc}. Submission refused."
                )

            elif status == "slow_down":
                current_interval += 5
                logger.info("Auth0 requested slow_down. Increased polling interval to %d seconds.", current_interval)

            elif status == "pending":
                logger.debug("CIBA Consent pending user action. Sleeping %ds...", current_interval)

            else:
                err_info = res.get("error_description") or res.get("error") or "Unknown error"
                raise CIBAError(f"CIBA polling failed with unexpected status: {err_info}")

            # Sleep between poll intervals, capped by remaining timeout
            remaining_time = max(0.0, timeout - (time.time() - start_time))
            sleep_duration = min(float(current_interval), remaining_time)
            if sleep_duration <= 0:
                raise ConsentTimeoutError("CIBA polling timed out while waiting for next interval.")
            
            await asyncio.sleep(sleep_duration)

    # Simulator manipulation helpers for testing
    def simulate_approval(self, auth_req_id: str) -> None:
        """Force simulated request to approve on next poll."""
        if auth_req_id in self._sim_requests:
            self._sim_requests[auth_req_id]["pending_cycles"] = 0
            self._sim_requests[auth_req_id]["slow_down_cycles"] = 0
            self._sim_requests[auth_req_id]["final_decision"] = "approved"

    def simulate_denial(self, auth_req_id: str) -> None:
        """Force simulated request to deny (access_denied) on next poll."""
        if auth_req_id in self._sim_requests:
            self._sim_requests[auth_req_id]["pending_cycles"] = 0
            self._sim_requests[auth_req_id]["slow_down_cycles"] = 0
            self._sim_requests[auth_req_id]["final_decision"] = "access_denied"

    def simulate_slow_down(self, auth_req_id: str, count: int = 1) -> None:
        """Configure simulated request to emit slow_down for specified number of cycles."""
        if auth_req_id in self._sim_requests:
            self._sim_requests[auth_req_id]["slow_down_cycles"] = count

    def simulate_expiration(self, auth_req_id: str) -> None:
        """Force simulated request to expire on next poll."""
        if auth_req_id in self._sim_requests:
            self._sim_requests[auth_req_id]["pending_cycles"] = 0
            self._sim_requests[auth_req_id]["slow_down_cycles"] = 0
            self._sim_requests[auth_req_id]["final_decision"] = "expired_token"
