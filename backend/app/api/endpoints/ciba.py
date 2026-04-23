"""
CIBA Approval Endpoints — Phase 15.

Handles async approve/deny for queries blocked by Security Sentinel.

Base path: /api/v1/ciba
"""

import time
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel

from app.core.ciba_approval_store import get_ciba_store, CIBARequestStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ciba", tags=["CIBA Approval"])


# ── Request/Response Models ──────────────────────────────────────────────────

class ThreatDetail(BaseModel):
    threat_type: str
    threat_detail: str
    severity: str
    evidence: List[str]
    recommended_action: str


class CIBAApprovalRequestResponse(BaseModel):
    request_id: str
    session_id: str
    user_id: str
    role_id: str
    query: str
    generated_sql: str
    threat: ThreatDetail
    tables_requested: List[str]
    status: str
    created_at: float
    expires_at: float
    time_remaining_seconds: float
    edited_sql: Optional[str] = None
    conditional_constraints: Optional[str] = None
    feedback_instructions: Optional[str] = None

class CIBAApprovalPayload(BaseModel):
    approver_id: str
    comments: Optional[str] = ""
    edited_sql: Optional[str] = ""
    conditional_constraints: Optional[str] = ""

class CIBAApprovalResponse(BaseModel):
    request_id: str
    status: str
    message: str
    approved_at: float


class CIBADenialResponse(BaseModel):
    request_id: str
    status: str
    message: str
    denied_at: float


class CIBARevisePayload(BaseModel):
    reviewer_id: str
    feedback_instructions: str

class CIBAReviseResponse(BaseModel):
    request_id: str
    status: str
    message: str


class CIBAPendingListResponse(BaseModel):
    session_id: str
    pending: List[CIBAApprovalRequestResponse]
    stats: Dict[str, Any]


