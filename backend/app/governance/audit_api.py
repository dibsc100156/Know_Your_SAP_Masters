"""
audit_api.py — LeanIX Audit Trail API Endpoints
============================================
Exposes the LeanIX audit trail for:
  - DPO / Compliance officers: full query audit
  - IT Auditors: role-based access reports
  - Security: anomaly detection alerts
  - LeanIX: bidirectional sync of query metadata

Base URL: /api/v1/governance
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.governance.leanix_governance import LeanIXGovernanceService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/governance", tags=["Governance"])

# Singleton governance service
_gov_service: Optional[LeanIXGovernanceService] = None


def get_governance() -> LeanIXGovernanceService:
    global _gov_service
    if _gov_service is None:
        _gov_service = LeanIXGovernanceService()
    return _gov_service


# ── Models ────────────────────────────────────────────────────────────────

class AuditQueryRequest(BaseModel):
    userId: Optional[str] = Field(None, description="Filter by user ID")
    roleId: Optional[str] = Field(None, description="Filter by role ID")
    sinceMinutes: int = Field(default=60, ge=1, le=10080,
                              description="Look back window in minutes (max 1 week)")
    authDecision: Optional[str] = Field(None, description="Filter by auth decision")
    complianceStatus: Optional[str] = Field(None, description="Filter by compliance status")
    limit: int = Field(default=100, ge=1, le=1000,
                        description="Maximum number of entries to return")


class AuditEntryResponse(BaseModel):
    auditId: str
    timestamp: str
    userId: str
    roleId: str
    query: str
    queryHash: str
    tablesAccessed: List[str]
    authDecision: str
    complianceStatus: str
    leanixApplications: List[str]
    executionTimeMs: int
    resultRowCount: int
    maskedFields: List[str]


class AuditReportResponse(BaseModel):
    totalQueries: int
    deniedQueries: int
    flaggedQueries: int
    complianceViolations: int
    topUsers: List[dict]
    topRoles: List[dict]
    topTables: List[dict]
    riskDistribution: dict
    entries: List[AuditEntryResponse]


class ComplianceSummaryResponse(BaseModel):
    period: str
    totalQueries: int
    gdprQueries: int
    personalDataQueries: int
    restrictedTableQueries: int
    maskedQueries: int
    deniedQueries: int
    byRole: dict
    byUser: dict


# ── Endpoints ──────────────────────────────────────────────────────────

@router.get(
    "/audit",
    response_model=AuditReportResponse,
    summary="Query audit trail",
    description="Retrieve the LeanIX audit trail with optional filters.",
)
async def get_audit_log(
    userId: Optional[str] = None,
    roleId: Optional[str] = None,
    sinceMinutes: int = Query(default=60, ge=1, le=10080),
    authDecision: Optional[str] = None,
    complianceStatus: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    """
    Query the LeanIX audit trail.

    DPO use cases:
      - All queries touching GDPR-relevant tables in the last 24h
      - All queries by a specific employee
      - All denied queries

    Security use cases:
      - Anomalous access patterns
      - After-hours query activity
    """
    gov = get_governance()
    since = datetime.now(timezone.utc) - timedelta(minutes=sinceMinutes)

    entries = gov.get_audit_log(
        user_id=userId,
        role_id=roleId,
        since=since,
        limit=limit,
    )

    # Apply in-memory filters
    if authDecision:
        entries = [e for e in entries if e["authDecision"] == authDecision]
    if complianceStatus:
        entries = [e for e in entries if e["complianceStatus"] == complianceStatus]

    # Compute summary stats
    total = len(entries)
    denied = sum(1 for e in entries if e["authDecision"] == "deny")
    flagged = sum(1 for e in entries if e["authDecision"] == "flag")
    violations = sum(
        1 for e in entries
        if e["complianceStatus"] in ("block", "mask_and_log")
    )

    # Top users
    from collections import Counter
    user_counts = Counter(e["userId"] for e in entries)
    top_users = [{"userId": u, "count": c} for u, c in user_counts.most_common(5)]

    role_counts = Counter(e["roleId"] for e in entries)
    top_roles = [{"roleId": r, "count": c} for r, c in role_counts.most_common(5)]

    table_counter = Counter(t for e in entries for t in e["tablesAccessed"])
    top_tables = [{"table": t, "count": c} for t, c in table_counter.most_common(10)]

    # Risk distribution
    risk_dist = {
        "critical": sum(1 for e in entries if e.get("itRiskLevel") == "CRITICAL"),
        "high": sum(1 for e in entries if e.get("itRiskLevel") == "HIGH"),
        "medium": sum(1 for e in entries if e.get("itRiskLevel") == "MEDIUM"),
        "low": sum(1 for e in entries if e.get("itRiskLevel") == "LOW"),
    }

    return AuditReportResponse(
        totalQueries=total,
        deniedQueries=denied,
        flaggedQueries=flagged,
        complianceViolations=violations,
        topUsers=top_users,
        topRoles=top_roles,
        topTables=top_tables,
        riskDistribution=risk_dist,
        entries=[
            AuditEntryResponse(**{k: v for k, v in e.items()
                                 if k in AuditEntryResponse.model_fields})
            for e in entries
        ],
    )


@router.get(
    "/audit/{audit_id}",
    response_model=AuditEntryResponse,
    summary="Get single audit entry",
    description="Retrieve a specific audit entry by ID.",
)
async def get_audit_entry(audit_id: str):
    """Get a specific audit entry by its LeanIX audit ID."""
    gov = get_governance()
    entries = gov.get_audit_log(limit=10000)
    for e in entries:
        if e["auditId"] == audit_id:
            return AuditEntryResponse(**{k: v for k, v in e.items()
                                         if k in AuditEntryResponse.model_fields})
    raise HTTPException(status_code=404, detail=f"Audit entry {audit_id} not found")


@router.get(
    "/compliance/summary",
    response_model=ComplianceSummaryResponse,
    summary="GDPR/Compliance summary",
    description="Compliance report for DPO and privacy officers.",
)
async def get_compliance_summary(
    sinceMinutes: int = Query(default=1440, ge=60, le=43200),
):
    """
    Generate a compliance summary report for GDPR/SOX reporting.

    Includes:
      - GDPR-relevant query counts
      - Personal data access statistics
      - Restricted table access by role
      - Masked query counts
    """
    gov = get_governance()
    since = datetime.now(timezone.utc) - timedelta(minutes=sinceMinutes)
    entries = gov.get_audit_log(since=since, limit=10000)

    gdpr_queries = sum(
        1 for e in entries
        if any(
            flag in e.get("complianceStatus", "")
            for flag in ["gdpr", "personal", "mask"]
        )
    )
    personal_data = sum(
        1 for e in entries
        if e.get("personalDataFound") or
           e.get("complianceStatus") == "mask_and_log"
    )
    restricted = sum(
        1 for e in entries
        if e.get("authDecision") == "deny"
    )
    masked = sum(
        1 for e in entries
        if e.get("complianceStatus") == "mask_and_log"
    )

    from collections import Counter
    by_role = {
        r: {
            "total": c,
            "gdpr": sum(1 for e in entries if e["roleId"] == r and
                       e.get("complianceStatus") in ["gdpr", "personal"]),
        }
        for r, c in Counter(e["roleId"] for e in entries).most_common(10)
    }
    by_user = {
        u: {"total": c, "denied": sum(1 for e in entries if e["userId"] == u and e["authDecision"] == "deny")}
        for u, c in Counter(e["userId"] for e in entries).most_common(10)
    }

    return ComplianceSummaryResponse(
        period=f"last {sinceMinutes} minutes",
        totalQueries=len(entries),
        gdprQueries=gdpr_queries,
        personalDataQueries=personal_data,
        restrictedTableQueries=restricted,
        maskedQueries=masked,
        deniedQueries=restricted,
        byRole=by_role,
        byUser=by_user,
    )


@router.get(
    "/governance/active-sessions",
    summary="Active LeanIX-governed sessions",
    description="Show active sessions with LeanIX governance metadata.",
)
async def get_active_sessions():
    """
    List all active sessions with their LeanIX governance status.
    Useful for SOC2 reporting and access reviews.
    """
    from app.core.redis_dialog_manager import get_dialog_manager
    dm = get_dialog_manager()
    stats = dm.stats()
    return {
        "activeDialogSessions": stats.get("dialog_sessions", 0),
        "governanceMode": "active" if not dm._fallback else "degraded",
        "leanixMode": "live" if not LeanIXGovernanceService.__init__.__self__._demo_mode else "demo",
        "auditRetention": "30 days",
    }
