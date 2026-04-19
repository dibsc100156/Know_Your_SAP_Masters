"""
CIBA Approval Store — Client Initiated Backchannel Authentication.

Phase 15: When the Security Sentinel issues a hard "block" verdict,
execution is NOT continued. Instead:
  1. An approval request is stored in Redis.
  2. The orchestrator returns status="ciba_pending" with a request_id.
  3. The user approves/denies via API endpoints.
  4. On approval, subsequent calls for the same query auto-pass.
  5. On deny, the query is permanently rejected for that session.
"""

import json
import time
import uuid
import hashlib
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

import redis

logger = logging.getLogger(__name__)


class CIBARequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class CIBAApprovalRequest:
    request_id: str          # UUID hex
    session_id: str
    user_id: str             # who owns the session
    role_id: str             # role under which query was blocked
    query: str               # original natural-language query
    generated_sql: str       # SQL that was blocked
    threat_type: str         # sentinel threat type
    threat_detail: str       # human-readable explanation
    severity: str            # HIGH | MEDIUM | LOW
    evidence: List[str]      # sentinel evidence list
    recommended_action: str   # original recommended_action
    tables_requested: List[str]
    status: CIBARequestStatus = CIBARequestStatus.PENDING
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0  # set on creation
    approved_at: float = 0.0
    denied_at: float = 0.0
    approver_id: str = ""
    denial_reason: str = ""
    approver_comments: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, CIBARequestStatus) else self.status
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CIBAApprovalRequest":
        d = dict(d)
        d["status"] = CIBARequestStatus(d.get("status", "pending"))
        return cls(**d)


