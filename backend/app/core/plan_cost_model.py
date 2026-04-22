from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class BenefitScore:
    score: float
    rationale: str


class PlanCostModel:
    def score_replan(self, plan: Any, findings: Dict[str, Any]) -> BenefitScore:
        score = 0.0
        reasons = []
        schema_conf = float(findings.get("schema_confidence", 1.0) or 1.0)
        retrieval_quality = float(findings.get("retrieval_quality", 1.0) or 1.0)
        new_tables = int(findings.get("new_tables", 0) or 0)
        temporal_mode = findings.get("temporal_mode", "none")

        if schema_conf < 0.6:
            score += 0.35
            reasons.append("schema confidence is low")
        if retrieval_quality < 0.65:
            score += 0.35
            reasons.append("retrieval quality is low")
        if new_tables >= 2:
            score += 0.2
            reasons.append("new tables expanded plan surface")
        if temporal_mode != "none":
            score += 0.1
            reasons.append("temporal mode active")

        return BenefitScore(score=min(1.0, score), rationale=", ".join(reasons) or "no strong replan signal")
