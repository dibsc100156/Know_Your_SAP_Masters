"""
harness_runs.py — Harness Runs Table (Redis)
============================================
Tracks every orchestrator execution as a structured run record in Redis.
Each run is a full phase-by-phase audit trail — from query intake to masking.

Why a Harness Runs Table matters:
  - Retry from last successful phase instead of re-executing from scratch
  - Per-phase artifacts (SQL generated, tables found, row counts)
  - Validator fire events logged per phase (for failure attribution)
  - Query runs by role to build role-specific performance profiles
  - Active runs trackable for real-time monitoring

Redis key design:
  harness_run:{run_id}     → Hash  (all fields, artifacts as JSON string)
  harness_runs:by_role:{role} → Sorted Set  (score=timestamp, member=run_id)
  harness_runs:active      → Set  (run_ids still in "running" state)
  TTL: 30 days on all keys

No circular imports — this module only imports dataclasses and redis.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PhaseState:
    """Immutable snapshot of a single phase's execution."""
    phase: str              # e.g. "phase_1", "domain_bp_agent", "synthesis"
    status: str             # pending | running | completed | failed | skipped
    started_at: Optional[str] = None   # ISO-8601
    completed_at: Optional[str] = None  # ISO-8601
    duration_ms: int = 0
    error: Optional[str] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
    validator_fired: bool = False
    validator_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "artifacts": self.artifacts,
            "validator_fired": self.validator_fired,
            "validator_errors": self.validator_errors,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PhaseState":
        return cls(
            phase=d.get("phase", ""),
            status=d.get("status", "pending"),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            duration_ms=d.get("duration_ms", 0),
            error=d.get("error"),
            artifacts=d.get("artifacts", {}),
            validator_fired=d.get("validator_fired", False),
            validator_errors=d.get("validator_errors", []),
        )


@dataclass
class HarnessRun:
    """Complete record of a single query execution through the orchestrator."""
    run_id: str
    query: str
    user_role: str
    status: str               # running | completed | failed | partial
    swarm_routing: str       # single | parallel | cross_module | negotiation | escalated
    planner_reasoning: str = ""
    complexity_score: float = 0.0
    created_at: str = ""     # ISO-8601
    updated_at: str = ""     # ISO-8601
    execution_time_ms: int = 0
    confidence_score: float = 0.0
    phase_states: List[PhaseState] = field(default_factory=list)
    trajectory_log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "query": self.query,
            "user_role": self.user_role,
            "status": self.status,
            "swarm_routing": self.swarm_routing,
            "planner_reasoning": self.planner_reasoning,
            "complexity_score": self.complexity_score,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "execution_time_ms": self.execution_time_ms,
            "confidence_score": self.confidence_score,
            "phase_states": [p.to_dict() for p in self.phase_states],
            "trajectory_log": self.trajectory_log,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HarnessRun":
        phases = [
            PhaseState.from_dict(p) for p in d.get("phase_states", [])
        ]
        return cls(
            run_id=d.get("run_id", ""),
            query=d.get("query", ""),
            user_role=d.get("user_role", ""),
            status=d.get("status", "running"),
            swarm_routing=d.get("swarm_routing", "single"),
            planner_reasoning=d.get("planner_reasoning", ""),
            complexity_score=d.get("complexity_score", 0.0),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            execution_time_ms=d.get("execution_time_ms", 0),
            confidence_score=d.get("confidence_score", 0.0),
            phase_states=phases,
            trajectory_log=d.get("trajectory_log", []),
        )


# =============================================================================
# Redis Connection Singleton
# =============================================================================

