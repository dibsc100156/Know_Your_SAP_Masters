from __future__ import annotations

from dataclasses import dataclass

from app.core.chain_types import ChainOutput, QualityGate, StopCondition


@dataclass
class GateVerdict:
    action: str
    reason: str


class QualityGateEngine:
    def evaluate_step_result(self, step_output: ChainOutput, gate: QualityGate, stop_condition: StopCondition) -> GateVerdict:
        status = (step_output.status or "unknown").lower()

        if status == "error":
            return GateVerdict(
                action="HALT" if stop_condition.halt_on_error else "RETRY",
                reason="step returned error status",
            )

        if step_output.item_count == 0 and gate.allow_empty:
            return GateVerdict(action="PASS", reason="empty result allowed by gate")

        if step_output.item_count < gate.min_items:
            return GateVerdict(action="RETRY", reason=f"item_count {step_output.item_count} < min_items {gate.min_items}")

        if gate.min_score is not None and (step_output.score or 0.0) < gate.min_score:
            return GateVerdict(action="RETRY", reason=f"score {(step_output.score or 0.0):.3f} < min_score {gate.min_score:.3f}")

        return GateVerdict(action="PASS", reason="quality gate satisfied")
