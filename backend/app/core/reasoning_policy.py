from __future__ import annotations

from app.core.reasoning_trace import ReasoningTrace
from app.core.reasoning_types import ReasoningDepth, ReasoningStep


class ReasoningPolicy:
    def __init__(self, depth: ReasoningDepth = ReasoningDepth.LIGHT):
        self.depth = depth

    def filter_reasoning_trace(self, trace: ReasoningTrace) -> ReasoningTrace:
        if self.depth == ReasoningDepth.DETAILED:
            return trace
        filtered_steps = [
            ReasoningStep(
                phase=step.phase,
                decision=step.decision,
                evidence=step.evidence[:1],
                detail={},
            )
            for step in trace.steps
        ]
        trace.steps = filtered_steps
        return trace
