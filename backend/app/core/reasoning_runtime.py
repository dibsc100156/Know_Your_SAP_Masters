from __future__ import annotations

from typing import Any, Dict, List

from app.core.reasoning_trace import ReasoningTrace
from app.core.reasoning_types import ReasoningDepth, ReasoningStep, ReasoningSummary


class ReasoningRuntime:
    def __init__(self, depth: ReasoningDepth = ReasoningDepth.LIGHT):
        self.depth = depth
        self.steps: List[ReasoningStep] = []

    def record_reasoning_step(self, phase: str, decision: str, evidence: List[str] | None = None, detail: Dict[str, Any] | None = None) -> None:
        self.steps.append(ReasoningStep(
            phase=phase,
            decision=decision,
            evidence=list(evidence or []),
            detail=dict(detail or {}),
        ))

    def build_reasoning_trace(self) -> ReasoningTrace:
        phases = [step.phase for step in self.steps]
        summary = ReasoningSummary(depth=self.depth.value, step_count=len(self.steps), phases=phases)
        return ReasoningTrace(steps=self.steps, summary=summary)