class CIBAApprovalStore:
    """
    Redis-backed store for CIBA approval requests.
    
    Key layout:
      ciba:pending:{request_id}          → JSON approval request (until resolved)
      ciba:session:{session_id}         → SET of pending request_ids
      ciba:approved:{session_id}:{qhash} → "1" TTL=approval_ttl (auto-approve for repeated queries)
      ciba:denied:{session_id}:{qhash}   → "1" TTL=denial_ttl (hard reject)
    """

    # TTLs (seconds)
    DEFAULT_PENDING_TTL = 600       # 10 minutes
    DEFAULT_APPROVAL_TTL = 3600    # 1 hour
    DEFAULT_DENIAL_TTL = 1800      # 30 minutes

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        pending_ttl: int = DEFAULT_PENDING_TTL,
        approval_ttl: int = DEFAULT_APPROVAL_TTL,
        denial_ttl: int = DEFAULT_DENIAL_TTL,
    ):
        self._redis_url = redis_url
        self._pending_ttl = pending_ttl
        self._approval_ttl = approval_ttl
        self._denial_ttl = denial_ttl
        self._client: Optional[redis.Redis] = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            try:
                self._client = redis.from_url(self._redis_url, decode_responses=True)
                self._client.ping()
            except redis.ConnectionError:
                logger.warning("[CIBA] Redis not available — using in-memory fallback")
                self._client = None
        return self._client

    def _mk_pending_key(self, request_id: str) -> str:
        return f"ciba:pending:{request_id}"

    def _mk_session_key(self, session_id: str) -> str:
        return f"ciba:session:{session_id}"

    def _mk_approved_key(self, session_id: str, query_hash: str) -> str:
        return f"ciba:approved:{session_id}:{query_hash}"

    def _mk_denied_key(self, session_id: str, query_hash: str) -> str:
        return f"ciba:denied:{session_id}:{query_hash}"

    @staticmethod
    def _query_hash(query: str) -> str:
        return hashlib.sha256(query.lower().strip().encode()).hexdigest()[:32]

    # ── Create ─────────────────────────────────────────────────────────────────

    def create_approval_request(
        self,
        session_id: str,
        user_id: str,
        role_id: str,
        query: str,
        generated_sql: str,
        threat_type: str,
        threat_detail: str,
        severity: str,
        evidence: List[str],
        recommended_action: str,
        tables_requested: List[str],
        pending_ttl: Optional[int] = None,
    ) -> CIBAApprovalRequest:
        """
        Create a new CIBA pending approval request.
        Returns the created CIBAApprovalRequest with request_id.
        """
        request_id = uuid.uuid4().hex[:16]
        ttl = pending_ttl or self._pending_ttl
        expires_at = time.time() + ttl

        req = CIBAApprovalRequest(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            role_id=role_id,
            query=query,
            generated_sql=generated_sql,
            threat_type=threat_type,
            threat_detail=threat_detail,
            severity=severity,
            evidence=evidence,
            recommended_action=recommended_action,
            tables_requested=tables_requested,
            status=CIBARequestStatus.PENDING,
            created_at=time.time(),
            expires_at=expires_at,
        )

        if self.client:
            pipe = self.client.pipeline()
            pipe.set(self._mk_pending_key(request_id), json.dumps(req.to_dict()), ex=ttl)
            pipe.sadd(self._mk_session_key(session_id), request_id)
            pipe.execute()
            logger.info(f"[CIBA] Created pending request {request_id} for session {session_id}")
        else:
            # In-memory fallback — keep in _memory dict
            if not hasattr(self, "_memory"):
                self._memory: Dict[str, CIBAApprovalRequest] = {}
            if not hasattr(self, "_session_index"):
                self._session_index: Dict[str, set] = {}
            self._memory[request_id] = req
            self._session_index.setdefault(session_id, set()).add(request_id)
            logger.info(f"[CIBA-MEM] Created pending request {request_id} (in-memory fallback)")

        return req

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_pending_request(self, request_id: str) -> Optional[CIBAApprovalRequest]:
        """Get a specific pending approval request by ID."""
        if self.client:
            data = self.client.get(self._mk_pending_key(request_id))
            if data:
                return CIBAApprovalRequest.from_dict(json.loads(data))
            return None
        else:
            if hasattr(self, "_memory"):
                req = self._memory.get(request_id)
                if req and req.status == CIBARequestStatus.PENDING:
                    return req
            return None

    def get_pending_for_session(self, session_id: str) -> List[CIBAApprovalRequest]:
        """Get all pending approval requests for a given session."""
        if self.client:
            request_ids = self.client.smembers(self._mk_session_key(session_id))
            results = []
            for rid in request_ids:
                req = self.get_pending_request(rid)
                if req:
                    results.append(req)
            return sorted(results, key=lambda r: r.created_at, reverse=True)
        else:
            if hasattr(self, "_session_index"):
                ids = self._session_index.get(session_id, set())
                return [self._memory[r] for r in ids if r in self._memory and self._memory[r].status == CIBARequestStatus.PENDING]
            return []

    # ── Approve / Deny ─────────────────────────────────────────────────────────

    def approve(
        self,
        request_id: str,
        approver_id: str,
        comments: str = "",
    ) -> bool:
        """
        Approve a pending CIBA request.
        On success: marks request approved + stores auto-approve hash in Redis.
        """
        req = self.get_pending_request(request_id)
        if not req:
            logger.warning(f"[CIBA] Approve failed: request {request_id} not found or not pending")
            return False

        req.status = CIBARequestStatus.APPROVED
        req.approved_at = time.time()
        req.approver_id = approver_id
        req.approver_comments = comments

        if self.client:
            # Store approved hash (auto-approve same query in future)
            qhash = self._query_hash(req.query)
            pipe = self.client.pipeline()
            # Keep the request record but remove from pending set
            pipe.set(self._mk_pending_key(request_id), json.dumps(req.to_dict()), ex=self._approval_ttl)
            pipe.srem(self._mk_session_key(req.session_id), request_id)
            # Auto-approve key — same query from same session auto-passes for approval_ttl
            pipe.set(self._mk_approved_key(req.session_id, qhash), "1", ex=self._approval_ttl)
            pipe.execute()
            logger.info(f"[CIBA] Request {request_id} APPROVED by {approver_id}")
        else:
            if hasattr(self, "_memory"):
                self._memory[request_id] = req
                self._session_index.get(req.session_id, set()).discard(request_id)
            logger.info(f"[CIBA-MEM] Request {request_id} APPROVED by {approver_id} (in-memory)")

        return True

    def deny(
        self,
        request_id: str,
        denier_id: str,
        reason: str = "",
    ) -> bool:
        """
        Deny a pending CIBA request.
        On success: marks denied + stores denial hash (hard reject) in Redis.
        """
        req = self.get_pending_request(request_id)
        if not req:
            logger.warning(f"[CIBA] Deny failed: request {request_id} not found or not pending")
            return False

        req.status = CIBARequestStatus.DENIED
        req.denied_at = time.time()
        req.approver_id = denier_id
        req.denial_reason = reason

        if self.client:
            qhash = self._query_hash(req.query)
            pipe = self.client.pipeline()
            pipe.set(self._mk_pending_key(request_id), json.dumps(req.to_dict()), ex=self._denial_ttl)
            pipe.srem(self._mk_session_key(req.session_id), request_id)
            # Denial hash — same query from same session is hard-rejected for denial_ttl
            pipe.set(self._mk_denied_key(req.session_id, qhash), "1", ex=self._denial_ttl)
            pipe.execute()
            logger.info(f"[CIBA] Request {request_id} DENIED by {denier_id}: {reason}")
        else:
            if hasattr(self, "_memory"):
                self._memory[request_id] = req
                self._session_index.get(req.session_id, set()).discard(request_id)
            logger.info(f"[CIBA-MEM] Request {request_id} DENIED by {denier_id} (in-memory)")

        return True

    # ── Query auto-check ───────────────────────────────────────────────────────

    def is_query_approved(self, session_id: str, query: str) -> bool:
        """
        Check if a query from this session has been approved.
        Returns True if the query was previously approved and the TTL hasn't expired.
        """
        if not self.client:
            if hasattr(self, "_memory"):
                qhash = self._query_hash(query)
                for req in self._memory.values():
                    if req.session_id == session_id and self._query_hash(req.query) == qhash:
                        if req.status == CIBARequestStatus.APPROVED:
                            return True
            return False

        qhash = self._query_hash(query)
        return self.client.exists(self._mk_approved_key(session_id, qhash)) > 0

    def is_query_denied(self, session_id: str, query: str) -> bool:
        """
        Check if a query from this session has been denied.
        Returns True if denied (hard reject for denial_ttl window).
        """
        if not self.client:
            if hasattr(self, "_memory"):
                qhash = self._query_hash(query)
                for req in self._memory.values():
                    if req.session_id == session_id and self._query_hash(req.query) == qhash:
                        if req.status == CIBARequestStatus.DENIED:
                            return True
            return False

        qhash = self._query_hash(query)
        return self.client.exists(self._mk_denied_key(session_id, qhash)) > 0

    # ── Housekeeping ──────────────────────────────────────────────────────────

    def expire_old_requests(self) -> int:
        """Remove expired pending requests. Returns count of expired."""
        if not self.client:
            return 0
        expired = 0
        for key in self.client.scan_iter("ciba:pending:*"):
            data = self.client.get(key)
            if data is None:
                expired += 1
                continue
            try:
                req = CIBAApprovalRequest.from_dict(json.loads(data))
            except Exception:
                expired += 1
                continue
            if req.status == CIBARequestStatus.PENDING and time.time() > req.expires_at:
                req.status = CIBARequestStatus.EXPIRED
                self.client.set(key, json.dumps(req.to_dict()), ex=60)
                self.client.srem(self._mk_session_key(req.session_id), req.request_id)
                expired += 1
                logger.info(f"[CIBA] Request {req.request_id} expired")
        return expired

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return CIBA store statistics."""
        if not self.client:
            if hasattr(self, "_memory"):
                total = len(self._memory)
                pending = sum(1 for r in self._memory.values() if r.status == CIBARequestStatus.PENDING)
                approved = sum(1 for r in self._memory.values() if r.status == CIBARequestStatus.APPROVED)
                denied = sum(1 for r in self._memory.values() if r.status == CIBARequestStatus.DENIED)
                return {"total": total, "pending": pending, "approved": approved, "denied": denied, "backend": "memory"}
            return {"total": 0, "pending": 0, "backend": "memory"}

        total = len(list(self.client.scan_iter("ciba:pending:*")))
        approved_keys = len(list(self.client.scan_iter("ciba:approved:*")))
        denied_keys = len(list(self.client.scan_iter("ciba:denied:*")))
        return {
            "total_pending": total,
            "total_approved_auto": approved_keys,
            "total_denied_auto": denied_keys,
            "backend": "redis",
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_ciba_store: Optional[CIBAApprovalStore] = None

def get_ciba_store() -> CIBAApprovalStore:
    global _ciba_store
    if _ciba_store is None:
        import os
        redis_url = os.environ.get("CIBA_REDIS_URL", "redis://localhost:6379/0")
        _ciba_store = CIBAApprovalStore(redis_url=redis_url)
    return _ciba_store
