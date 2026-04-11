"""
redis_dialog_manager.py — Redis-backed Dialog & Session State
==========================================================
Replaces in-process DialogManager + file-based session persistence
with Redis-backed distributed session state.

Key properties stored in Redis:
  dialog:{session_id}       → Hash (conversation state, TTL 1h)
  dialog:{session_id}:turns  → List (turn history, capped at 50)
  celery:result:{task_id}   → String (JSON task result, TTL 10min) [Celery default]
  celery:meta:{task_id}      → Hash (task metadata: query, role, status)
  preferences:{role}         → Hash (per-role output preferences)
  rate_limit:{user_id}      → String + TTL (token bucket rate limit)

Benefits over file-based:
  - Works across multiple FastAPI workers (horizontal scale)
  - TTL-based expiry (no orphaned session files)
  - Atomic operations (no file locking)
  - Sub-ms read latency vs disk I/O
  - Distributed Celery result backend (already Redis-backed)

Backwards-compatible API:
  Replace: DialogManager()
  With:    RedisDialogManager(redis_url="redis://redis:6379/0")
  Or:      DialogManagerRedisCompat() — drops into existing orchestrator unchanged.
"""

from __future__ import annotations

import json
import time
import uuid
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import asdict

import redis

from app.core.dialog_manager import (
    ClarificationType,
    Clarification,
    ConversationTurn,
    ConversationState,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_state(state: ConversationState) -> Dict[str, str]:
    """Serialize ConversationState to a Redis-friendly dict."""
    return {
        "session_id": state.session_id,
        "user_id": state.user_id,
        "role": state.role,
        "context": json.dumps(state.context),
        "last_domain": state.last_domain,
        "last_tables": json.dumps(state.last_tables),
        "last_entities": json.dumps(state.last_entities),
        "pending_clarification_type": (
            state.pending_clarification.clarification_type.value
            if state.pending_clarification else ""
        ),
        "pending_clarification_question": (
            state.pending_clarification.question
            if state.pending_clarification else ""
        ),
        "pending_clarification_options": (
            json.dumps(state.pending_clarification.options)
            if state.pending_clarification else ""
        ),
        "pending_clarification_context_key": (
            state.pending_clarification.context_key
            if state.pending_clarification else ""
        ),
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def _deserialize_state(data: Dict[str, Any]) -> ConversationState:
    """Deserialize a Redis hash back to ConversationState."""
    pending = None
    clar_type = data.get("pending_clarification_type", "")
    if clar_type:
        pending = Clarification(
            clarification_type=ClarificationType(clar_type),
            question=data.get("pending_clarification_question", ""),
            options=json.loads(data["pending_clarification_options"])
                if data.get("pending_clarification_options") else [],
            context_key=data.get("pending_clarification_context_key", ""),
        )

    return ConversationState(
        session_id=data["session_id"],
        user_id=data["user_id"],
        role=data["role"],
        context=json.loads(data["context"]) if data.get("context") else {},
        last_domain=data.get("last_domain", "auto"),
        last_tables=json.loads(data["last_tables"])
            if data.get("last_tables") else [],
        last_entities=json.loads(data["last_entities"])
            if data.get("last_entities") else {},
        pending_clarification=pending,
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Redis Dialog Manager
# ─────────────────────────────────────────────────────────────────────────────

class RedisDialogManager:
    """
    Drop-in replacement for DialogManager backed by Redis.

    Key design decisions:
      - TTL of 3600s (1 hour) on all session keys — auto-cleanup
      - ConversationState stored as Redis HASH (O(1) field access)
      - Turn history stored as Redis LIST (LPUSH + LTRIM for cap)
      - All operations are atomic via Redis pipeline
      - Fallback to original DialogManager if Redis unavailable
    """

    DIALOG_TTL      = 3600   # 1 hour session expiry
    TURN_LIST_MAX   = 50     # Keep last 50 turns
    RATE_LIMIT_TTL = 60      # 1 minute rate limit window
    RATE_LIMIT_MAX  = 30     # 30 requests per minute per user

    def __init__(
        self,
        redis_url: str = "redis://redis:6379/0",
        fallback_to_file: bool = None,
    ):
        self._redis_url = redis_url
        
        # In production/Docker, default to enforcing Redis (no silent file fallback)
        # Windows local dev can still fallback to file if REDIS_ENFORCE=false
        if fallback_to_file is None:
            self._fallback = os.environ.get("REDIS_ENFORCE", "true").lower() != "true"
        else:
            self._fallback = fallback_to_file
            
        self._r: Optional[redis.Redis] = None
        self._file_dm = None  # Lazy fallback

        self._connect_with_retry()

    # ── Redis connection ────────────────────────────────────────────────────────

    def _connect_with_retry(self, max_retries=3, delay=1.0):
        """Connect to Redis with exponential backoff."""
        for attempt in range(max_retries):
            try:
                self._r = redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                    retry_on_timeout=True,
                )
                self._r.ping()
                logger.info(f"[RedisDialogManager] Connected to {self._redis_url}")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"[RedisDialogManager] Connection failed ({e}). Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2
                else:
                    self._r = None
                    if self._fallback:
                        logger.warning(f"[RedisDialogManager] Redis unavailable after {max_retries} retries. Falling back to file-based.")
                    else:
                        logger.error(f"[RedisDialogManager] CRITICAL: Redis unavailable and fallback is disabled (REDIS_ENFORCE=true).")
        return False

    def _key(self, session_id: str, suffix: str = "") -> str:
        prefix = f"dialog:{session_id}"
        return f"{prefix}:{suffix}" if suffix else prefix

    def _ensure_connected(self) -> bool:
        if self._r is None:
            return False
        try:
            self._r.ping()
            return True
        except redis.ConnectionError:
            logger.warning("[RedisDialogManager] Lost connection, attempting reconnect...")
            return self._connect_with_retry(max_retries=2, delay=0.5)

    def _fallback_dm(self):
        """Lazily create file-based DialogManager as fallback, or raise error if enforced."""
        if not self._fallback:
            raise RuntimeError("Redis dialog state is required (REDIS_ENFORCE=true) but Redis is unreachable. Distributed session persistence is failing.")
            
        if self._file_dm is None:
            from app.core.dialog_manager import DialogManager
            self._file_dm = DialogManager()
        return self._file_dm

    # ── Session lifecycle ──────────────────────────────────────────────────────

    def start_session(
        self,
        user_id: str,
        role: str,
        session_id: Optional[str] = None,
    ) -> ConversationState:
        """
        Create a new dialog session in Redis.
        If Redis is down, falls back to file-based DialogManager.
        """
        if not self._ensure_connected():
            return self._fallback_dm().start_session(user_id, role, session_id)

        sid = session_id or f"{user_id}_{int(time.time())}"
        state = ConversationState(
            session_id=sid,
            user_id=user_id,
            role=role,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )

        pipe = self._r.pipeline()
        pipe.hset(self._key(sid), mapping=_serialize_state(state))
        pipe.expire(self._key(sid), self.DIALOG_TTL)
        # Initialize empty turn list
        pipe.delete(self._key(sid, "turns"))
        pipe.execute()

        logger.info(f"[RedisDialogManager] Session started: {sid}")
        return state

    def resume_session(self, session_id: str) -> Optional[ConversationState]:
        """Resume an existing session from Redis. Returns None if expired/not found."""
        if not self._ensure_connected():
            return self._fallback_dm().resume_session(session_id)

        data = self._r.hgetall(self._key(session_id))
        if not data:
            return None

        state = _deserialize_state(data)
        # Refresh TTL on access
        self._r.expire(self._key(session_id), self.DIALOG_TTL)
        return state

    def end_session(self, session_id: str) -> bool:
        """Delete session and turn history from Redis."""
        if not self._ensure_connected():
            return self._fallback_dm().end_session(session_id)

        pipe = self._r.pipeline()
        pipe.delete(self._key(session_id))
        pipe.delete(self._key(session_id, "turns"))
        pipe.delete(self._key(session_id, "rate"))
        pipe.execute()
        logger.info(f"[RedisDialogManager] Session ended: {session_id}")
        return True

    # ── Turn management ─────────────────────────────────────────────────────────

    def append_turn(self, session_id: str, turn: ConversationTurn) -> int:
        """
        Append a turn to the session's turn history.
        Returns the new turn number.
        """
        if not self._ensure_connected():
            dm = self._fallback_dm()
            dm._sessions[session_id] = self.resume_session(session_id)
            result = dm.handle_turn(
                dm._sessions[session_id],
                turn.user_query,
                orchestrator_fn=None,
            )
            return result["turn_number"]

        turn_json = json.dumps({
            "turn_number": turn.turn_number,
            "user_query": turn.user_query,
            "agent_response": turn.agent_response,
            "domain": turn.domain,
            "executed": turn.executed,
            "entities_extracted": turn.entities_extracted,
            "timestamp": turn.timestamp,
        })

        pipe = self._r.pipeline()
        pipe.lpush(self._key(session_id, "turns"), turn_json)
        pipe.ltrim(self._key(session_id, "turns"), 0, self.TURN_LIST_MAX - 1)
        pipe.execute()

        # Update session updated_at
        self._r.hset(self._key(session_id), "updated_at", _utc_now())
        self._r.expire(self._key(session_id), self.DIALOG_TTL)

        return turn.turn_number

    def get_turn_history(self, session_id: str) -> List[ConversationTurn]:
        """Return the session's turn history."""
        if not self._ensure_connected():
            dm = self._fallback_dm()
            state = dm.resume_session(session_id)
            return state.turns if state else []

        raw_turns = self._r.lrange(self._key(session_id, "turns"), 0, -1)
        turns = []
        for i, t in enumerate(reversed(raw_turns)):
            try:
                d = json.loads(t)
                turns.append(ConversationTurn(
                    turn_number=d["turn_number"],
                    user_query=d["user_query"],
                    agent_response=d.get("agent_response", ""),
                    domain=d.get("domain", "auto"),
                    executed=d.get("executed", False),
                    entities_extracted=d.get("entities_extracted", {}),
                    timestamp=d.get("timestamp", ""),
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        return turns

    # ── Context helpers ────────────────────────────────────────────────────────

    def update_context(self, session_id: str, context_updates: Dict[str, Any]) -> bool:
        """Atomically update session context fields."""
        if not self._ensure_connected():
            return False

        state = self.resume_session(session_id)
        if not state:
            return False

        state.context.update(context_updates)
        state.updated_at = _utc_now()

        pipe = self._r.pipeline()
        pipe.hset(self._key(session_id), "context", json.dumps(state.context))
        pipe.hset(self._key(session_id), "updated_at", _utc_now())
        pipe.expire(self._key(session_id), self.DIALOG_TTL)
        pipe.execute()
        return True

    def get_context(self, session_id: str) -> Dict[str, Any]:
        """Get the full session context."""
        state = self.resume_session(session_id)
        return state.context if state else {}

    # ── Rate limiting ───────────────────────────────────────────────────────────

    def check_rate_limit(self, user_id: str) -> tuple[bool, Dict[str, Any]]:
        """
        Token-bucket rate limiting. Returns (allowed, info_dict).

        info dict: {"allowed": bool, "remaining": int, "reset_in": int}
        """
        key = self._key(user_id, "rate")

        if not self._ensure_connected():
            # No Redis = no rate limiting (fail open for local dev)
            return True, {"allowed": True, "remaining": self.RATE_LIMIT_MAX, "reset_in": 0}

        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        results = pipe.execute()

        current_count = results[0]
        ttl = results[1]

        # Initialize key with TTL if this is the first request in the window
        if ttl == -1:
            self._r.expire(key, self.RATE_LIMIT_TTL)
            ttl = self.RATE_LIMIT_TTL
            current_count = 1

        allowed = current_count <= self.RATE_LIMIT_MAX
        remaining = max(0, self.RATE_LIMIT_MAX - current_count)

        return allowed, {
            "allowed": allowed,
            "remaining": remaining,
            "reset_in": ttl if ttl > 0 else self.RATE_LIMIT_TTL,
            "limit": self.RATE_LIMIT_MAX,
        }

    # ── User preferences (Redis hash per role) ────────────────────────────────

    def set_preference(
        self,
        role: str,
        output_format: str = "table",
        max_rows: int = 100,
        include_sql: bool = True,
        language: str = "en",
    ) -> bool:
        """Set per-role output preferences in Redis."""
        if not self._ensure_connected():
            return False

        key = f"preferences:{role}"
        self._r.hset(key, mapping={
            "output_format": output_format,
            "max_rows": str(max_rows),
            "include_sql": str(include_sql),
            "language": language,
            "updated_at": _utc_now(),
        })
        return True

    def get_preference(self, role: str) -> Dict[str, Any]:
        """Get preferences for a role."""
        if not self._ensure_connected():
            # Fallback to file-based
            from app.core.memory_layer import sap_memory
            return sap_memory.get_user_preference(role)

        key = f"preferences:{role}"
        data = self._r.hgetall(key)
        defaults = {"output_format": "table", "max_rows": 100, "include_sql": True, "language": "en"}
        if not data:
            return defaults
        return {
            "output_format": data.get("output_format", "table"),
            "max_rows": int(data.get("max_rows", 100)),
            "include_sql": data.get("include_sql", "True") == "True",
            "language": data.get("language", "en"),
        }

    # ── Celery task metadata (auxiliary, Celery owns result) ───────────────────

    def set_task_meta(
        self,
        task_id: str,
        query: str,
        user_id: str,
        role: str,
        domain: str = "auto",
    ) -> bool:
        """Store auxiliary task metadata (query, role, timestamps) alongside Celery result."""
        if not self._ensure_connected():
            return False

        key = f"celery:meta:{task_id}"
        self._r.hset(key, mapping={
            "query": query,
            "user_id": user_id,
            "role": role,
            "domain": domain,
            "submitted_at": _utc_now(),
            "status": "PENDING",
        })
        self._r.expire(key, 600)  # 10 min TTL matching Celery result expiry
        return True

    def update_task_status(self, task_id: str, status: str, result: Optional[Dict] = None) -> bool:
        """Update task status in Redis (called by Celery worker on completion)."""
        if not self._ensure_connected():
            return False

        key = f"celery:meta:{task_id}"
        updates = {
            "status": status,
            "completed_at": _utc_now(),
        }
        if result:
            # Store truncated result for quick polling (full result is in Celery backend)
            answer = result.get("answer", "")[:200]
            tables = ",".join(result.get("tables_used", [])[:5])
            updates["answer_preview"] = answer
            updates["tables_used"] = tables
            updates["execution_time_ms"] = str(result.get("execution_time_ms", 0))

        self._r.hset(key, mapping=updates)
        return True

    def get_task_meta(self, task_id: str) -> Optional[Dict[str, str]]:
        """Get task metadata (lightweight, does not fetch Celery result)."""
        if not self._ensure_connected():
            return None
        return self._r.hgetall(f"celery:meta:{task_id}")

    # ── Stats / health ────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return Redis-backed session stats."""
        if not self._ensure_connected():
            return {"backend": "file", "connected": False}

        info = self._r.info("memory")
        dialog_keys = len(self._r.keys("dialog:*"))
        pref_keys = len(self._r.keys("preferences:*"))
        return {
            "backend": "redis",
            "connected": True,
            "dialog_sessions": dialog_keys,
            "role_preferences": pref_keys,
            "memory_used_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
            "peak_memory_mb": round(info.get("used_memory_peak", 0) / 1024 / 1024, 2),
            "total_connections": info.get("total_connections", 0),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatibility shim — drops into existing orchestrator unchanged
# ─────────────────────────────────────────────────────────────────────────────

def use_redis_dialog_manager(
    redis_url: str = "redis://redis:6379/0",
) -> RedisDialogManager:
    """
    Call at startup to replace file-based DialogManager with Redis-backed.

    Usage (in app/main.py startup):
        from app.core.redis_dialog_manager import use_redis_dialog_manager
        redis_dm = use_redis_dialog_manager("redis://redis:6379/0")
    """
    # Monkey-patch the orchestrator's DialogManager import
    import app.agents.orchestrator as orch_mod
    from app.core.dialog_manager import DialogManager

    # Store original for fallback
    orch_mod._dialog_manager_file = DialogManager
    orch_mod._dialog_manager_redis = RedisDialogManager(redis_url=redis_url)
    orch_mod._dialog_manager = orch_mod._dialog_manager_redis

    logger.info("[RedisDialogManager] File-based DialogManager replaced with Redis-backed.")
    return orch_mod._dialog_manager_redis


def get_dialog_manager(redis_url: str = None) -> RedisDialogManager:
    """Get the global Redis-backed DialogManager singleton.

    Host resolution (Windows vs Docker):
      Windows/Mac: REDIS_HOST=localhost  (set by main.py on startup)
      Docker/k8s:  REDIS_HOST=redis      (Docker service name)

    Override via REDIS_URL env var for full URL control.
    """
    # Use REDIS_URL (full URL) or fall back to REDIS_HOST + default port/path
    url = os.environ.get("REDIS_URL") or (
        f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:{os.environ.get('REDIS_PORT', '6379')}/0"
    )
    if not hasattr(get_dialog_manager, "_instance"):
        get_dialog_manager._instance = RedisDialogManager(redis_url=url)
    return get_dialog_manager._instance
