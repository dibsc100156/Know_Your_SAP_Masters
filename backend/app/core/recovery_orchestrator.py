from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.recovery_router import EscalationRouter, RecoveryDecision
from app.core.recovery_types import RecoveryCase


@dataclass
class RecoveryResult:
    decision: RecoveryDecision
    case_snapshot: Dict[str, Any]
    trace: List[Dict[str, Any]] = field(default_factory=list)


class RecoveryOrchestrator:
    def __init__(self):
        self.router = EscalationRouter()

    def resolve_recovery(self, case: RecoveryCase, context: Dict[str, Any]) -> RecoveryResult:
        decision = self.router.route_recovery(case, context)

        trace_entry = {
            "event": "recovery_escalation_routed",
            "error_class": case.error_class,
            "severity": case.severity.value,
            "attempt_count": len(case.attempts),
            "chosen_lane": decision.lane.value,
            "reason": decision.reason,
        }

        return RecoveryResult(
            decision=decision,
            case_snapshot=case.to_dict(),
            trace=[trace_entry],
        )
