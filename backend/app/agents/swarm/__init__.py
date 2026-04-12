"""
swarm/__init__.py — Multi-Agent Domain Swarm
=============================================
Exports the three core swarm components:

  PlannerAgent   — routing and dispatch (entry point for the swarm)
  SynthesisAgent — merges + ranks + synthesizes multi-agent results
  SwarmDecision  — routing plan dataclass

Usage:
    from app.agents.swarm import PlannerAgent, run_swarm

    planner = PlannerAgent()
    result = planner.execute(query="vendor open POs over 50000", auth_context=ctx)

    # Or use the convenience function:
    result = run_swarm(query, auth_context, domain_hint="auto")
"""

from app.agents.swarm.planner_agent import (
    PlannerAgent,
    SwarmDecision,
    RoutingType,
    AgentAssignment,
    QueryComplexityAnalyzer,
)
from app.agents.swarm.synthesis_agent import SynthesisAgent

__all__ = [
    "PlannerAgent",
    "SwarmDecision",
    "RoutingType",
    "AgentAssignment",
    "QueryComplexityAnalyzer",
    "SynthesisAgent",
]


def run_swarm(
    query: str,
    auth_context,
    domain_hint: str = "auto",
    verbose: bool = False,
    use_swarm: bool = True,
):
    """
    Convenience entry point — runs the multi-agent swarm or falls back
    to the monolithic orchestrator based on use_swarm flag.

    Args:
        query: Natural language question
        auth_context: SAPAuthContext
        domain_hint: Optional domain hint (auto, business_partner, purchasing, etc.)
        verbose: Print swarm reasoning steps
        use_swarm: If True, use PlannerAgent; if False, use monolithic orchestrator

    Returns:
        Result dict with answer, data, agent trace, etc.
    """
    if not use_swarm:
        from app.agents.orchestrator import run_agent_loop
        return run_agent_loop(
            query=query,
            auth_context=auth_context,
            domain=domain_hint,
            verbose=verbose,
            use_supervisor=False,
        )

    planner = PlannerAgent()
    return planner.execute(
        query=query,
        auth_context=auth_context,
        domain_hint=domain_hint,
        verbose=verbose,
    )
