from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from app.core.reasoning_types import ReasoningStep, ReasoningSummary


@dataclass
class ReasoningTrace:
    steps: List[ReasoningStep] = field(default_factory=list)
    summary: ReasoningSummary | None = None

    def to_dict(self) -> Dict:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "summary": self.summary.to_dict() if self.summary else None,
        }
