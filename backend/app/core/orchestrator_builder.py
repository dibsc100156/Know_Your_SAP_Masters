"""
orchestrator_builder.py - Fluent Orchestrator Syntax (Priority 10)
==================================================================
Current problem (per Sam Bhagwat): Graph-node/edge APIs force developers to think 
in graph terms. Our orchestrator's run_agent_loop() is readable but the tool 
registration uses declarative dict structures that are opaque.

Introduce fluent step notation:
orchestrator = (
    OrchestratorBuilder()
    .step("schema_discovery", if_tier_not("trivial"))
    .step("graph_enhanced_schema", if_tier_in("simple", "complex", "expert"))
    .step("sql_pattern_match", always)
    .step("graph_traversal", if_tier_in("complex", "expert"))
    .step("sql_assembly", always)
    .step("self_critique", if_confidence_below(0.70))
    .step("execute", always)
    .build()
)

This makes the orchestration flow visible at a glance.
"""

from typing import Callable, Any, Dict, List

ConditionFunc = Callable[[Dict[str, Any]], bool]

class OrchestratorPlan:
    def __init__(self, steps: List[Dict[str, Any]]):
        self._steps = steps
        self._step_map = {s["name"]: s["condition"] for s in steps}
        
    def should_run(self, step_name: str, context: Dict[str, Any]) -> bool:
        """Evaluate the condition for a given step based on context."""
        condition = self._step_map.get(step_name)
        if not condition:
            # Default to True if a step wasn't registered in the fluent builder
            # (Allows gradual adoption of the builder syntax)
            return True
            
        return condition(context)


class OrchestratorBuilder:
    def __init__(self):
        self._steps: List[Dict[str, Any]] = []
        
    def step(self, name: str, condition: ConditionFunc) -> 'OrchestratorBuilder':
        self._steps.append({"name": name, "condition": condition})
        return self
        
    def build(self) -> OrchestratorPlan:
        return OrchestratorPlan(self._steps)


# ---------------------------------------------------------------------------
# Fluent Conditions
# ---------------------------------------------------------------------------

def always(ctx: Dict[str, Any]) -> bool:
    return True

def never(ctx: Dict[str, Any]) -> bool:
    return False

def if_tier_not(excluded_tier: str) -> ConditionFunc:
    def condition(ctx: Dict[str, Any]) -> bool:
        tier = ctx.get("tier", "").lower()
        return tier != excluded_tier.lower()
    return condition

def if_tier_in(*allowed_tiers: str) -> ConditionFunc:
    allowed_lower = [t.lower() for t in allowed_tiers]
    def condition(ctx: Dict[str, Any]) -> bool:
        tier = ctx.get("tier", "").lower()
        return tier in allowed_lower
    return condition

def if_confidence_below(threshold: float) -> ConditionFunc:
    def condition(ctx: Dict[str, Any]) -> bool:
        conf = ctx.get("confidence", 1.0)
        return conf < threshold
    return condition

def if_tables_discovered() -> ConditionFunc:
    def condition(ctx: Dict[str, Any]) -> bool:
        tables = ctx.get("tables_involved", [])
        return len(tables) > 0
    return condition

def if_multi_table() -> ConditionFunc:
    def condition(ctx: Dict[str, Any]) -> bool:
        tables = ctx.get("tables_involved", [])
        return len(tables) > 1
    return condition

"""
Example usage in orchestrator.py:

from app.core.orchestrator_builder import OrchestratorBuilder, always, if_tier_not, if_tier_in, if_confidence_below

orchestrator_plan = (
    OrchestratorBuilder()
    .step("schema_discovery", if_tier_not("trivial"))
    .step("graph_enhanced_schema", if_tier_in("simple", "complex", "expert"))
    .step("sql_pattern_match", always)
    .step("graph_traversal", if_tier_in("complex", "expert"))
    .step("sql_assembly", always)
    .step("self_critique", if_confidence_below(0.70))
    .step("execute", always)
    .build()
)

context = {
    "tier": routing.tier.value,
    "confidence": current_confidence,
    "tables_involved": tables_involved
}

if not orchestrator_plan.should_run("schema_discovery", context):
    logger.info("SKIPPED")
"""