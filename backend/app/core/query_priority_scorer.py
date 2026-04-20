"""
query_priority_scorer.py — Phase 22: Dynamic Query Prioritization
==============================================================
Urgency × Recency × Role-Authority scoring for Celery queue position.

Score range: 0.0–10.0 (higher = more urgent)

Formula:
    priority_score = (
        URGENCY_WEIGHTS[urgency_level]        # 0.0–1.0
        × RECENCY_BOOST(queries_last_30min)   # 1.0 + up to 0.5 per recent query
        × ROLE_AUTHORITY[role_tier]           # 1.0–3.0 multiplier
        × COMPLEXITY_PENALTY(routing_tier)    # 1.0 (trivial) to 0.7 (expert)
        × SLA_BONUS(contract_type)             # 1.0 or 1.5
    )

Usage:
    scorer = QueryPriorityScorer(redis_client)
    score, breakdown = scorer.compute_priority(
        query="vendor payment terms",
        user_role="PROCUREMENT_MANAGER_EU",
        routing_tier="SIMPLE",
        domain="vendor",
        contract_type="premium",   # optional
        is_critical_report=False,
    )
    celery_kwargs = scorer.to_celery_kwargs(score)  # → {"priority": 7, "expires": 300}

Queue routing:
    score >= 8.0 → "priority" queue (fast lane)
    score >= 5.0 → "agent" queue with priority=N
    otherwise    → "agent" queue with default priority
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any

import redis

logger = logging.getLogger(__name__)

# ── Urgency Level Weights ──────────────────────────────────────────────────────

URGENCY_LEVELS = {
    "critical":  1.0,   # P0 — executive dashboard, system-down SLA
    "high":     0.8,   # P1 — business-critical report, deadline imminent
    "normal":   0.5,   # P2 — standard business query
    "low":      0.2,   # P3 — background analytics, batch
}

# ── Role Authority Multipliers ─────────────────────────────────────────────────
# Higher-tier roles get faster queue position (executive > manager > clerk > analyst)

ROLE_AUTHORITY = {
    "CFO_GLOBAL":               3.0,
    "COO_GLOBAL":               3.0,
    "CTO_GLOBAL":               3.0,
    "COO":                      2.5,
    "CTO":                      2.5,
    "VP":                       2.5,
    "DIRECTOR":                 2.0,
    "SENIOR_MANAGER":           1.8,
    "PROCUREMENT_MANAGER_EU":   1.6,
    "PROCUREMENT_MANAGER_AP":   1.6,
    "FINANCIAL_CONTROLLER":     1.5,
    "PLANT_MANAGER":            1.4,
    "MM_CLERK":                 1.2,
    "SD_CLERK":                 1.2,
    "FI_ACCOUNTANT":             1.2,
    "AP_CLERK":                 1.0,
    "HR_ADMIN":                 0.9,
    "ANALYST":                  0.7,
    "GUEST":                    0.5,
}

# ── SLA Contract Bonuses ────────────────────────────────────────────────────────

CONTRACT_BONUS = {
    "enterprise":  1.5,   # Enterprise SLA — 15-min P0 response
    "premium":     1.2,   # Premium SLA — 1-hr response
    "standard":    1.0,   # Standard SLA — best effort
    None:          1.0,
}

# ── Complexity Penalty (expert queries should run but not crowd out trivial) ─────

COMPLEXITY_PENALTY = {
    "trivial":  1.1,   # Fast — slight bonus for quick wins
    "simple":   1.0,   # Normal
    "complex":  0.85,  # Penalty — long-running queries wait more
    "expert":   0.70,  # Heavy penalty — don't crowd fast lane
}

# ── Redis key patterns ─────────────────────────────────────────────────────────

_RECENT_QUERIES_KEY  = "phase22:user:{user_id}:recent_queries"   # Sorted set: query_id → timestamp
_QUERY_COUNT_KEY     = "phase22:user:{user_id}:query_count_30min"  # String with TTL
_QUEUE_STATS_KEY     = "phase22:queue:agent:stats"               # Hash: {submitted, completed, avg_latency_ms}


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class PriorityBreakdown:
    """Full breakdown of a priority score — for explainability / audit."""
    urgency_raw:       float
    role_authority_raw: float
    complexity_raw:    float
    sla_bonus_raw:    float
    recency_boost:     float
    final_score:       float
    urgency_label:     str
    role_tier:         str
    routing_tier:      str
    queue_target:      str
    celery_priority:   int   # 0–10 for RabbitMQ

    def to_dict(self) -> Dict[str, Any]:
        return {
            "urgency_raw":        self.urgency_raw,
            "role_authority_raw":  self.role_authority_raw,
            "complexity_raw":     self.complexity_raw,
            "sla_bonus_raw":      self.sla_bonus_raw,
            "recency_boost":      self.recency_boost,
            "final_score":        self.final_score,
            "urgency_label":      self.urgency_label,
            "role_tier":         self.role_tier,
            "routing_tier":      self.routing_tier,
            "queue_target":       self.queue_target,
            "celery_priority":    self.celery_priority,
        }


@dataclass
class PriorityResult:
    """Result of a priority computation."""
    score: float                      # Raw score 0.0–15.0
    celery_priority: int               # RabbitMQ priority 0–10
    queue: str                         # "priority" | "agent" | "system"
    routing_key: str                   # RabbitMQ routing key
    breakdown: PriorityBreakdown
    redis_recorded: bool = False

    def to_celery_kwargs(self) -> Dict[str, Any]:
        """Args to pass to .send_task() or .apply_async()."""
        return {
            "priority": self.celery_priority,
            "expires": 300,           # 5-min task expiry if not started
            "routing_key": self.routing_key,
        }


# ── QueryPriorityScorer ───────────────────────────────────────────────────────

class QueryPriorityScorer:
    """
    Computes per-query priority score using urgency × recency × role-authority.

    Thread-safe. Redis is only touched for recency counting (non-critical path).
    All scoring logic is in-memory.
    """

    # Celery priority range is 0–10; we map our 0–15 score range to it
    _CELERY_MIN: float = 0.0
    _CELERY_MAX: float = 15.0
    _CELERY_RANGE: float = 10.0   # max priority in RabbitMQ

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        recency_window_s: int = 1800,   # 30 minutes
        max_recency_queries: int = 20,
    ):
        self._redis = redis_client
        self._recency_window_s = recency_window_s
        self._max_recency = max_recency_queries

    # ── Public API ─────────────────────────────────────────────────────────────

    def compute_priority(
        self,
        query: str,
        user_role: str,
        routing_tier: str = "simple",
        domain: str = "auto",
        urgency: str = "normal",           # "critical" | "high" | "normal" | "low"
        contract_type: Optional[str] = None,
        is_critical_report: bool = False,
        user_id: Optional[str] = None,
    ) -> PriorityResult:
        """
        Compute priority score and Celery routing for a query.

        Args:
            query:               The natural language query
            user_role:           SAP role key (e.g. "AP_CLERK", "CFO_GLOBAL")
            routing_tier:        Phase L5 tier: "trivial" | "simple" | "complex" | "expert"
            domain:              SAP domain hint
            urgency:             Urgency level from request header or user preference
            contract_type:       SLA contract: "enterprise" | "premium" | "standard"
            is_critical_report: True if query is a P0 executive dashboard report
            user_id:             Override user_id (defaults to role-based guest)

        Returns:
            PriorityResult with score, Celery kwargs, and full breakdown.
        """
        # Normalize inputs
        role_key = self._normalize_role(user_role)
        routing_tier = routing_tier.lower() if routing_tier else "simple"
        urgency = urgency.lower() if urgency else "normal"
        contract_type = contract_type.lower() if contract_type else None

        # Factor 1: Urgency weight
        u_raw = URGENCY_LEVELS.get(urgency, 0.5)

        # Factor 2: Role authority multiplier
        role_mult = ROLE_AUTHORITY.get(role_key, 1.0)
        role_tier = self._role_tier(role_key)

        # Factor 3: Complexity penalty
        complexity_mult = COMPLEXITY_PENALTY.get(routing_tier, 1.0)

        # Factor 4: SLA bonus
        sla_mult = CONTRACT_BONUS.get(contract_type, 1.0)

        # Factor 5: Recency boost (if user submitted recent queries)
        recency_boost = self._compute_recency_boost(user_role, domain)

        # Critical report → 2x score multiplier (P0 executive SLA)
        critical_boost = 1.0
        if is_critical_report:
            u_raw = 1.0
            role_mult = max(role_mult, 2.5)   # Boost even clerk queries if P0
            critical_boost = 2.0              # P0 SLA multiplier

        # Compute raw score
        raw_score = (
            u_raw
            * role_mult
            * complexity_mult
            * sla_mult
            * recency_boost
            * critical_boost
        )

        # Clamp to 0–15
        final_score = max(0.0, min(15.0, raw_score))

        # Map to Celery priority 0–10
        celery_priority = self._to_celery_priority(final_score)

        # Determine queue
        queue, routing_key = self._resolve_queue(final_score, is_critical_report)

        # Build breakdown
        breakdown = PriorityBreakdown(
            urgency_raw=u_raw,
            role_authority_raw=role_mult,
            complexity_raw=complexity_mult,
            sla_bonus_raw=sla_mult,
            recency_boost=recency_boost,
            final_score=round(final_score, 4),
            urgency_label=urgency,
            role_tier=role_tier,
            routing_tier=routing_tier,
            queue_target=queue,
            celery_priority=celery_priority,
        )

        # Record recency in Redis (fire-and-forget)
        recorded = False
        if self._redis is not None:
            try:
                self._record_query(user_role, domain)
                recorded = True
            except Exception as e:
                logger.debug(f"[Phase22] Redis recency record failed: {e}")

        logger.info(
            f"[Phase22] priority_score={final_score:.2f} queue={queue} "
            f"role={user_role} tier={routing_tier} urgency={urgency} "
            f"recency_boost={recency_boost:.2f}"
        )

        return PriorityResult(
            score=final_score,
            celery_priority=celery_priority,
            queue=queue,
            routing_key=routing_key,
            breakdown=breakdown,
            redis_recorded=recorded,
        )

    def compute_from_request(
        self,
        query: str,
        user_role: str,
        routing_tier: str = "simple",
        domain: str = "auto",
        urgency: str = "normal",
        contract_type: Optional[str] = None,
        is_critical_report: bool = False,
    ) -> PriorityResult:
        """
        Alias for compute_priority() — uses only request-level data
        (no user_id lookup needed). Preferred for API entry points.
        """
        return self.compute_priority(
            query=query,
            user_role=user_role,
            routing_tier=routing_tier,
            domain=domain,
            urgency=urgency,
            contract_type=contract_type,
            is_critical_report=is_critical_report,
        )

    # ── Priority Queue Stats ─────────────────────────────────────────────────

    def get_queue_stats(self) -> Dict[str, Any]:
        """Return approximate queue depth and latency from Redis."""
        if self._redis is None:
            return {"available": False, "reason": "no_redis_connection"}

        try:
            pipe = self._redis.pipeline()
            # Approximate depth via pending messages (Celery uses separate queues)
            pipe.llen("phase22:queue:depth")
            pipe.hget("phase22:queue:agent:stats", "avg_latency_ms")
            pipe.hget("phase22:queue:agent:stats", "submitted_last_5min")
            results = pipe.execute()

            return {
                "available": True,
                "approx_depth": results[0] or 0,
                "avg_latency_ms": float(results[1] or 0),
                "submitted_last_5min": int(results[2] or 0),
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    def record_task_completion(self, latency_ms: float):
        """Call after a Celery task completes to update queue stats."""
        if self._redis is None:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.hincrby("phase22:queue:agent:stats", "completed", 1)
            pipe.hset("phase22:queue:agent:stats", "last_latency_ms", str(latency_ms))
            # Rolling average: new_avg = (old_avg * n + new_val) / (n + 1)
            pipe.execute()
        except Exception as e:
            logger.debug(f"[Phase22] record_completion failed: {e}")

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _normalize_role(self, role: str) -> str:
        """Canonical role key."""
        return role.upper().strip()

    def _role_tier(self, role_key: str) -> str:
        """Human-readable tier for breakdown."""
        tier_map = {
            3.0: "executive",
            2.5: "senior_executive",
            2.0: "director",
            1.8: "senior_manager",
            1.6: "manager",
            1.5: "controller",
            1.4: "plant_manager",
            1.2: "clerk",
            1.0: "standard",
            0.9: "restricted",
            0.7: "analyst",
            0.5: "guest",
        }
        mult = ROLE_AUTHORITY.get(role_key, 1.0)
        return tier_map.get(mult, "standard")

    def _compute_recency_boost(self, user_role: str, domain: str) -> float:
        """
        If user has submitted queries recently → small boost (they're active session).
        If many recent queries → slight penalty (don't let power-users crowd out).
        """
        if self._redis is None:
            return 1.0

        try:
            key = _RECENT_QUERIES_KEY.format(user_id=user_role.lower())
            now = time.time()
            cutoff = now - self._recency_window_s

            # Remove stale entries
            self._redis.zremrangebyscore(key, 0, cutoff)

            # Count recent queries
            count = self._redis.zcard(key)

            if count == 0:
                return 1.0   # No recent queries — no boost or penalty

            # Light boost for first few recent queries (active session)
            # Penalty beyond 10 to prevent flooding
            if count <= 3:
                boost = 1.0 + (count * 0.05)   # +5% per recent query, max +15%
            elif count <= 10:
                boost = 1.0 + 0.15
            else:
                excess = min(count - 10, self._max_recency - 10)
                boost = max(0.8, 1.0 + 0.15 - (excess * 0.02))

            return boost

        except Exception:
            return 1.0   # Fail safe

    def _record_query(self, user_role: str, domain: str):
        """Add query to recency sorted set."""
        if self._redis is None:
            return
        key = _RECENT_QUERIES_KEY.format(user_id=user_role.lower())
        query_id = f"{time.time()}:{domain}"
        self._redis.zadd(key, {query_id: time.time()})
        # Expire the key after 35 minutes
        self._redis.expire(key, 2100)

    def _to_celery_priority(self, score: float) -> int:
        """Map 0–15 score range to Celery RabbitMQ priority 0–10."""
        normalized = (score - self._CELERY_MIN) / max(self._CELERY_MAX - self._CELERY_MIN, 0.001)
        priority = int(normalized * self._CELERY_RANGE)
        return max(0, min(10, priority))

    def _resolve_queue(self, score: float, is_critical: bool) -> Tuple[str, str]:
        """
        Map score to Celery queue and routing_key.

        Rules:
            - is_critical=True → priority queue (fastest path)
            - score >= 8.0     → priority queue (P0/P1 executives)
            - score >= 5.0     → agent queue with priority routing
            - otherwise        → agent queue (default priority)
        """
        if is_critical or score >= 8.0:
            return "priority", "priority"
        elif score >= 5.0:
            return "agent", "agent"
        else:
            return "agent", "agent"


# ── Module-level singleton ──────────────────────────────────────────────────────

_redis_client: Optional[redis.Redis] = None
_scorer: Optional[QueryPriorityScorer] = None


def get_priority_scorer() -> QueryPriorityScorer:
    """
    Returns the module-level QueryPriorityScorer singleton.
    Lazy-initializes Redis connection.
    """
    global _redis_client, _scorer
    if _scorer is None:
        try:
            _redis_client = redis.Redis(
                host="localhost",
                port=6379,
                db=0,
                decode_responses=False,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Test connection
            _redis_client.ping()
            logger.info("[Phase22] Redis connected for priority scoring")
        except Exception as e:
            logger.warning(f"[Phase22] Redis unavailable for priority scoring: {e}. Using in-memory mode.")
            _redis_client = None

        _scorer = QueryPriorityScorer(redis_client=_redis_client)

    return _scorer


def compute_priority(
    query: str,
    user_role: str,
    routing_tier: str = "simple",
    domain: str = "auto",
    urgency: str = "normal",
    contract_type: Optional[str] = None,
    is_critical_report: bool = False,
) -> PriorityResult:
    """Convenience function — delegates to the singleton scorer."""
    return get_priority_scorer().compute_from_request(
        query=query,
        user_role=user_role,
        routing_tier=routing_tier,
        domain=domain,
        urgency=urgency,
        contract_type=contract_type,
        is_critical_report=is_critical_report,
    )
