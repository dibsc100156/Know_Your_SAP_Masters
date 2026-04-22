from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ReasoningDepth(str, Enum):
    LIGHT = "light"
    DETAILED = "detailed"


@dataclass
class ReasoningStep:
    phase: str
    decision: str
    evidence: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "decision": self.decision,
            "evidence": self.evidence,
            "detail": self.detail,
        }


@dataclass
class ReasoningSummary:
    depth: str
    step_count: int
    phases: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"depth": self.depth, "step_count": self.step_count, "phases": self.phases}
