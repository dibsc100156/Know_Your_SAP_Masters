from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.goal_types import GoalCheckpoint
from app.core.query_goal import QueryGoal


@dataclass
class GoalState:
    goal: QueryGoal
    checkpoints: List[GoalCheckpoint] = field(default_factory=list)
    progress: Dict[str, Any] = field(default_factory=dict)
    status: str = "in_progress"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal.to_dict(),
            "status": self.status,
            "progress": self.progress,
            "checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints],
        }


class GoalTracker:
    def __init__(self, goal: QueryGoal):
        self.state = GoalState(goal=goal)

    def update_goal_state(self, phase: str, status: str, **detail: Any) -> GoalState:
        self.state.checkpoints.append(GoalCheckpoint(phase=phase, status=status, detail=detail))
        self.state.progress[phase] = detail
        if status == "failed":
            self.state.status = "at_risk"
        elif phase == "final_answer" and status == "completed":
            self.state.status = "completed"
        return self.state

    def goal_trace(self) -> List[Dict[str, Any]]:
        return [checkpoint.to_dict() for checkpoint in self.state.checkpoints]
