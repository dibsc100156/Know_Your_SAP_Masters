from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.chain_quality_gates import QualityGateEngine
from app.core.chain_retry_policy import RetryDecision, RetryPolicy
from app.core.chain_types import ChainOutput, ChainStep


@dataclass
class ChainState:
    step_attempts: Dict[str, int] = field(default_factory=dict)
    halted: bool = False
    halt_reason: Optional[str] = None


@dataclass
class ChainRunResult:
    trace: List[Dict]
    step_verdicts: Dict[str, Dict]
    halted: bool = False
    halt_reason: Optional[str] = None


class ChainController:
    def __init__(self, steps: List[ChainStep]):
        self.steps = {step.name: step for step in steps}
        self.state = ChainState()
        self.trace: List[Dict] = []
        self.step_verdicts: Dict[str, Dict] = {}
        self.gate_engine = QualityGateEngine()
        self.retry_policy = RetryPolicy()

    def evaluate_step(self, step_name: str, output: ChainOutput) -> RetryDecision:
        step = self.steps[step_name]
        attempts = self.state.step_attempts.get(step_name, 0)
        gate_verdict = self.gate_engine.evaluate_step_result(output, step.quality_gate, step.stop_condition)
        decision = self.retry_policy.next_action(step, gate_verdict, attempts)
        if decision.action == "RETRY":
            self.state.step_attempts[step_name] = attempts + 1
        else:
            self.state.step_attempts.setdefault(step_name, attempts)

        entry = {
            "step": step_name,
            "label": step.label,
            "status": output.status,
            "item_count": output.item_count,
            "score": output.score,
            "gate_verdict": gate_verdict.action,
            "gate_reason": gate_verdict.reason,
            "decision": decision.action,
            "decision_reason": decision.reason,
            "attempts": self.state.step_attempts.get(step_name, attempts),
        }
        self.trace.append(entry)
        self.step_verdicts[step_name] = entry

        if decision.action == "HALT":
            self.state.halted = True
            self.state.halt_reason = decision.reason

        return decision

    def result(self) -> ChainRunResult:
        return ChainRunResult(
            trace=self.trace,
            step_verdicts=self.step_verdicts,
            halted=self.state.halted,
            halt_reason=self.state.halt_reason,
        )
