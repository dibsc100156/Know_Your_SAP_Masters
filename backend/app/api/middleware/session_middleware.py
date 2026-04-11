"""
session_middleware.py — FastAPI Session & Rate Limiting Middleware
================================================================
Two layers:

1. SessionMiddleware — FastAPI middleware
   - Reads X-Session-ID header or sets a new session cookie
   - Attaches dialog state to request.state
   - Auto-creates Redis dialog session on first request
   - Validates session expiry

2. redis_session_dependency — FastAPI Depends()
   - Inject session-aware dialog state into any endpoint
   - Handles rate limiting
   - Returns (session_id, session_state, rate_info)

Usage in endpoints:
    @router.post("/chat/master-data")
    async def chat(request: ChatRequest, session=Depends(redis_session_dependency)):
        session_id, state, rate = session
        # state is a ConversationState or None
"""

from __future__ import annotations

import os
import uuid
import time
import logging
from typing import Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.core.redis_dialog_manager import RedisDialogManager, get_dialog_manager

logger = logging.getLogger(__name__)

# ── Environment ────────────────────────────────────────────────────────────────

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
SESSION_COOKIE_NAME = "sap_session_id"
SESSION_HEADER_NAME = "X-Session-ID"
MAX_AGE_SECONDS = 3600  # 1 hour — matches DialogManager TTL

# ── Rate limit defaults ───────────────────────────────────────────────────────

RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_MAX    = int(os.environ.get("RATE_LIMIT_MAX", "30"))    # req/min
RATE_LIMIT_WINDOW  = int(os.environ.get("RATE_LIMIT_WINDOW", "60")) # seconds


# ── Middleware ────────────────────────────────────────────────────────────────

class SessionMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that:

    1. Extracts or generates session_id (header or cookie)
    2. Resumes/creates dialog state in Redis
    3. Attaches to request.state for access in endpoints
    4. Sets session cookie on response
    5. Enforces rate limiting (returns 429 if exceeded)

    Does NOT:
      - Block websockets (pass through)
      - Touch GET requests for rate limiting (only POST /chat/*)
    """

    def __init__(self, app, redis_url: str = REDIS_URL):
        super().__init__(app)
        self.redis_url = redis_url

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip non-HTTP paths (e.g., WebSocket upgrades)
        if not hasattr(request, "scope"):
            return await call_next(request)

        session_id: Optional[str] = None
        dialog_state: Optional[dict] = None
        rate_info: Optional[dict] = None

        # ── 1. Extract or create session ID ───────────────────────────────────
        session_id = (
            request.headers.get(SESSION_HEADER_NAME)
            or request.cookies.get(SESSION_COOKIE_NAME)
        )

        if not session_id:
            session_id = str(uuid.uuid4())

        request.state.session_id = session_id

        # ── 2. Resume dialog state from Redis ─────────────────────────────────
        dm = get_dialog_manager(self.redis_url)
        try:
            state = dm.resume_session(session_id)
            if state:
                request.state.dialog_state = {
                    "session_id": state.session_id,
                    "user_id": state.user_id,
                    "role": state.role,
                    "context": state.context,
                    "last_domain": state.last_domain,
                    "last_tables": state.last_tables,
                    "pending_clarification": (
                        state.pending_clarification.clarification_type.value
                        if state.pending_clarification else None
                    ),
                }
            else:
                request.state.dialog_state = None
        except Exception as e:
            logger.warning(f"[SessionMiddleware] Redis error: {e}")
            request.state.dialog_state = None

        # ── 3. Rate limiting (chat endpoints only) ─────────────────────────────
        if RATE_LIMIT_ENABLED:
            user_id = request.headers.get("X-User-ID", session_id)
            dm = get_dialog_manager(self.redis_url)
            allowed, rate_info = dm.check_rate_limit(user_id)
            request.state.rate_info = rate_info

            if not allowed:
                # Return 429 Too Many Requests
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "limit": RATE_LIMIT_MAX,
                        "remaining": 0,
                        "reset_in": rate_info.get("reset_in", 60),
                        "retry_after": rate_info.get("reset_in", 60),
                    },
                    headers={
                        "Retry-After": str(rate_info.get("reset_in", 60)),
                        "X-RateLimit-Limit": str(RATE_LIMIT_MAX),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + rate_info.get("reset_in", 60)),
                    },
                )
        else:
            request.state.rate_info = {"allowed": True, "remaining": RATE_LIMIT_MAX, "reset_in": 0}

        # ── 4. Process request ─────────────────────────────────────────────────
        response: Response = await call_next(request)

        # ── 5. Set session cookie (if new or updated) ─────────────────────────
        if session_id != request.cookies.get(SESSION_COOKIE_NAME):
            response.set_cookie(
                key=SESSION_COOKIE_NAME,
                value=session_id,
                max_age=MAX_AGE_SECONDS,
                httponly=True,
                samesite="lax",
                secure=False,  # True in production with HTTPS
            )

        return response


# ── FastAPI Dependency ────────────────────────────────────────────────────────

def redis_session_dependency(
    request: Request,
) -> Tuple[str, Optional[dict], dict]:
    """
    FastAPI Depends() — inject dialog session + rate info into endpoints.

    Returns:
        (session_id, dialog_state, rate_info)

    Usage:
        @router.post("/chat/master-data")
        async def chat(request: ChatRequest, session=Depends(redis_session_dependency)):
            session_id, state, rate = session
    """
    session_id = getattr(request.state, "session_id", None)
    dialog_state = getattr(request.state, "dialog_state", None)
    rate_info = getattr(request.state, "rate_info", {"allowed": True, "remaining": RATE_LIMIT_MAX})
    return session_id, dialog_state, rate_info


# ── Health check ───────────────────────────────────────────────────────────────

def check_redis_health() -> dict:
    """Lightweight Redis health check for /health endpoint."""
    dm = get_dialog_manager(REDIS_URL)
    try:
        stats = dm.stats()
        return {"redis": "ok", **stats}
    except Exception as e:
        return {"redis": "error", "error": str(e)}
