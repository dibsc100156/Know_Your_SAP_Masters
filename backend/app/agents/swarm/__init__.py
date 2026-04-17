"""
swarm/__init__.py — Multi-Agent Domain Swarm
=============================================
Exports the core swarm components:

  PlannerAgent   — routing and dispatch (entry point for the swarm)
  SynthesisAgent — merges + ranks + synthesizes multi-agent results
  SwarmDecision  — routing plan dataclass
  AgentInbox     — async inbox listener per agent
  InboxManager   — manages lifecycle of all agent inboxes

Usage:
    from app.agents.swarm import PlannerAgent, run_swarm

    planner = PlannerAgent()
    result = planner.execute(query="vendor open POs over 50000", auth_context=ctx)

    # Or use the convenience function:
    result = run_swarm(query, auth_context, domain_hint="auto")

    # With async inbox support:
    from app.agents.swarm import MessageDispatcher, run_swarm
    dispatcher = MessageDispatcher()
    result = run_swarm(query, auth_context, enable_inboxes=True, dispatcher=dispatcher)
"""

from typing import Optional

from app.agents.swarm.planner_agent import (
    PlannerAgent,
    SwarmDecision,
    RoutingType,
    AgentAssignment,
    QueryComplexityAnalyzer,
)
from app.agents.swarm.synthesis_agent import SynthesisAgent
from app.core.agent_inbox import AgentInbox, InboxManager

__all__ = [
    "PlannerAgent",
    "SwarmDecision",
    "RoutingType",
    "AgentAssignment",
    "QueryComplexityAnalyzer",
    "SynthesisAgent",
    "AgentInbox",
    "InboxManager",
]


# ---------------------------------------------------------------------------
# Global inbox manager (lazy-initialized per dispatcher)
# ---------------------------------------------------------------------------
_inbox_manager: Optional[InboxManager] = None


def _get_inbox_manager(dispatcher) -> InboxManager:
    global _inbox_manager
    if _inbox_manager is None:
        _inbox_manager = InboxManager(dispatcher)
    return _inbox_manager


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

def run_swarm(
    query: str,
    auth_context,
    domain_hint: str = "auto",
    verbose: bool = False,
    use_swarm: bool = True,
    run_id: Optional[str] = None,
    enable_inboxes: bool = False,
    dispatcher = None,
) -> dict:
    """
    Convenience entry point — runs the multi-agent swarm or falls back
    to the monolithic orchestrator based on use_swarm flag.

    Args:
        query: Natural language question
        auth_context: SAPAuthContext
        domain_hint: Optional domain hint (auto, business_partner, purchasing, etc.)
        verbose: Print swarm reasoning steps
        use_swarm: If True, use PlannerAgent; if False, use monolithic orchestrator
        run_id: Optional harness run ID for trajectory logging
        enable_inboxes: If True, start async inboxes for all domain agents before swarm run
        dispatcher: MessageDispatcher instance (required if enable_inboxes=True)

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

    # Optionally start inboxes for all domain agents (async messaging support)
    inbox_mgr = None
    if enable_inboxes:
        if dispatcher is None:
            raise ValueError("dispatcher required when enable_inboxes=True")
        inbox_mgr = _get_inbox_manager(dispatcher)
        inbox_mgr.start_all(
            ["pur_agent", "bp_agent", "mm_agent", "sd_agent", "qm_agent", "wm_agent", "cross_agent"],
            run_id=run_id,
        )

    try:
        planner = PlannerAgent()
        return planner.execute(
            query=query,
            auth_context=auth_context,
            domain_hint=domain_hint,
            verbose=verbose,
            run_id=run_id,
        )
    finally:
        # Clean up inboxes after swarm execution
        if inbox_mgr is not None:
            inbox_mgr.stop_all()