"""
governance.py — LeanIX Governance API Endpoints
==============================================
Access to LeanIX audit trail, governance decisions, and compliance status.

Requires LEANIX_API_TOKEN set for live mode. Works in demo mode without credentials.

Endpoints:
  GET  /governance/audit          — Query audit log with filters
  GET  /governance/audit/{id}     — Single audit entry by ID
  GET  /governance/classify/{table} — Data classification for a SAP table
  GET  /governance/status          — LeanIX connection + governance mode
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.governance.leanix_governance import LeanIXGovernanceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/governance", tags=["Governance"])

# ── Singleton service ───────────────────────────────────────────────────────────
_gov_service: Optional[LeanIXGovernanceService] = None


def _gov() -> LeanIXGovernanceService:
    global _gov_service
    if _gov_service is None:
        _gov_service = LeanIXGovernanceService()
    return _gov_service


# ── Response Models ─────────────────────────────────────────────────────────────

class GovernanceStatusResponse(BaseModel):
    mode: str               # "live" or "demo"
    demo_mode: bool
    leanix_url: Optional[str]
    redis_audit: bool
    audit_log_entries: int


class TableClassificationResponse(BaseModel):
    table: str
    gdprRelevant: bool
    personalData: bool
    personalDataCategory: str
    dataCriticality: str
    complianceFlags: list[str]
    maskingRequired: bool


class AuditEntryResponse(BaseModel):
    auditId: str
    timestamp: str
    userId: str
    roleId: str
    query: str
    tablesAccessed: list[str]
    authDecision: str
    complianceStatus: str
    queryHash: str
    executionTimeMs: int
    resultRowCount: int
    maskedFields: list[str]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/status",
    response_model=GovernanceStatusResponse,
    summary="LeanIX governance status",
)
async def governance_status():
    """Return current LeanIX governance service status."""
    gov = _gov()
    return GovernanceStatusResponse(
        mode="live" if not gov._demo_mode else "demo",
        demo_mode=gov._demo_mode,
        leanix_url=gov._client.base_url or None,
        redis_audit=gov._audit_redis is not None,
        audit_log_entries=len(gov._audit_log),
    )


@router.get(
    "/classify/{table}",
    response_model=TableClassificationResponse,
    summary="Classify a SAP table by data sensitivity",
)
async def classify_table(table: str):
    """
    Return GDPR/financial/HR data classification for any SAP table.

    Uses the DataClassificationEngine with LeanIX metadata when available.
    No credentials required for classification.
    """
    gov = _gov()
    classification = gov._classifier.classify(table.upper())

    return TableClassificationResponse(
        table=table.upper(),
        gdprRelevant=classification["gdprRelevant"],
        personalData=classification["personalData"],
        personalDataCategory=classification["personalDataCategory"],
        dataCriticality=classification["dataCriticality"],
        complianceFlags=classification["complianceFlags"],
        maskingRequired=classification["maskingRequired"],
    )


@router.get(
    "/audit",
    summary="Query LeanIX audit log",
)
async def get_audit_log(
    user_id: Optional[str] = Query(default=None, description="Filter by user ID"),
    role_id: Optional[str] = Query(default=None, description="Filter by SAP role"),
    since_hours: int = Query(default=24, ge=1, le=720, description="Hours to look back (1-720)"),
    limit: int = Query(default=100, ge=1, le=500, description="Max entries to return"),
):
    """
    Retrieve governance audit entries.

    Returns the most recent queries with their authorization decisions,
    compliance classifications, and masked fields.

    Useful for:
      - DPO monthly reviews (GDPR Article 30 records)
      - SOX compliance auditing
      - Security incident investigation
      - Agent behavior analytics
    """
    gov = _gov()

    since = None
    if since_hours:
        since = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    entries = gov.get_audit_log(
        user_id=user_id,
        role_id=role_id,
        since=since,
        limit=limit,
    )

    return {
        "count": len(entries),
        "filters": {
            "user_id": user_id,
            "role_id": role_id,
            "since_hours": since_hours,
        },
        "entries": [
            AuditEntryResponse(
                auditId=e["auditId"],
                timestamp=e["timestamp"],
                userId=e.get("userId", e.get("user_id", "")),
                roleId=e.get("roleId", e.get("role_id", "")),
                query=e["query"],
                tablesAccessed=e["tablesAccessed"],
                authDecision=e["authDecision"],
                complianceStatus=e["complianceStatus"],
                queryHash=e["queryHash"],
                executionTimeMs=e.get("executionTimeMs", 0),
                resultRowCount=e.get("resultRowCount", 0),
                maskedFields=e.get("maskedFields", []),
            )
            for e in entries
        ],
    }


@router.get(
    "/audit/{audit_id}",
    summary="Get single audit entry",
)
async def get_audit_entry(audit_id: str):
    """Get a single audit entry by LeanIX audit ID."""
    gov = _gov()
    entries = gov.get_audit_log(limit=500)

    for e in entries:
        if e["auditId"] == audit_id:
            return AuditEntryResponse(
                auditId=e["auditId"],
                timestamp=e["timestamp"],
                userId=e.get("userId", e.get("user_id", "")),
                roleId=e.get("roleId", e.get("role_id", "")),
                query=e["query"],
                tablesAccessed=e["tablesAccessed"],
                authDecision=e["authDecision"],
                complianceStatus=e["complianceStatus"],
                queryHash=e["queryHash"],
                executionTimeMs=e.get("executionTimeMs", 0),
                resultRowCount=e.get("resultRowCount", 0),
                maskedFields=e.get("maskedFields", []),
            )

    return {"error": "Audit entry not found", "auditId": audit_id}
