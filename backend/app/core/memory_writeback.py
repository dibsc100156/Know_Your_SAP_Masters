from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.episodic_memory import EpisodicMemoryStore, get_memory_store
from app.core.memory_layer import sap_memory
from app.core.memory_policy import get_memory_policy


@dataclass
class MemoryEvent:
    event_type: str
    session_id: str
    query: str
    role_id: str
    domain: str = "auto"
    tables_used: Optional[List[str]] = None
    sql_generated: Optional[str] = None
    confidence: Optional[float] = None
    answer: Optional[str] = None
    routing_tier: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MemoryWriteDecision:
    target: str
    action: str
    reason: str
    ttl_seconds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "action": self.action,
            "reason": self.reason,
            "ttl_seconds": self.ttl_seconds,
        }


class MemoryWriteRouter:
    def __init__(self, memory_store: Optional[EpisodicMemoryStore] = None):
        self.memory_store = memory_store or get_memory_store()
        self.policy = get_memory_policy()

    def record_query(self, event: MemoryEvent) -> List[MemoryWriteDecision]:
        ttl = self.policy.retention_for("query")
        self.memory_store.record_query(
            session_id=event.session_id,
            query=event.query,
            tables_used=event.tables_used or [],
            sql_generated=event.sql_generated,
            domain=event.domain,
            role_id=event.role_id,
            confidence=event.confidence,
            answer=event.answer or "",
        )
        return [MemoryWriteDecision(target="episodic_memory", action="record_query", reason="persist session result", ttl_seconds=ttl)]

    def record_result(self, event: MemoryEvent) -> List[MemoryWriteDecision]:
        decisions: List[MemoryWriteDecision] = []
        self.memory_store.set_scratchpad(event.session_id, "last_domain", event.domain, ttl=self.policy.retention_for("result"))
        decisions.append(MemoryWriteDecision(target="scratchpad", action="set:last_domain", reason="carry forward resolved domain", ttl_seconds=self.policy.retention_for("result")))

        if event.routing_tier:
            self.memory_store.set_scratchpad(event.session_id, "last_routing_tier", event.routing_tier, ttl=self.policy.retention_for("result"))
            decisions.append(MemoryWriteDecision(target="scratchpad", action="set:last_routing_tier", reason="reuse routing hint", ttl_seconds=self.policy.retention_for("result")))

        if event.tables_used:
            self.memory_store.set_scratchpad(event.session_id, "last_tables", event.tables_used[:10], ttl=self.policy.retention_for("result"))
            decisions.append(MemoryWriteDecision(target="scratchpad", action="set:last_tables", reason="reuse recent table hints", ttl_seconds=self.policy.retention_for("result")))

        decisions.extend(self.record_query(event))
        return decisions

    def record_heal(self, event: MemoryEvent, heal_code: str, error: Optional[str] = None) -> List[MemoryWriteDecision]:
        if event.sql_generated:
            sap_memory.log_gotcha(
                pattern=f"heal:{heal_code}",
                domain=event.domain,
                severity="warn",
                description=error or "healed query pattern",
                remedy="prefer healed variant / critique before execution",
            )
        return [MemoryWriteDecision(target="persistent_memory", action="log_gotcha", reason=f"capture heal signal {heal_code}", ttl_seconds=self.policy.retention_for("heal"))]

    def record_feedback(self, event: MemoryEvent, rating: Optional[int] = None) -> List[MemoryWriteDecision]:
        if event.sql_generated and rating and rating >= 4:
            sap_memory.log_pattern_success(
                domain=event.domain,
                pattern_name=(event.metadata or {}).get("pattern_name", "feedback_success"),
                sql=event.sql_generated,
                tables=event.tables_used or [],
                user_rating=rating,
            )
            return [MemoryWriteDecision(target="persistent_patterns", action="boost_pattern", reason="positive feedback", ttl_seconds=self.policy.retention_for("feedback"))]
        return [MemoryWriteDecision(target="feedback", action="ignored", reason="no promotable feedback", ttl_seconds=self.policy.retention_for("feedback"))]


_router: Optional[MemoryWriteRouter] = None


def get_memory_write_router() -> MemoryWriteRouter:
    global _router
    if _router is None:
        _router = MemoryWriteRouter()
    return _router
