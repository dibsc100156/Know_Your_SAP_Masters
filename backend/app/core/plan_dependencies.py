from __future__ import annotations

from typing import Dict, List

from app.core.planning_types import ExecutionPlan, PlanStep


DEFAULT_DEPENDENCIES: Dict[str, List[str]] = {
    "schema_lookup": [],
    "graph_enhanced_schema_discovery": ["schema_lookup"],
    "sql_pattern_lookup": ["schema_lookup"],
    "temporal_graph_search": ["schema_lookup"],
    "all_paths_explore": ["schema_lookup"],
    "sql_validate": ["sql_pattern_lookup"],
    "sql_execute": ["sql_validate"],
}


class DependencyGraph:
    def attach_dependencies(self, step_names: List[str]) -> List[PlanStep]:
        return [
            PlanStep(name=step, dependencies=[dep for dep in DEFAULT_DEPENDENCIES.get(step, []) if dep in step_names])
            for step in step_names
        ]

    def validate(self, plan: ExecutionPlan) -> bool:
        seen = set()
        for step in plan.steps:
            if any(dep not in seen for dep in step.dependencies):
                return False
            seen.add(step.name)
        return True
