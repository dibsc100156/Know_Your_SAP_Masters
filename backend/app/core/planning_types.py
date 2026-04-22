from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PlanStep:
    name: str
    status: str = "pending"
    dependencies: List[str] = field(default_factory=list)
    cost_hint: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "dependencies": self.dependencies,
            "cost_hint": self.cost_hint,
            "metadata": self.metadata,
        }


@dataclass
class PlanRevision:
    stage: str
    reason: str
    benefit_score: float
    previous_steps: List[str]
    revised_steps: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "reason": self.reason,
            "benefit_score": round(self.benefit_score, 3),
            "previous_steps": self.previous_steps,
            "revised_steps": self.revised_steps,
        }


@dataclass
class ExecutionPlan:
    steps: List[PlanStep]
    revisions: List[PlanRevision] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def step_names(self) -> List[str]:
        return [step.name for step in self.steps]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "revisions": [revision.to_dict() for revision in self.revisions],
            "metadata": self.metadata,
        }
