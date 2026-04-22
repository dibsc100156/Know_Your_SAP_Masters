from __future__ import annotations

from dataclasses import dataclass

from app.core.plan_cost_model import BenefitScore


@dataclass
class TriggerThreshold:
    min_benefit_score: float = 0.45


class ReplanPolicy:
    def __init__(self, threshold: TriggerThreshold | None = None):
        self.threshold = threshold or TriggerThreshold()

    def should_replan(self, score: BenefitScore) -> bool:
        return score.score >= self.threshold.min_benefit_score
