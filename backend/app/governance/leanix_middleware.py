"""
leanix_middleware.py — LeanIX Governance Middleware for FastAPI
=======================================================
Injects LeanIX governance into the FastAPI request pipeline.

Pre-processing (before orchestrator):
  1. LeanIX pre-authorization check
  2. Compliance classification
  3. Query context enrichment

Post-processing (after response):
  4. LeanIX audit trail logging
  5. Response enrichment (LeanIX business context headers)

Usage:
  app.add_middleware(LeanIXGovernanceMiddleware)
"""

from __future__ import annotations

import os
import re
import logging
from typing import List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.governance.leanix_governance import (
    LeanIXGovernanceService,
    AuthDecision,
)

logger = logging.getLogger(__name__)

# Paths that bypass governance entirely
GOVERNANCE_EXEMPT_PATHS = {
    "/",
    "/docs",
    "/openapi.json",
    "/health",
    "/health/redis",
    "/api/v1/chat/tasks",
    "/api/v1/chat/health",
    "/ws",
    "/favicon.ico",
}

# Regex patterns for common SAP table names in natural language queries
_SAP_TABLE_PATTERNS = [
    r"\b(LFA1|LFB1|LFBK|EINA|EINE|EORD|EKKO|EKPO|EKKN|EKES)\b",
    r"\b(KNA1|KNB1|KNVV|KNVK|KNVI|KNVP)\b",
    r"\b(MARA|MARC|MARD|MBEW|MAKT|MVKE|MARC|MSSL)\b",
    r"\b(BKPF|BSEG|BSIK|BSAK|BSID|BSAD|BSAS)\b",
    r"\b(VBAK|VBAP|VBEP|VBFA|LIKP|LIPS|VBRK|VBRP)\b",
    r"\b(QALS|QAVE|QAMV|MAPL|PLMK|PLPO)\b",
    r"\b(PROJ|PRPS|AFVC|AFVV|COSP|COSS|CSKB|CSSL)\b",
    r"\b(ANLA|ANLC|ANEP|ANLB)\b",
    r"\b(BUT000|BUT020|BUT050)\b",
    r"\b(T001|T001W|T001L|T001K|T024|T024E)\b",
    r"\b(PA0001|PA0008|PCL1|PCL2)\b",
    r"\b(J_1I[A-Z0-9]+)\b",
    r"\b(/SAPSLL/[A-Z0-9]+)\b",
]


class LeanIXGovernanceMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware applying LeanIX governance to chat requests.

    Bypasses: health checks, WebSocket streams, task polling.
    """

    def __init__(
        self,
        app,
        governance_service: LeanIXGovernanceService = None,
        bypass: bool = False,
    ):
        super().__init__(app)
        self.gov = governance_service or LeanIXGovernanceService()
        self.bypass = bypass or os.environ.get("LEANIX_ENABLED", "true").lower() != "true"

    # ── Public dispatch ───────────────────────────────────────────────────────

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip exempt paths (no governance overhead)
        if request.url.path in GOVERNANCE_EXEMPT_PATHS:
            return await call_next(request)

        # Only govern chat endpoints
        if "/chat" not in request.url.path:
            return await call_next(request)

        # ── Parse request body ───────────────────────────────────────────────
        user_id = request.headers.get("X-User-ID", "anonymous")
        role_id = request.headers.get(
            "X-Role-ID",
            getattr(request.state, "role", "unknown"),
        )

        body = {}
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.json()
            except Exception:
                body = {}

        query = body.get("query", "")
        if not query:
            return await call_next(request)

        # ── Pre-flight: governance checks run in parallel ────────────────────
        tables_guessed = self._extract_tables(query)

        try:
            import asyncio
            auth_result, compliance_result, enriched = await asyncio.gather(
                self.gov.pre_authorize(user_id, role_id, query, tables_guessed),
                self.gov.check_compliance(query, tables_guessed),
                self.gov.enrich_context(query, tables_guessed),
            )
        except Exception as e:
            logger.warning(f"[LeanIXMiddleware] Governance check failed: {e}")
            return await call_next(request)   # fail open

        # ── Pre-flight: block denied queries immediately ────────────────────
        _decision = auth_result.get("decision", "allow")
        _is_denied = (
            isinstance(_decision, AuthDecision)
            and _decision in (AuthDecision.DENY, AuthDecision.BLOCK_LOG)
        ) or str(_decision).upper() in ("DENY", "BLOCK", "FALSE")

        if _is_denied:
            logger.warning(f"[LeanIX] BLOCKED: {user_id} ({role_id}): {auth_result.get('reason', '')}")
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Query not authorized",
                    "reason": auth_result.get("reason", "Denied by LeanIX policy"),
                    "auditId": auth_result.get("auditId", ""),
                    "decision": (
                        _decision.value
                        if isinstance(_decision, AuthDecision)
                        else str(_decision)
                    ),
                    "complianceStatus": compliance_result.get("status", "unknown"),
                },
                headers={
                    "X-Audit-Id": auth_result.get("auditId", ""),
                    "X-Governance-Decision": (
                        _decision.value
                        if isinstance(_decision, AuthDecision)
                        else str(_decision)
                    ),
                    "X-Compliance-Status": compliance_result.get("status", "unknown"),
                },
            )

        # ── Attach governance data to request state for downstream use ────────
        request.state.leanix_auth = auth_result
        request.state.leanix_compliance = compliance_result
        request.state.leanix_context = enriched
        request.state.leanix_tables = tables_guessed

        # ── Process request ─────────────────────────────────────────────────
        response = await call_next(request)

        # ── Post-flight: audit log ─────────────────────────────────────────
        # Use actual tables from request.state if the endpoint wrote them there.
        # Do NOT call response.json() — it breaks streaming responses and can
        # consume the response body stream.
        actual_tables = getattr(request.state, "orchestrator_tables_used", None) or tables_guessed

        try:
            self.gov.log_query(
                query=query,
                auth_result=auth_result,
                compliance_result=compliance_result,
                result_summary={
                    "tables_accessed": actual_tables,
                    "row_count": getattr(request.state, "orchestrator_row_count", 0),
                    "execution_time_ms": getattr(request.state, "orchestrator_exec_ms", 0),
                },
                user_id=user_id,
                role_id=role_id,
            )
        except Exception as e:
            logger.error(f"[LeanIXMiddleware] Audit log failed: {e}")

        # ── Inject LeanIX headers into JSON responses ─────────────────────
        if isinstance(response, JSONResponse):
            response.headers["X-Audit-Id"] = auth_result.get("auditId", "")
            response.headers["X-Governance-Decision"] = (
                _decision.value
                if isinstance(_decision, AuthDecision)
                else str(_decision)
            )
            response.headers["X-Compliance-Status"] = compliance_result.get("status", "unknown")
            risk = enriched.get("itRiskLevel", "UNKNOWN") if enriched else "UNKNOWN"
            response.headers["X-IT-Risk-Level"] = risk
            if risk == "CRITICAL":
                logger.warning(
                    f"[LeanIXMiddleware] CRITICAL risk query: "
                    f"user={user_id}, apps={enriched.get('leanixApplications', [])}"
                )

        return response

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _extract_tables(self, query: str) -> List[str]:
        """Extract SAP table names mentioned in a natural language query."""
        found = set()
        q = query.upper()
        for pattern in _SAP_TABLE_PATTERNS:
            found.update(re.findall(pattern, q))
        return list(found)
