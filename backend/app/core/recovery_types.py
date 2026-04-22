from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RecoverySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryOption(str, Enum):
    RETRY = "retry"
    FALLBACK = "fallback"
    PARTIAL = "partial"
    HUMAN_REVIEW = "human_review"
    HALT = "halt"


@dataclass
class RecoveryAttempt:
    action: str
    success: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "success": self.success, "details": self.details}


@dataclass
class RecoveryCase:
    error_class: str
    error_message: str
    context: Dict[str, Any]
    severity: RecoverySeverity = RecoverySeverity.MEDIUM
    attempts: List[RecoveryAttempt] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_class": self.error_class,
            "error_message": self.error_message,
            "context": self.context,
            "severity": self.severity.value,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }
