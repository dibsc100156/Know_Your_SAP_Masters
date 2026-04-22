from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.core.goal_types import GoalConstraint, GoalTarget, GoalThreshold


@dataclass
class QueryGoal:
    query: str
    role_id: str
    targets: List[GoalTarget] = field(default_factory=list)
    constraints: List[GoalConstraint] = field(default_factory=list)
    thresholds: GoalThreshold = field(default_factory=GoalThreshold)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "role_id": self.role_id,
            "targets": [{"name": t.name, "target_value": t.target_value} for t in self.targets],
            "constraints": [{"name": c.name, "required": c.required} for c in self.constraints],
            "thresholds": {
                "min_confidence": self.thresholds.min_confidence,
                "min_tables": self.thresholds.min_tables,
                "min_retrieval_quality": self.thresholds.min_retrieval_quality,
            },
            "metadata": self.metadata,
        }


def build_query_goal(query: str, auth_context: Any, session_context: Dict[str, Any] | None = None) -> QueryGoal:
    session_context = session_context or {}
    temporal = any(keyword in query.lower() for keyword in ["year", "month", "quarter", "trend", "as of", "between"])
    thresholds = GoalThreshold(
        min_confidence=0.7 if temporal else 0.65,
        min_tables=1,
        min_retrieval_quality=0.62 if temporal else 0.58,
    )
    return QueryGoal(
        query=query,
        role_id=getattr(auth_context, "role_id", "AP_CLERK"),
        targets=[
            GoalTarget(name="grounded_tables", target_value="at_least_one"),
            GoalTarget(name="answer_confidence", target_value=thresholds.min_confidence),
        ],
        constraints=[
            GoalConstraint(name="security_masking", required=True),
            GoalConstraint(name="sql_validation", required=True),
        ],
        thresholds=thresholds,
        metadata={"session_context": session_context},
    )
