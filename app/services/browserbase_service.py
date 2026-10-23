"""Browserbase cloud browser session lifecycle and management service."""

import logging
import os
import uuid
from typing import Any, Dict, Optional

from browserbase import Browserbase
from browserbase.types.session_create_params import BrowserSettings
from app.config import get_settings
from app.models.browser_schema import BrowserbaseSession

logger = logging.getLogger(__name__)


class BrowserbaseService:
    """Manages remote Browserbase cloud browser sessions, proxies, debug inspection, and replay URLs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        client: Optional[Any] = None,
        offline: Optional[bool] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or os.getenv("BROWSERBASE_API_KEY") or settings.BROWSERBASE_API_KEY
        self.project_id = project_id or os.getenv("BROWSERBASE_PROJECT_ID") or settings.BROWSERBASE_PROJECT_ID

        # Determine offline/mock mode
        if offline is not None:
            self.offline = offline
        else:
            self.offline = bool(
                not self.api_key
                or self.api_key.startswith("bb_live_dummy")
                or self.api_key in ("test", "dummy", "offline")
            )

        self._active_sessions: Dict[str, Dict[str, Any]] = {}

        if client:
            self.client = client
            self.offline = False
        elif not self.offline:
            try:
                self.client = Browserbase(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize live Browserbase client ({e}). Falling back to offline mode.")
                self.client = None
                self.offline = True
        else:
            self.client = None

    def create_session(
        self,
        timeout: int = 1800,
        proxies: bool = True,
        solve_captchas: bool = True,
        keep_alive: bool = False,
    ) -> BrowserbaseSession:
        """
        Provisions a Browserbase cloud Chromium session.
        When credentials are live, calls the upstream SDK with residential proxies and CAPTCHA solving.
        When running in offline/mock mode, produces a deterministic simulated session.
        """
        if self.offline or not self.client:
            mock_id = f"sess_mock_{uuid.uuid4().hex[:12]}"
            connect_url = f"wss://connect.browserbase.com?apiKey=mock&sessionId={mock_id}"
            session = BrowserbaseSession(
                id=mock_id,
                connect_url=connect_url,
                status="RUNNING",
                proxy_bytes=0,
            )
            self._active_sessions[mock_id] = {
                "id": mock_id,
                "status": "RUNNING",
                "connect_url": connect_url,
                "keep_alive": keep_alive,
                "timeout": timeout,
                "proxies": proxies,
                "solve_captchas": solve_captchas,
            }
            logger.info(f"[Offline] Created simulated Browserbase session: {mock_id}")
            return session

        try:
            browser_settings = BrowserSettings(
                block_ads=True,
                solve_captchas=solve_captchas,
                record_session=True,
                log_session=True,
            )
            try:
                resp = self.client.sessions.create(
                    project_id=self.project_id,
                    proxies=proxies,
                    keep_alive=keep_alive,
                    browser_settings=browser_settings,
                    api_timeout=timeout,
                )
            except Exception as plan_err:
                err_text = str(plan_err).lower()
                if (proxies or keep_alive) and (
                    "402" in err_text
                    or "proxies" in err_text
                    or "free plan" in err_text
                    or "keep_alive" in err_text
                ):
                    logger.warning(
                        f"Browserbase plan does not include residential proxies/keep_alive ({plan_err}); "
                        "retrying live cloud session creation with proxies=False."
                    )
                    resp = self.client.sessions.create(
                        project_id=self.project_id,
                        proxies=False,
                        keep_alive=False,
                        browser_settings=browser_settings,
                        api_timeout=timeout,
                    )
                else:
                    raise
            session = BrowserbaseSession(
                id=resp.id,
                connect_url=resp.connect_url,
                status=resp.status,
                proxy_bytes=resp.proxy_bytes or 0,
            )
            self._active_sessions[resp.id] = {
                "id": resp.id,
                "status": resp.status,
                "connect_url": resp.connect_url,
            }
            logger.info(f"Provisioned live Browserbase session {resp.id}")
            return session
        except Exception as e:
            logger.error(f"Live Browserbase session creation failed: {e}")
            raise

    def get_debug_urls(self, session_id: str) -> Dict[str, str]:
        """
        Retrieves live debugging inspection URLs for embedding in web viewports.
        """
        if self.offline or not self.client:
            return {
                "debugger_fullscreen_url": f"https://browserbase.com/sessions/{session_id}/debug",
                "debugger_url": f"https://browserbase.com/sessions/{session_id}/devtools",
                "ws_url": f"wss://connect.browserbase.com/debug?sessionId={session_id}",
            }

        try:
            debug_info = self.client.sessions.debug(session_id)
            return {
                "debugger_fullscreen_url": getattr(debug_info, "debugger_fullscreen_url", f"https://browserbase.com/sessions/{session_id}/debug"),
                "debugger_url": getattr(debug_info, "debugger_url", f"https://browserbase.com/sessions/{session_id}/devtools"),
                "ws_url": getattr(debug_info, "ws_url", ""),
            }
        except Exception as e:
            logger.warning(f"Could not fetch debug URLs for {session_id}: {e}")
            return {
                "debugger_fullscreen_url": f"https://browserbase.com/sessions/{session_id}/debug",
                "debugger_url": f"https://browserbase.com/sessions/{session_id}/devtools",
            }

    def release_session(self, session_id: str) -> None:
        """
        Mandatory session teardown: issues REQUEST_RELEASE to stop cloud container billing
        and finalize recording.
        """
        if self.offline or not self.client:
            if session_id in self._active_sessions:
                self._active_sessions[session_id]["status"] = "REQUEST_RELEASE"
            logger.info(f"[Offline] Released simulated Browserbase session {session_id}")
            return

        try:
            self.client.sessions.update(session_id, status="REQUEST_RELEASE")
            if session_id in self._active_sessions:
                self._active_sessions[session_id]["status"] = "REQUEST_RELEASE"
            logger.info(f"Released Browserbase session {session_id}")
        except Exception as e:
            logger.error(f"Failed to release session {session_id}: {e}")
            raise

    def get_replay_url(self, session_id: str) -> str:
        """
        Returns the permanent playable Browserbase session replay URL.
        """
        return f"https://browserbase.com/sessions/{session_id}"
