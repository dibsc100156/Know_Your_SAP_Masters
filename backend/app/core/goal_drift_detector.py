from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from app.core.goal_tracker import GoalState


@dataclass
class DriftSignal:
    name: str
    severity: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "severity": self.severity, "detail": self.detail}


@dataclass
class CorrectionAction:
    action: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "reason": self.reason}


class GoalDriftDetector:
    def detect_drift(self, goal_state: GoalState, execution_state: Dict[str, Any]) -> List[DriftSignal]:
        signals: List[DriftSignal] = []
        thresholds = goal_state.goal.thresholds
        if int(execution_state.get("tables_found", 0) or 0) < thresholds.min_tables:
            signals.append(DriftSignal("missing_grounding", "high", "too few grounded tables"))
        if float(execution_state.get("retrieval_quality", 1.0) or 1.0) < thresholds.min_retrieval_quality:
            signals.append(DriftSignal("weak_retrieval", "medium", "retrieval quality below target"))
        if float(execution_state.get("confidence", 1.0) or 1.0) < thresholds.min_confidence:
            signals.append(DriftSignal("low_confidence", "medium", "answer confidence below target"))
        return signals
