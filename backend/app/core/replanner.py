from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.plan_cost_model import PlanCostModel
from app.core.plan_dependencies import DependencyGraph
from app.core.plan_policy import ReplanPolicy
from app.core.planning_types import ExecutionPlan, PlanRevision


@dataclass
class ReplanTrigger:
    stage: str
    findings: Dict[str, Any]


class Replanner:
    def __init__(self):
        self.cost_model = PlanCostModel()
        self.policy = ReplanPolicy()
        self.dependencies = DependencyGraph()

    def build_initial_plan(self, selected_tools: List[str], metadata: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        steps = self.dependencies.attach_dependencies(selected_tools)
        return ExecutionPlan(steps=steps, metadata=metadata or {})

    def revise_plan(self, plan: ExecutionPlan, findings: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        score = self.cost_model.score_replan(plan, findings)
        if not self.policy.should_replan(score):
            return plan

        current_steps = plan.step_names()
        revised_steps = list(current_steps)
        reason_parts: List[str] = []

        if float(findings.get("schema_confidence", 1.0) or 1.0) < 0.6:
            revised_steps = self._ensure_before(revised_steps, "graph_enhanced_schema_discovery", "sql_pattern_lookup")
            reason_parts.append("low schema confidence")

        if int(findings.get("new_tables", 0) or 0) >= 2:
            revised_steps = self._ensure_before(revised_steps, "all_paths_explore", "sql_validate")
            reason_parts.append("new table expansion")

        if float(findings.get("retrieval_quality", 1.0) or 1.0) < 0.65:
            revised_steps = self._ensure_before(revised_steps, "all_paths_explore", "sql_validate")
            reason_parts.append("weak retrieval quality")

        if findings.get("temporal_mode", "none") != "none":
            revised_steps = self._ensure_before(revised_steps, "temporal_graph_search", "sql_validate")
            reason_parts.append("temporal mode active")

        revised_steps = list(dict.fromkeys(revised_steps))
        if revised_steps == current_steps:
            return plan

        revised_plan = ExecutionPlan(
            steps=self.dependencies.attach_dependencies(revised_steps),
            revisions=list(plan.revisions),
            metadata={**plan.metadata, **(context or {}), "last_findings": findings},
        )
        revised_plan.revisions.append(PlanRevision(
            stage=findings.get("stage", "unknown"),
            reason=", ".join(reason_parts) or score.rationale,
            benefit_score=score.score,
            previous_steps=current_steps,
            revised_steps=revised_steps,
        ))
        return revised_plan

    def _ensure_before(self, steps: List[str], step_name: str, anchor: str) -> List[str]:
        if step_name not in steps:
            if anchor in steps:
                idx = steps.index(anchor)
                steps.insert(idx, step_name)
            else:
                steps.append(step_name)
        return steps


_replanner: Optional[Replanner] = None


def get_replanner() -> Replanner:
    global _replanner
    if _replanner is None:
        _replanner = Replanner()
    return _replanner
