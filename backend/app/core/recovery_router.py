from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.core.recovery_policy import RecoveryPolicy
from app.core.recovery_types import RecoveryCase, RecoveryOption


@dataclass
class RecoveryDecision:
    lane: RecoveryOption
    reason: str


class EscalationRouter:
    def __init__(self):
        self.policy = RecoveryPolicy()

    def route_recovery(self, case: RecoveryCase, state: Dict[str, Any]) -> RecoveryDecision:
        lane = self.policy.evaluate_recovery_policy(case, state)

        if lane == RecoveryOption.RETRY:
            return RecoveryDecision(lane=lane, reason="Retry budget available for timeout or transient error.")
        if lane == RecoveryOption.PARTIAL:
            return RecoveryDecision(lane=lane, reason="Returning partial response data despite execution failure.")
        if lane == RecoveryOption.FALLBACK:
            return RecoveryDecision(lane=lane, reason="Falling back to simpler query pattern or LFA1 baseline.")
        if lane == RecoveryOption.HUMAN_REVIEW:
            return RecoveryDecision(lane=lane, reason="Escalating complex execution failure to human review.")

        return RecoveryDecision(lane=RecoveryOption.HALT, reason="No viable recovery lane; hard halting.")
