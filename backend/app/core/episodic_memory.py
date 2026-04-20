"""
episodic_memory.py — Phase 24: Episodic Memory Store (Session Scratchpad)
=========================================================================
Redis-backed session memory for the KYSM Agentic RAG architecture.

Provides persistent, TTL-managed session scratchpad for orchestrator agents:
  - Per-session query history (sliding window)
  - Conversation context (last N exchanges)
  - Agent scratchpad (key-value intermediate state)
  - Query deduplication (near-identical within session)
  - Cross-turn context injection (upstream agents remember downstream results)

Redis keys (prefix: `kysm:episodic:`):
  session:{session_id}:queries     — List of query records (JSON)
  session:{session_id}:context     — Sliding window context (JSON list)
  session:{session_id}:scratchpad  — Dict scratchpad (Hash)
  session:{session_id}:meta         — Session metadata (Hash)
  dedup:{session_id}:{query_hash}  — Deduplication marker (TTL=10min)

Non-blocking: If Redis is unavailable, falls back to in-memory dict store.
All operations are fire-and-forget (failures never block the request path).

Usage:
    store = EpisodicMemoryStore()
    store.record_query(session_id="user123_s1", query="show vendors", result=result)
    context = store.get_context(session_id="user123_s1", max_turns=5)
    store.set_scratchpad(session_id="user123_s1", key="last_domain", value="vendor_master")
    dedup_key = store.check_dedup(session_id="user123_s1", query="show vendors")
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_SESSION_TTL_SECONDS = 3600 * 8        # 8 hours
DEFAULT_CONTEXT_WINDOW = 10                   # last 10 turns
DEFAULT_QUERY_HISTORY_LIMIT = 50             # last 50 queries per session
DEFAULT_DEDUP_TTL_SECONDS = 600               # 10-minute dedup window
DEFAULT_SCRATCHPAD_TTL_SECONDS = 3600 * 4     # 4 hours

REDIS_KEY_PREFIX = "kysm:episodic"


def _redis_url_from_env() -> str:
    import os
    return os.environ.get("KYSM_EPISODIC_REDIS_URL", DEFAULT_REDIS_URL)


# =============================================================================
# Query Record — single turn in session history
# =============================================================================

@dataclass
class QueryRecord:
    """One query turn in the session history."""
    turn_id: int              # Monotonically increasing turn number within session
    query: str               # The natural language query
    query_signature: str     # SHA256 of query text (for dedup + similarity)
    domain: str               # Resolved domain (or "auto")
    role_id: str              # Role used for this query
    tables_used: List[str]    # Tables accessed
    sql_generated: Optional[str] = None
    result_count: Optional[int] = None
    confidence: Optional[float] = None
    answer_excerpt: Optional[str] = None  # First 200 chars of answer
    agent_name: Optional[str] = None      # Domain agent used (or "orchestrator")
    phase_used: Optional[str] = None      # e.g. "fast_path", "cross_module", "swarm"
    duration_ms: Optional[int] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "query": self.query,
            "query_signature": self.query_signature,
            "domain": self.domain,
            "role_id": self.role_id,
            "tables_used": self.tables_used,
            "sql_generated": self.sql_generated,
            "result_count": self.result_count,
            "confidence": round(self.confidence, 3) if self.confidence else None,
            "answer_excerpt": self.answer_excerpt,
            "agent_name": self.agent_name,
            "phase_used": self.phase_used,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "QueryRecord":
        return cls(
            turn_id=d["turn_id"],
            query=d["query"],
            query_signature=d["query_signature"],
            domain=d["domain"],
            role_id=d["role_id"],
            tables_used=d.get("tables_used", []),
            sql_generated=d.get("sql_generated"),
            result_count=d.get("result_count"),
            confidence=d.get("confidence"),
            answer_excerpt=d.get("answer_excerpt"),
            agent_name=d.get("agent_name"),
            phase_used=d.get("phase_used"),
            duration_ms=d.get("duration_ms"),
            timestamp=d.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


# =============================================================================
# Conversation Context — sliding window of recent turns
# =============================================================================

@dataclass
class ConversationTurn:
    """One turn in the conversation context window."""
    role: str          # "user" | "assistant"
    content: str       # Query (user) or answer excerpt (assistant)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content, "timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, d: Dict) -> "ConversationTurn":
        return cls(role=d["role"], content=d["content"], timestamp=d.get("timestamp", ""))


@dataclass
class ConversationContext:
    """Sliding window of recent conversation turns."""
    turns: List[ConversationTurn] = field(default_factory=list)

    def add_user(self, content: str):
        self.turns.append(ConversationTurn(role="user", content=content))

    def add_assistant(self, content: str):
        self.turns.append(ConversationTurn(role="assistant", content=content))

    def get_prompt_snippet(self, max_turns: int = 6) -> str:
        """Get last N turns formatted as a prompt snippet for context injection."""
        recent = self.turns[-max_turns:]
        lines = []
        for turn in recent:
            prefix = "User: " if turn.role == "user" else "Assistant: "
            lines.append(prefix + turn.content[:300])
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {"turns": [t.to_dict() for t in self.turns]}

    @classmethod
    def from_dict(cls, d: Dict) -> "ConversationContext":
        turns = [ConversationTurn.from_dict(t) for t in d.get("turns", [])]
        return cls(turns=turns)


# =============================================================================
# Session Metadata
# =============================================================================

@dataclass
class SessionMeta:
    """Metadata for a session."""
    session_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_activity: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    turn_count: int = 0
    role_id: str = "AP_CLERK"
    user_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def touch(self):
        self.last_activity = datetime.now(timezone.utc).isoformat()
        self.turn_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "turn_count": self.turn_count,
            "role_id": self.role_id,
            "user_id": self.user_id,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SessionMeta":
        return cls(
            session_id=d["session_id"],
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
            last_activity=d.get("last_activity", datetime.now(timezone.utc).isoformat()),
            turn_count=d.get("turn_count", 0),
            role_id=d.get("role_id", "AP_CLERK"),
            user_id=d.get("user_id"),
            tags=d.get("tags", []),
        )


# =============================================================================
# Redis Backend
# =============================================================================

class RedisBackend:
    """
    Redis-backed storage for episodic memory.
    All operations are fire-and-forget (errors logged, never raised).
    """

    def __init__(self, redis_url: str = DEFAULT_REDIS_URL):
        self.redis_url = redis_url
        self._client = None
        self._lock = Lock()
        self._connect()

    def _connect(self):
        try:
            import redis as redis_lib
            self._client = redis_lib.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Test connection
            self._client.ping()
            logger.info(f"[EpisodicMemory] Redis connected: {self.redis_url}")
        except Exception as e:
            logger.warning(f"[EpisodicMemory] Redis unavailable: {e}. Using in-memory fallback.")
            self._client = None

    def _key(self, *parts: str) -> str:
        return ":".join([REDIS_KEY_PREFIX] + list(parts))

    # ── Query History ───────────────────────────────────────────────────────

    def push_query(self, session_id: str, record: QueryRecord, max_history: int = DEFAULT_QUERY_HISTORY_LIMIT) -> None:
        """Append a query record to the session's history list."""
        if not self._client:
            return
        try:
            key = self._key("session", session_id, "queries")
            pipe = self._client.pipeline()
            pipe.rpush(key, json.dumps(record.to_dict()))
            pipe.ltrim(key, -max_history, -1)
            pipe.expire(key, DEFAULT_SESSION_TTL_SECONDS)
            pipe.execute()
        except Exception as e:
            logger.debug(f"[EpisodicMemory] push_query failed: {e}")

    def get_queries(self, session_id: str, limit: int = DEFAULT_QUERY_HISTORY_LIMIT) -> List[QueryRecord]:
        """Get the last N query records for a session."""
        if not self._client:
            return []
        try:
            key = self._key("session", session_id, "queries")
            raw = self._client.lrange(key, -limit, -1)
            return [QueryRecord.from_dict(json.loads(r)) for r in raw]
        except Exception as e:
            logger.debug(f"[EpisodicMemory] get_queries failed: {e}")
            return []

    # ── Conversation Context ────────────────────────────────────────────────

    def push_context(self, session_id: str, turn: ConversationTurn, max_window: int = DEFAULT_CONTEXT_WINDOW) -> None:
        """Append a conversation turn to the context window."""
        if not self._client:
            return
        try:
            key = self._key("session", session_id, "context")
            pipe = self._client.pipeline()
            pipe.rpush(key, json.dumps(turn.to_dict()))
            pipe.ltrim(key, -max_window, -1)
            pipe.expire(key, DEFAULT_SESSION_TTL_SECONDS)
            pipe.execute()
        except Exception as e:
            logger.debug(f"[EpisodicMemory] push_context failed: {e}")

    def get_context(self, session_id: str, max_turns: int = DEFAULT_CONTEXT_WINDOW) -> ConversationContext:
        """Get the conversation context for a session."""
        if not self._client:
            return ConversationContext()
        try:
            key = self._key("session", session_id, "context")
            raw = self._client.lrange(key, -max_turns, -1)
            turns = [ConversationTurn.from_dict(json.loads(r)) for r in raw]
            return ConversationContext(turns=turns)
        except Exception as e:
            logger.debug(f"[EpisodicMemory] get_context failed: {e}")
            return ConversationContext()

    # ── Scratchpad ────────────────────────────────────────────────────────

    def set_scratchpad(self, session_id: str, key: str, value: Any, ttl: int = DEFAULT_SCRATCHPAD_TTL_SECONDS) -> None:
        """Set a scratchpad key-value pair."""
        if not self._client:
            return
        try:
            redis_key = self._key("session", session_id, "scratchpad")
            pipe = self._client.pipeline()
            pipe.hset(redis_key, key, json.dumps(value))
            pipe.expire(redis_key, ttl)
            pipe.execute()
        except Exception as e:
            logger.debug(f"[EpisodicMemory] set_scratchpad failed: {e}")

    def get_scratchpad(self, session_id: str, key: str) -> Optional[Any]:
        """Get a scratchpad value by key."""
        if not self._client:
            return None
        try:
            redis_key = self._key("session", session_id, "scratchpad")
            raw = self._client.hget(redis_key, key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.debug(f"[EpisodicMemory] get_scratchpad failed: {e}")
            return None

    def get_all_scratchpad(self, session_id: str) -> Dict[str, Any]:
        """Get all scratchpad key-values."""
        if not self._client:
            return {}
        try:
            redis_key = self._key("session", session_id, "scratchpad")
            raw = self._client.hgetall(redis_key)
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception as e:
            logger.debug(f"[EpisodicMemory] get_all_scratchpad failed: {e}")
            return {}

    def delete_scratchpad(self, session_id: str, key: str) -> None:
        """Delete a scratchpad key."""
        if not self._client:
            return
        try:
            redis_key = self._key("session", session_id, "scratchpad")
            self._client.hdel(redis_key, key)
        except Exception as e:
            logger.debug(f"[EpisodicMemory] delete_scratchpad failed: {e}")

    # ── Session Metadata ───────────────────────────────────────────────────

    def save_meta(self, meta: SessionMeta) -> None:
        """Save session metadata."""
        if not self._client:
            return
        try:
            key = self._key("session", session_id := meta.session_id, "meta")
            self._client.hset(key, mapping={k: json.dumps(v) for k, v in meta.to_dict().items()})
            self._client.expire(key, DEFAULT_SESSION_TTL_SECONDS)
        except Exception as e:
            logger.debug(f"[EpisodicMemory] save_meta failed: {e}")

    def get_meta(self, session_id: str) -> Optional[SessionMeta]:
        """Get session metadata."""
        if not self._client:
            return None
        try:
            key = self._key("session", session_id, "meta")
            raw = self._client.hgetall(key)
            if not raw:
                return None
            parsed = {k: json.loads(v) for k, v in raw.items()}
            return SessionMeta.from_dict(parsed)
        except Exception as e:
            logger.debug(f"[EpisodicMemory] get_meta failed: {e}")
            return None

    # ── Deduplication ─────────────────────────────────────────────────────

    def check_dedup(self, session_id: str, query: str, ttl: int = DEFAULT_DEDUP_TTL_SECONDS) -> Tuple[bool, Optional[str]]:
        """
        Check if a query is a near-duplicate of a recent query in this session.
        Returns (is_duplicate, query_signature).
        """
        if not self._client:
            return False, None
        sig = self._query_signature(query)
        try:
            key = self._key("dedup", session_id, sig)
            exists = self._client.exists(key)
            if not exists:
                self._client.setex(key, ttl, "1")
            return bool(exists), sig
        except Exception as e:
            logger.debug(f"[EpisodicMemory] check_dedup failed: {e}")
            return False, None

    # ── Session Lifecycle ─────────────────────────────────────────────────

    def delete_session(self, session_id: str) -> None:
        """Delete all data for a session."""
        if not self._client:
            return
        try:
            keys = [
                self._key("session", session_id, "queries"),
                self._key("session", session_id, "context"),
                self._key("session", session_id, "scratchpad"),
                self._key("session", session_id, "meta"),
            ]
            self._client.delete(*keys)
        except Exception as e:
            logger.debug(f"[EpisodicMemory] delete_session failed: {e}")

    def get_all_session_ids(self) -> List[str]:
        """Get all active session IDs (for admin/monitoring)."""
        if not self._client:
            return []
        try:
            pattern = self._key("session", "*", "meta")
            keys = self._client.keys(pattern)
            prefix_len = len(self._key("session", "", ""))
            return [k[prefix_len:-5] for k in keys]  # strip prefix and :meta
        except Exception as e:
            logger.debug(f"[EpisodicMemory] get_all_session_ids failed: {e}")
            return []

    @staticmethod
    def _query_signature(query: str) -> str:
        """Normalize and hash a query for deduplication."""
        normalized = " ".join(query.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# =============================================================================
# In-Memory Fallback Backend
# =============================================================================

class InMemoryBackend:
    """
    Fire-and-forget in-memory fallback when Redis is unavailable.
    All data is lost when the process exits.
    """

    def __init__(self):
        self._queries: Dict[str, List[QueryRecord]] = {}
        self._context: Dict[str, List[ConversationTurn]] = {}
        self._scratchpad: Dict[str, Dict[str, Any]] = {}
        self._meta: Dict[str, SessionMeta] = {}
        self._dedup: Dict[str, float] = {}   # sig -> expiry timestamp
        self._lock = Lock()

    def _cleanup_dedup(self):
        now = time.time()
        expired = [k for k, v in self._dedup.items() if v < now]
        for k in expired:
            del self._dedup[k]

    def push_query(self, session_id: str, record: QueryRecord, max_history: int = DEFAULT_QUERY_HISTORY_LIMIT) -> None:
        with self._lock:
            if session_id not in self._queries:
                self._queries[session_id] = []
            self._queries[session_id].append(record)
            self._queries[session_id] = self._queries[session_id][-max_history:]

    def get_queries(self, session_id: str, limit: int = DEFAULT_QUERY_HISTORY_LIMIT) -> List[QueryRecord]:
        with self._lock:
            return list(self._queries.get(session_id, [])[-limit:])

    def get_history(self, session_id: str, limit: int = DEFAULT_QUERY_HISTORY_LIMIT) -> List[QueryRecord]:
        """Alias for get_queries -- called by EpisodicMemoryStore.get_recent_context_for_prompt."""
        return self.get_queries(session_id, limit=limit)

    def push_context(self, session_id: str, turn: ConversationTurn, max_window: int = DEFAULT_CONTEXT_WINDOW) -> None:
        with self._lock:
            if session_id not in self._context:
                self._context[session_id] = []
            self._context[session_id].append(turn)
            self._context[session_id] = self._context[session_id][-max_window:]

    def get_context(self, session_id: str, max_turns: int = DEFAULT_CONTEXT_WINDOW) -> ConversationContext:
        with self._lock:
            turns = list(self._context.get(session_id, [])[-max_turns:])
            return ConversationContext(turns=turns)

    def set_scratchpad(self, session_id: str, key: str, value: Any, ttl: int = DEFAULT_SCRATCHPAD_TTL_SECONDS) -> None:
        with self._lock:
            if session_id not in self._scratchpad:
                self._scratchpad[session_id] = {}
            self._scratchpad[session_id][key] = value

    def get_scratchpad(self, session_id: str, key: str) -> Optional[Any]:
        with self._lock:
            return self._scratchpad.get(session_id, {}).get(key)

    def get_all_scratchpad(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._scratchpad.get(session_id, {}))

    def delete_scratchpad(self, session_id: str, key: str) -> None:
        with self._lock:
            if session_id in self._scratchpad:
                self._scratchpad[session_id].pop(key, None)

    def save_meta(self, meta: SessionMeta) -> None:
        with self._lock:
            self._meta[session_id := meta.session_id] = meta

    def get_meta(self, session_id: str) -> Optional[SessionMeta]:
        with self._lock:
            return self._meta.get(session_id)

    def check_dedup(self, session_id: str, query: str, ttl: int = DEFAULT_DEDUP_TTL_SECONDS) -> Tuple[bool, Optional[str]]:
        self._cleanup_dedup()
        sig = RedisBackend._query_signature(query)
        key = f"{session_id}:{sig}"
        with self._lock:
            if key in self._dedup:
                return True, sig
            self._dedup[key] = time.time() + ttl
            return False, sig

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._queries.pop(session_id, None)
            self._context.pop(session_id, None)
            self._scratchpad.pop(session_id, None)
            self._meta.pop(session_id, None)

    def get_all_session_ids(self) -> List[str]:
        with self._lock:
            return list(self._meta.keys())


# =============================================================================
# Episodic Memory Store — Main API
# =============================================================================

class EpisodicMemoryStore:
    """
    Redis-backed episodic memory store for KYSM orchestrator sessions.

    Provides:
      - Query history: What queries has this session run?
      - Context window: Recent conversation turns for context injection
      - Scratchpad: Agent scratchpad (key-value intermediate state)
      - Deduplication: Near-identical query detection within a session
      - Session metadata: Track session lifecycle, role, tags

    All operations are fire-and-forget:
      - Redis failures are logged and silently skipped
      - No blocking, no retries, never raise to caller
      - In-memory fallback used when Redis unavailable

    Args:
        redis_url: Redis connection URL (default: redis://localhost:6379/0)
        session_ttl: Default TTL for session data (seconds)
        context_window: Default number of turns in context window
        query_history_limit: Default max query history per session
        force_backend: Force "redis" or "memory" backend (default: auto)

    Usage:
        store = EpisodicMemoryStore()
        store.record_query(session_id="user123_s1", query="show vendors", ...)
        context = store.get_context(session_id="user123_s1", max_turns=5)
        store.set_scratchpad(session_id="user123_s1", key="last_domain", value="vendor_master")
        is_dup, sig = store.check_dedup(session_id="user123_s1", query="show vendors")
    """

    def __init__(
        self,
        redis_url: str = DEFAULT_REDIS_URL,
        session_ttl: int = DEFAULT_SESSION_TTL_SECONDS,
        context_window: int = DEFAULT_CONTEXT_WINDOW,
        query_history_limit: int = DEFAULT_QUERY_HISTORY_LIMIT,
        force_backend: Optional[str] = None,  # "redis" | "memory"
    ):
        self.redis_url = redis_url
        self.session_ttl = session_ttl
        self.context_window = context_window
        self.query_history_limit = query_history_limit

        # Initialize backend
        if force_backend == "memory":
            self._backend: Any = InMemoryBackend()
            self._backend_name = "memory"
            logger.info("[EpisodicMemory] Force-using in-memory backend")
        elif force_backend == "redis":
            self._backend = RedisBackend(redis_url)
            self._backend_name = "redis"
        else:
            # Auto: try Redis, fall back to memory
            redis_backend = RedisBackend(redis_url)
            if redis_backend._client is not None:
                self._backend = redis_backend
                self._backend_name = "redis"
            else:
                self._backend = InMemoryBackend()
                self._backend_name = "memory"

        logger.info(
            f"[EpisodicMemory] Initialized with {self._backend_name} backend "
            f"(ttl={session_ttl}s, ctx_window={context_window}, hist_limit={query_history_limit})"
        )

    # ── Public API ────────────────────────────────────────────────────────

    def record_query(
        self,
        session_id: str,
        query: str,
        domain: str = "auto",
        role_id: str = "AP_CLERK",
        tables_used: Optional[List[str]] = None,
        sql_generated: Optional[str] = None,
        result_count: Optional[int] = None,
        confidence: Optional[float] = None,
        answer: Optional[str] = None,
        agent_name: Optional[str] = None,
        phase_used: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> QueryRecord:
        """
        Record a query execution in session history.
        Also updates session metadata (turn count, last activity).

        Returns the created QueryRecord.
        """
        # Get existing meta for turn count
        meta = self._backend.get_meta(session_id)
        turn_id = (meta.turn_count + 1) if meta else 1

        sig = self._backend._query_signature(query) if hasattr(self._backend, '_query_signature') else RedisBackend._query_signature(query)

        record = QueryRecord(
            turn_id=turn_id,
            query=query,
            query_signature=sig,
            domain=domain,
            role_id=role_id,
            tables_used=tables_used or [],
            sql_generated=sql_generated,
            result_count=result_count,
            confidence=confidence,
            answer_excerpt=answer[:200] if answer else None,
            agent_name=agent_name,
            phase_used=phase_used,
            duration_ms=duration_ms,
        )

        # Push to query history
        self._backend.push_query(session_id, record, max_history=self.query_history_limit)

        # Update context window
        self._backend.push_context(
            session_id,
            ConversationTurn(role="user", content=query),
            max_window=self.context_window,
        )
        if answer:
            self._backend.push_context(
                session_id,
                ConversationTurn(role="assistant", content=answer[:300]),
                max_window=self.context_window,
            )

        # Update metadata
        if meta is None:
            meta = SessionMeta(session_id=session_id, role_id=role_id)
        meta.touch()
        self._backend.save_meta(meta)

        logger.debug(
            f"[EpisodicMemory] Recorded turn {turn_id} for session {session_id[:20]}... "
            f"domain={domain} tables={tables_used or []}"
        )
        return record

    def get_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[QueryRecord]:
        """Get the query history for a session (most recent last)."""
        return self._backend.get_queries(session_id, limit=limit or self.query_history_limit)

    def get_context(
        self,
        session_id: str,
        max_turns: Optional[int] = None,
    ) -> ConversationContext:
        """Get the conversation context window for a session."""
        return self._backend.get_context(session_id, max_turns=max_turns or self.context_window)

    def get_context_snippet(self, session_id: str, max_turns: int = 6) -> str:
        """Get conversation context formatted as a prompt snippet."""
        ctx = self.get_context(session_id, max_turns=max_turns)
        return ctx.get_prompt_snippet(max_turns=max_turns)

    def set_scratchpad(
        self,
        session_id: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """Set a scratchpad value for this session."""
        self._backend.set_scratchpad(
            session_id, key, value,
            ttl=ttl or DEFAULT_SCRATCHPAD_TTL_SECONDS,
        )
        logger.debug(f"[EpisodicMemory] Scratchpad set: session={session_id[:20]} key={key}")

    def get_scratchpad(
        self,
        session_id: str,
        key: str,
    ) -> Optional[Any]:
        """Get a scratchpad value."""
        return self._backend.get_scratchpad(session_id, key)

    def get_all_scratchpad(self, session_id: str) -> Dict[str, Any]:
        """Get all scratchpad key-values for this session."""
        return self._backend.get_all_scratchpad(session_id)

    def delete_scratchpad_key(self, session_id: str, key: str) -> None:
        """Delete a specific scratchpad key."""
        self._backend.delete_scratchpad(session_id, key)

    def check_dedup(
        self,
        session_id: str,
        query: str,
        ttl: int = DEFAULT_DEDUP_TTL_SECONDS,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if query is a near-duplicate of a recent query in this session.
        Returns (is_duplicate, query_signature).

        If not duplicate, marks it for the TTL duration.
        """
        return self._backend.check_dedup(session_id, query, ttl=ttl)

    def get_session_meta(self, session_id: str) -> Optional[SessionMeta]:
        """Get session metadata."""
        return self._backend.get_meta(session_id)

    def update_session_meta(self, session_id: str, **kwargs) -> None:
        """Update session metadata fields."""
        meta = self._backend.get_meta(session_id)
        if meta is None:
            meta = SessionMeta(session_id=session_id)
        for k, v in kwargs.items():
            if hasattr(meta, k):
                setattr(meta, k, v)
        meta.touch()
        self._backend.save_meta(meta)

    def tag_session(self, session_id: str, tag: str) -> None:
        """Add a tag to a session."""
        meta = self._backend.get_meta(session_id)
        if meta is None:
            meta = SessionMeta(session_id=session_id)
        if tag not in meta.tags:
            meta.tags.append(tag)
        self._backend.save_meta(meta)

    def delete_session(self, session_id: str) -> None:
        """Delete all data for a session (logout/cleanup)."""
        self._backend.delete_session(session_id)
        logger.info(f"[EpisodicMemory] Session deleted: {session_id[:20]}...")

    def get_active_sessions(self) -> List[str]:
        """Get all active session IDs (admin/monitoring)."""
        return self._backend.get_all_session_ids()

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """
        Get a full summary of a session for debugging/admin.
        Includes: metadata, query count, table access summary, scratchpad.
        """
        meta = self._backend.get_meta(session_id)
        history = self._backend.get_queries(session_id, limit=100)
        scratchpad = self._backend.get_all_scratchpad(session_id)
        all_tables = {}
        for rec in history:
            for t in rec.tables_used:
                all_tables[t] = all_tables.get(t, 0) + 1
        return {
            "session_id": session_id,
            "meta": meta.to_dict() if meta else None,
            "query_count": len(history),
            "top_tables": sorted(all_tables.items(), key=lambda x: -x[1])[:10],
            "scratchpad_keys": list(scratchpad.keys()),
        }

    def get_recent_context_for_prompt(
        self,
        session_id: str,
        max_turns: int = 8,
    ) -> str:
        """
        Build a context string suitable for injecting into an LLM prompt.
        Includes:
          - Recent conversation turns (user/assistant exchange)
          - Recent query results (table access, confidence)
          - Session tags and role
        """
        meta = self._backend.get_meta(session_id)
        ctx = self.get_context(session_id, max_turns=max_turns)
        history = self._backend.get_history(session_id, limit=max_turns)

        lines = ["[Session Context]"]
        if meta:
            lines.append(f"Role: {meta.role_id} | Turns: {meta.turn_count} | Tags: {', '.join(meta.tags) or 'none'}")
        if ctx.turns:
            lines.append(f"Recent conversation:\n{ctx.get_prompt_snippet(max_turns=max_turns)}")
        if history:
            table_summary = []
            for rec in history[-3:]:
                tables_str = ", ".join(rec.tables_used[:5]) if rec.tables_used else "none"
                conf_str = f"{rec.confidence:.2f}" if rec.confidence else "?"
                table_summary.append(
                    f"  - [{rec.domain}] tables:{tables_str} conf:{conf_str}"
                )
            if table_summary:
                lines.append("Recent queries:\n" + "\n".join(table_summary))

        return "\n".join(lines)


# =============================================================================
# Module-level singleton + convenience function
# =============================================================================

_store: Optional[EpisodicMemoryStore] = None
_store_lock = Lock()


def get_memory_store(
    redis_url: Optional[str] = None,
    force_backend: Optional[str] = None,
) -> EpisodicMemoryStore:
    """Get the module-level EpisodicMemoryStore singleton."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                url = redis_url or _redis_url_from_env()
                _store = EpisodicMemoryStore(redis_url=url, force_backend=force_backend)
    return _store


def reset_memory_store() -> None:
    """Reset the singleton (mainly for testing)."""
    global _store
    with _store_lock:
        _store = None


def record_query(session_id: str, query: str, **kwargs) -> QueryRecord:
    """Convenience: record a query in the default store."""
    return get_memory_store().record_query(session_id=session_id, query=query, **kwargs)


def get_context(session_id: str, max_turns: int = 6) -> str:
    """Convenience: get context snippet from the default store."""
    return get_memory_store().get_context_snippet(session_id=session_id, max_turns=max_turns)
