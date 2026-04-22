from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.core.recovery_types import RecoveryCase, RecoveryOption


@dataclass
class FallbackRule:
    error_class: str
    target_action: RecoveryOption
    condition: str = "always"


class RecoveryPolicy:
    def __init__(self):
        self.rules = [
            FallbackRule("sql_execution_error", RecoveryOption.PARTIAL, "has_partial_data"),
            FallbackRule("sql_execution_error", RecoveryOption.FALLBACK, "always"),
            FallbackRule("validation_error", RecoveryOption.HALT, "always"),
            FallbackRule("timeout_error", RecoveryOption.RETRY, "attempts < 2"),
        ]

    def evaluate_recovery_policy(self, case: RecoveryCase, state: Dict[str, Any]) -> RecoveryOption:
        for rule in self.rules:
            if rule.error_class == case.error_class or rule.error_class == "any":
                if rule.condition == "always":
                    return rule.target_action
                if rule.condition == "has_partial_data" and state.get("has_partial_data"):
                    return rule.target_action
                if rule.condition == "attempts < 2" and len(case.attempts) < 2:
                    return rule.target_action
        return RecoveryOption.HALT