class CIBAAutoApproveResponse(BaseModel):
    session_id: str
    query_hash: str
    approved: bool
    reason: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_request_response(req) -> CIBAApprovalRequestResponse:
    return CIBAApprovalRequestResponse(
        request_id=req.request_id,
        session_id=req.session_id,
        user_id=req.user_id,
        role_id=req.role_id,
        query=req.query,
        generated_sql=req.generated_sql,
        threat=ThreatDetail(
            threat_type=req.threat_type,
            threat_detail=req.threat_detail,
            severity=req.severity,
            evidence=req.evidence,
            recommended_action=req.recommended_action,
        ),
        tables_requested=req.tables_requested,
        status=req.status.value,
        created_at=req.created_at,
        expires_at=req.expires_at,
        time_remaining_seconds=max(0.0, req.expires_at - time.time()),
        edited_sql=getattr(req, "edited_sql", None),
        conditional_constraints=getattr(req, "conditional_constraints", None),
        feedback_instructions=getattr(req, "feedback_instructions", None),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/pending", response_model=CIBAPendingListResponse)
def list_pending(
    session_id: str = Query(..., description="Session ID to list pending approvals for"),
    x_user_id: Optional[str] = Header(None, description="User ID for access control"),
):
    """
    List all pending CIBA approval requests for a session.
    Use this to populate the approval inbox UI.
    """
    store = get_ciba_store()
    pending_reqs = store.get_pending_for_session(session_id)
    
    # Filter by user_id if provided
    if x_user_id:
        pending_reqs = [r for r in pending_reqs if r.user_id == x_user_id]

    return CIBAPendingListResponse(
        session_id=session_id,
        pending=[_build_request_response(r) for r in pending_reqs],
        stats=store.get_stats(),
    )


@router.get("/pending/{request_id}", response_model=CIBAApprovalRequestResponse)
def get_pending(
    request_id: str,
    x_user_id: Optional[str] = Header(None, description="User ID for access control"),
):
    """
    Get a specific pending approval request.
    Includes time remaining before auto-expiry.
    """
    store = get_ciba_store()
    req = store.get_pending_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found or not pending")
    
    # Access control: user can only see their own requests
    if x_user_id and req.user_id != x_user_id:
        raise HTTPException(status_code=403, detail="Access denied to this approval request")

    return _build_request_response(req)


@router.post("/approve/{request_id}", response_model=CIBAApprovalResponse)
def approve_request(
    request_id: str,
    payload: CIBAApprovalPayload,
    x_user_id: Optional[str] = Header(None, description="User ID for access control"),
):
    """
    APPROVE a pending CIBA request.
    Can include edited_sql and conditional_constraints.
    """
    store = get_ciba_store()
    req = store.get_pending_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found or not pending")

    success = store.approve(
        request_id=request_id,
        approver_id=payload.approver_id,
        comments=payload.comments,
        edited_sql=payload.edited_sql,
        conditional_constraints=payload.conditional_constraints,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Approval failed")

    logger.info(f"[CIBA-API] Request {request_id} approved by {payload.approver_id}")

    return CIBAApprovalResponse(
        request_id=request_id,
        status="approved",
        message=f"Request approved by {payload.approver_id}. Query auto-approved for session {req.session_id}.",
        approved_at=time.time(),
    )


@router.post("/deny/{request_id}", response_model=CIBADenialResponse)
def deny_request(
    request_id: str,
    denier_id: str = Query(..., description="ID of the denier"),
    reason: str = Query("", description="Reason for denial"),
    x_user_id: Optional[str] = Header(None, description="User ID for access control"),
):
    """
    DENY a pending CIBA request.

    After denial:
      - The request is marked denied in Redis.
      - A query-deny hash is stored (same query from same session is hard-rejected
        for the next 30 minutes without needing another denial).
      - The blocked SQL will NOT be executed even if re-submitted.
    """
    store = get_ciba_store()
    req = store.get_pending_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found or not pending")

    success = store.deny(request_id, denier_id, reason)
    if not success:
        raise HTTPException(status_code=500, detail="Denial failed")

    logger.info(f"[CIBA-API] Request {request_id} denied by {denier_id}: {reason}")

    return CIBADenialResponse(
        request_id=request_id,
        status="denied",
        message=f"Request denied by {denier_id}. Query hard-rejected for session {req.session_id} for 30 minutes.",
        denied_at=time.time(),
    )


@router.post("/revise/{request_id}", response_model=CIBAReviseResponse)
def revise_request(
    request_id: str,
    payload: CIBARevisePayload,
    x_user_id: Optional[str] = Header(None, description="User ID for access control"),
):
    """
    REVISE a pending CIBA request.
    Kicks the request back to the orchestrator FormalRevisionLoop with instructions.
    """
    store = get_ciba_store()
    req = store.get_pending_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found or not pending")

    success = store.revise(
        request_id=request_id,
        reviewer_id=payload.reviewer_id,
        feedback_instructions=payload.feedback_instructions,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Revise failed")

    logger.info(f"[CIBA-API] Request {request_id} REVISE triggered by {payload.reviewer_id}")

    return CIBAReviseResponse(
        request_id=request_id,
        status="revise",
        message=f"Request kicked back to agent for revision by {payload.reviewer_id}.",
    )


@router.get("/check/{session_id}", response_model=CIBAAutoApproveResponse)
def check_query_approval(
    session_id: str,
    query: str = Query(..., description="The query string to check"),
):
    """
    Check if a query from a given session has been previously approved or denied.
    Used by the orchestrator BEFORE blocking to check auto-approve status.
    """
    store = get_ciba_store()
    from app.core.ciba_approval_store import CIBAApprovalStore
    qhash = CIBAApprovalStore._query_hash(query)

    if store.is_query_approved(session_id, query):
        return CIBAAutoApproveResponse(
            session_id=session_id,
            query_hash=qhash,
            approved=True,
            reason="Query was previously approved in this session.",
        )
    elif store.is_query_denied(session_id, query):
        return CIBAAutoApproveResponse(
            session_id=session_id,
            query_hash=qhash,
            approved=False,
            reason="Query was previously denied in this session.",
        )
    else:
        return CIBAAutoApproveResponse(
            session_id=session_id,
            query_hash=qhash,
            approved=False,
            reason="No prior approval record for this query in this session.",
        )


@router.post("/expire-old")
def expire_old_requests():
    """Trigger cleanup of expired pending requests. Returns count of expired."""
    store = get_ciba_store()
    expired = store.expire_old_requests()
    return {"expired": expired, "message": f"{expired} expired request(s) cleaned up."}


@router.get("/stats")
def ciba_stats():
    """Return CIBA store statistics."""
    store = get_ciba_store()
    return store.get_stats()
