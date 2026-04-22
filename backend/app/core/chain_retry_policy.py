from __future__ import annotations

from dataclasses import dataclass

from app.core.chain_quality_gates import GateVerdict
from app.core.chain_types import ChainStep


@dataclass
class RetryDecision:
    action: str
    reason: str


class RetryPolicy:
    def next_action(self, step: ChainStep, gate_verdict: GateVerdict, attempts: int) -> RetryDecision:
        if gate_verdict.action == "PASS":
            return RetryDecision(action="PROCEED", reason=gate_verdict.reason)

        if gate_verdict.action == "HALT":
            return RetryDecision(action="HALT", reason=gate_verdict.reason)

        if gate_verdict.action == "RETRY":
            if attempts < step.retry_budget.max_retries:
                return RetryDecision(action="RETRY", reason=f"{gate_verdict.reason}; retry {attempts + 1}/{step.retry_budget.max_retries}")
            if step.stop_condition.halt_on_retry_exhausted and step.required:
                return RetryDecision(action="HALT", reason=f"{gate_verdict.reason}; retry budget exhausted")
            return RetryDecision(action="PROCEED", reason=f"{gate_verdict.reason}; proceeding via fallback")

        return RetryDecision(action="PROCEED", reason="no explicit action")
