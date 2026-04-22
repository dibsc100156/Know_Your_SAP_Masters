from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GoalTarget:
    name: str
    target_value: Any


@dataclass
class GoalConstraint:
    name: str
    required: bool = True


@dataclass
class GoalThreshold:
    min_confidence: float = 0.65
    min_tables: int = 1
    min_retrieval_quality: float = 0.6


@dataclass
class GoalCheckpoint:
    phase: str
    status: str
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"phase": self.phase, "status": self.status, "detail": self.detail}
