from __future__ import annotations

from typing import List

from app.core.goal_drift_detector import CorrectionAction, DriftSignal
from app.core.goal_tracker import GoalState


class GoalPolicy:
    def evaluate_goal_policy(self, goal_state: GoalState, drift_signals: List[DriftSignal]) -> CorrectionAction:
        if not drift_signals:
            return CorrectionAction(action="continue", reason="goal on track")
        names = {signal.name for signal in drift_signals}
        if "missing_grounding" in names:
            return CorrectionAction(action="expand_retrieval", reason="grounding target missed")
        if "weak_retrieval" in names:
            return CorrectionAction(action="replan", reason="retrieval quality below target")
        if "low_confidence" in names:
            return CorrectionAction(action="self_heal", reason="confidence below goal threshold")
        return CorrectionAction(action="continue", reason="no blocking drift")