_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    """Lazily initialised Redis connection (localhost:6379)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host="localhost",
            port=6379,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _redis_client


def set_redis(client: redis.Redis) -> None:
    """Allow external override of the Redis client (e.g. for testing)."""
    global _redis_client
    _redis_client = client


# =============================================================================
# Harness Runs Table
# =============================================================================

class HarnessRuns:
    """
    Redis-backed harness runs table.

    Usage:
        hr = HarnessRuns(get_redis())
        run_id = hr.start_run(query="vendor open POs", user_role="AP_CLERK", swarm_routing="cross_module")
        hr.update_phase(run_id, phase="phase_1", status="completed",
                        artifacts={"tables_found": ["EKKO", "EKPO"], "sql": "SELECT ..."},
                        validator_fired=True)
        hr.complete_run(run_id, status="completed")
    """

    # TTL: 30 days in seconds
    TTL_SECONDS = 30 * 24 * 60 * 60

    HASH_KEY = "harness_run:{run_id}"
    ACTIVE_SET = "harness_runs:active"
    ROLE_SET_PREFIX = "harness_runs:by_role:{role}"

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self._redis = redis_client or get_redis()

    # -------------------------------------------------------------------------
    # Core CRUD
    # -------------------------------------------------------------------------

    def start_run(
        self,
        run_id: Optional[str],
        query: str,
        user_role: str,
        swarm_routing: str = "single",
        planner_reasoning: str = "",
        complexity_score: float = 0.0,
    ) -> HarnessRun:
        """
        Create a new harness run record and return it.
        Pass run_id=None to auto-generate a UUID.
        """
        now = _iso_now()
        run_id = run_id or str(uuid.uuid4())

        run = HarnessRun(
            run_id=run_id,
            query=query,
            user_role=user_role,
            status="running",
            swarm_routing=swarm_routing,
            planner_reasoning=planner_reasoning,
            complexity_score=complexity_score,
            created_at=now,
            updated_at=now,
            execution_time_ms=0,
            confidence_score=0.0,
            phase_states=[],
        )

        pipe = self._redis.pipeline()

        # Store hash
        hash_key = self.HASH_KEY.format(run_id=run_id)
        pipe.hset(hash_key, mapping=self._run_to_hash(run))
        pipe.expire(hash_key, self.TTL_SECONDS)

        # Track in active set
        pipe.sadd(self.ACTIVE_SET, run_id)

        # Index by role
        role_key = self.ROLE_SET_PREFIX.format(role=user_role)
        pipe.zadd(role_key, {run_id: _unix_ts()})
        pipe.expire(role_key, self.TTL_SECONDS)

        pipe.execute()
        return run

    def add_trajectory_event(
        self,
        run_id: str,
        step: str,
        decision: str,
        reasoning: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a reasoning span/decision point in the run's trajectory log.
        """
        now = _iso_now()
        metadata = metadata or {}
        
        hash_key = self.HASH_KEY.format(run_id=run_id)
        if not self._redis.exists(hash_key):
            return
            
        run = self.get_run(run_id)
        if not run:
            return
            
        run.trajectory_log.append({
            "timestamp": now,
            "step": step,
            "decision": decision,
            "reasoning": reasoning,
            "metadata": metadata,
        })
        # Save back the single JSON field without overwriting the whole hash
        self._redis.hset(hash_key, "trajectory_log", json.dumps(run.trajectory_log))



    def hset_run_field(self, run_id: str, field: str, value: str) -> None:
        """Set a single field on a run hash without overwriting the whole hash."""
        hash_key = self.HASH_KEY.format(run_id=run_id)
        if not self._redis.exists(hash_key):
            return
        self._redis.hset(hash_key, field, value)
        self._redis.expire(hash_key, self.TTL_SECONDS)

    def update_phase(
        self,
        run_id: str,
        phase: str,
        status: str,
        artifacts: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        validator_fired: bool = False,
        validator_errors: Optional[List[str]] = None,
        duration_ms: int = 0,
    ) -> None:
        """
        Update or append a phase state to an existing run.
        If the phase already exists its state is overwritten (idempotent retry).
        """
        now = _iso_now()
        artifacts = artifacts or {}
        validator_errors = validator_errors or []

        hash_key = self.HASH_KEY.format(run_id=run_id)
        if not self._redis.exists(hash_key):
            return  # Run doesn't exist — skip silently

        # Load full run
        run = self.get_run(run_id)
        if run is None:
            return

        # Find existing phase or create new
        existing_idx = None
        for i, p in enumerate(run.phase_states):
            if p.phase == phase:
                existing_idx = i
                break

        now_ts = _iso_now()
        if existing_idx is not None:
            updated = run.phase_states[existing_idx]
            updated.status = status
            updated.completed_at = now_ts
            updated.duration_ms = _duration_ms(updated.started_at, now_ts)
            updated.error = error or updated.error
            updated.artifacts = artifacts or updated.artifacts
            updated.validator_fired = validator_fired or updated.validator_fired
            updated.validator_errors = validator_errors or updated.validator_errors
        else:
            new_phase = PhaseState(
                phase=phase,
                status=status,
                started_at=now_ts,
                completed_at=now_ts,
                duration_ms=duration_ms,
                error=error,
                artifacts=artifacts or {},
                validator_fired=validator_fired,
                validator_errors=validator_errors or [],
            )
            run.phase_states.append(new_phase)

        # Update hash
        self._redis.hset(hash_key, mapping=self._run_to_hash(run))
        self._redis.expire(hash_key, self.TTL_SECONDS)

    def complete_run(
        self,
        run_id: str,
        status: str = "completed",
        confidence_score: float = 0.0,
        execution_time_ms: int = 0,
    ) -> None:
        """Mark a run as completed/failed/partial and remove from active set."""
        now = _iso_now()
        hash_key = self.HASH_KEY.format(run_id=run_id)

        if not self._redis.exists(hash_key):
            return

        self._redis.hset(hash_key, mapping={
            "status": status,
            "confidence_score": str(confidence_score),
            "execution_time_ms": str(execution_time_ms),
            "updated_at": now,
        })
        self._redis.expire(hash_key, self.TTL_SECONDS)
        self._redis.srem(self.ACTIVE_SET, run_id)

    def get_run(self, run_id: str) -> Optional[HarnessRun]:
        """Retrieve a single run by run_id, or None if not found."""
        hash_key = self.HASH_KEY.format(run_id=run_id)
        raw = self._redis.hgetall(hash_key)
        if not raw:
            return None
        return self._hash_to_run(raw)

    def list_runs_by_role(self, role: str, limit: int = 50) -> List[HarnessRun]:
        """
        Return the most recent `limit` runs for a given role,
        ordered newest-first.
        """
        role_key = self.ROLE_SET_PREFIX.format(role=role)
        run_ids = self._redis.zrevrange(role_key, 0, limit - 1)
        runs = []
        for rid in run_ids:
            r = self.get_run(rid)
            if r is not None:
                runs.append(r)
        return runs

    def list_active_runs(self) -> List[HarnessRun]:
        """Return all runs currently in 'running' state."""
        run_ids = self._redis.smembers(self.ACTIVE_SET)
        runs = []
        for rid in run_ids:
            r = self.get_run(rid)
            if r is not None and r.status == "running":
                runs.append(r)
        return runs

    def get_phase_history(self, run_id: str) -> List[PhaseState]:
        """Return the ordered list of phase states for a run."""
        run = self.get_run(run_id)
        return run.phase_states if run else []

    # -------------------------------------------------------------------------
    # Convenience helpers (used by domain agents / planner)
    # -------------------------------------------------------------------------

    def start_phase(self, run_id: str, phase: str) -> None:
        """Mark a phase as started (pending → running)."""
        self.update_phase(run_id, phase, status="running")

    def skip_phase(self, run_id: str, phase: str) -> None:
        """Mark a phase as skipped (e.g. meta-path fast-path skips Schema RAG)."""
        self.update_phase(run_id, phase, status="skipped")

    def fail_phase(self, run_id: str, phase: str, error: str) -> None:
        """Mark a phase as failed with an error message."""
        self.update_phase(run_id, phase, status="failed", error=error)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _run_to_hash(self, run: HarnessRun) -> Dict[str, str]:
        """Serialise a HarnessRun to a Redis hash (all values are strings)."""
        d = run.to_dict()
        d["phase_states"] = json.dumps(d["phase_states"])
        d["trajectory_log"] = json.dumps(d.get("trajectory_log", []))
        # Convert all scalar fields to strings
        return {k: str(v) if not isinstance(v, str) else v for k, v in d.items()}

    def _hash_to_run(self, raw: Dict[str, str]) -> HarnessRun:
        """Deserialise a Redis hash back to a HarnessRun."""
        if "phase_states" in raw:
            raw["phase_states"] = json.loads(raw["phase_states"])
        if "trajectory_log" in raw:
            raw["trajectory_log"] = json.loads(raw["trajectory_log"])
        if "complexity_score" in raw:
            raw["complexity_score"] = float(raw["complexity_score"])
        if "confidence_score" in raw:
            raw["confidence_score"] = float(raw["confidence_score"])
        if "execution_time_ms" in raw:
            raw["execution_time_ms"] = int(raw["execution_time_ms"])
        return HarnessRun.from_dict(raw)


# =============================================================================
# Module-level convenience functions
# =============================================================================

_harness_runs_instance: Optional[HarnessRuns] = None


def get_harness_runs() -> HarnessRuns:
    """Global HarnessRuns singleton backed by the process Redis connection."""
    global _harness_runs_instance
    if _harness_runs_instance is None:
        _harness_runs_instance = HarnessRuns(get_redis())
    return _harness_runs_instance


# =============================================================================
# Utilities
# =============================================================================

def _iso_now() -> str:
    """Current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _unix_ts() -> float:
    """Current UTC timestamp as Unix float (for sorted set scores)."""
    return datetime.now(timezone.utc).timestamp()


def _duration_ms(start_iso: Optional[str], end_iso: Optional[str]) -> int:
    """Compute duration_ms between two ISO-8601 timestamps."""
    if not start_iso or not end_iso:
        return 0
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        return max(0, int((end - start).total_seconds() * 1000))
    except (ValueError, TypeError):
        return 0
