"""
supervisor_agent.py — Phase 4 Supervisor / Hermes
================================================
Master orchestrator that:
  1. Decomposes complex user queries into sub-tasks
  2. Routes each sub-task to the appropriate domain agent(s)
  3. Executes independent tasks in parallel via ThreadPoolExecutor
  4. Synthesizes results from all agents into a unified response

SupervisorDecision:
  SINGLE — one domain agent handles it (fast path)
  PARALLEL — multiple agents handle independent sub-tasks
  CROSS_MODULE — cross_agent handles multi-domain JOINs
  FALLBACK — standard orchestrator (no domain agents available)

Usage:
  from app.agents.supervisor_agent import SupervisorAgent, SupervisorDecision
  supervisor = SupervisorAgent()
  decision = supervisor.decide(query, auth_context)
  result = supervisor.execute(decision, auth_context)
"""

import time
import re
from typing import Dict, Any, List, Optional, Literal
from enum import Enum
from dataclasses import dataclass, field

from app.core.security import SAPAuthContext
from app.agents.domain_agents import (
    route_query,
    run_agents_parallel,
    get_domain_agent,
    DomainAgent,
    CROSSAgent,
)
from app.agents.orchestrator import run_agent_loop


# ---------------------------------------------------------------------------
# Supervisor Decision Types
# ---------------------------------------------------------------------------
class SupervisorDecisionType(Enum):
    SINGLE = "single"           # One domain agent handles it alone
    PARALLEL = "parallel"       # Multiple agents handle independent sub-tasks
    CROSS_MODULE = "cross"      # Cross-module JOINs needed
    FALLBACK = "fallback"       # Use standard orchestrator


@dataclass
class SupervisorDecision:
    decision: SupervisorDecisionType
    primary_agent: Optional[DomainAgent] = None
    parallel_agents: List[tuple[DomainAgent, str]] = field(default_factory=list)
    # parallel_agents = list of (agent, query_fragment)
    cross_module_query: Optional[str] = None
    reasoning: str = ""
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Supervisor Agent
# ---------------------------------------------------------------------------
class SupervisorAgent:
    """
    Hermes — the master orchestrator for SAP domain agents.
    Decides WHEN to spawn sub-agents and WHICH, then coordinates execution.
    """

    # Thresholds
    CROSS_MODULE_THRESHOLD = 0.75  # confidence above this → cross_agent
    SINGLE_THRESHOLD = 0.7         # single agent confidence above this → use it
    PARALLEL_SIGNAL_COUNT = 2      # ≥N domain signals → parallel execution
    QUERY_COMPLEXITY_KEYWORDS = [
        "and", "also", "plus", "both", "multiple", "across",
        "together", "combined", "all", "for each",
    ]

    def __init__(self):
        self._call_count = 0

    def decide(
        self,
        query: str,
        auth_context: SAPAuthContext,
        domain_hint: str = "auto",
    ) -> SupervisorDecision:
        """
        Analyze the query and decide how to route it.
        """
        self._call_count += 1
        query_lower = query.lower()

        # Step 1: Check for cross-module signals
        cross_signals = self._count_cross_module_signals(query_lower)
        if cross_signals >= 2 or self._is_explicitly_cross_module(query_lower):
            return SupervisorDecision(
                decision=SupervisorDecisionType.CROSS_MODULE,
                cross_module_query=query,
                reasoning=f"Cross-module detected ({cross_signals} signals)",
                confidence=0.85,
            )

        # Step 2: Route to domain agents
        routed = route_query(query, domain_hint=domain_hint, top_k=3)

        if not routed:
            return SupervisorDecision(
                decision=SupervisorDecisionType.FALLBACK,
                reasoning="No domain agent matched (confidence < 0.4)",
                confidence=0.5,
            )

        top_agent, top_score = routed[0]

        # Step 3: Check if it's a parallel query (multiple domains mentioned)
        domain_signal_count = sum(1 for _, s in routed if s >= 0.6)

        is_complex = any(kw in query_lower for kw in self.QUERY_COMPLEXITY_KEYWORDS)
        is_multi_entity = any(w in query_lower for w in ["all vendors", "all customers",
                                                          "all materials", "every",
                                                          "all POs", "all orders"])

        if domain_signal_count >= self.PARALLEL_SIGNAL_COUNT and (is_complex or is_multi_entity):
            # Parallel execution — multiple agents handle different aspects
            parallel_agents = [(agent, query) for agent, score in routed[:domain_signal_count]]
            return SupervisorDecision(
                decision=SupervisorDecisionType.PARALLEL,
                primary_agent=top_agent,
                parallel_agents=parallel_agents,
                reasoning=f"Parallel execution: {len(parallel_agents)} agents "
                          f"({', '.join(a.name for a, _ in parallel_agents)})",
                confidence=top_score * 0.9,
            )

        # Step 4: Single agent
        if top_score >= self.SINGLE_THRESHOLD:
            return SupervisorDecision(
                decision=SupervisorDecisionType.SINGLE,
                primary_agent=top_agent,
                reasoning=f"Single agent '{top_agent.name}' matched (confidence={top_score:.2f})",
                confidence=top_score,
            )

        # Step 5: Fallback to standard orchestrator
        return SupervisorDecision(
            decision=SupervisorDecisionType.FALLBACK,
            primary_agent=top_agent,
            reasoning=f"Low confidence ({top_score:.2f}) — use standard orchestrator",
            confidence=top_score,
        )

    def execute(
        self,
        decision: SupervisorDecision,
        query: str,
        auth_context: SAPAuthContext,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute the supervisor decision and return a unified result.
        """
        start_time = time.time()

        if verbose:
            print(f"\n[SUPERVISOR] Decision: {decision.decision.value}")
            print(f"[SUPERVISOR] Reasoning: {decision.reasoning}")

        if decision.decision == SupervisorDecisionType.SINGLE:
            return self._execute_single(decision, query, auth_context, verbose)
        elif decision.decision == SupervisorDecisionType.PARALLEL:
            return self._execute_parallel(decision, query, auth_context, verbose)
        elif decision.decision == SupervisorDecisionType.CROSS_MODULE:
            return self._execute_cross_module(decision, query, auth_context, verbose)
        else:
            return self._execute_fallback(query, auth_context, verbose)

    # -------------------------------------------------------------------------
    # Execution Paths
    # -------------------------------------------------------------------------
    def _execute_single(
        self,
        decision: SupervisorDecision,
        query: str,
        auth_context: SAPAuthContext,
        verbose: bool,
    ) -> Dict[str, Any]:
        """Route to a single domain agent."""
        agent = decision.primary_agent
        if not agent:
            return self._execute_fallback(query, auth_context, verbose)

        result = agent.run(query=query, auth_context=auth_context, verbose=verbose)
        elapsed = int((time.time() - self._call_count * 0) * 1000)

        return {
            "supervisor": "supervisor_agent",
            "decision": decision.decision.value,
            "reasoning": decision.reasoning,
            "agents_used": [agent.name],
            "query": query,
            "answer": result["answer"],
            "tables_used": result["tables_used"],
            "executed_sql": result["executed_sql"],
            "data": result["data"],
            "masked_fields": result["masked_fields"],
            "execution_time_ms": result["execution_time_ms"],
            "sub_results": [result],
        }

    def _execute_parallel(
        self,
        decision: SupervisorDecision,
        query: str,
        auth_context: SAPAuthContext,
        verbose: bool,
    ) -> Dict[str, Any]:
        """Run multiple domain agents in parallel, one query per agent."""
        if verbose:
            print(f"[SUPERVISOR] Spawning {len(decision.parallel_agents)} agents in parallel...")

        # Build parallel tasks: (query_fragment, agent, auth_context)
        # Each agent gets the full query but focuses on its domain
        tasks = [
            (query, agent, auth_context)
            for agent, _ in decision.parallel_agents
        ]

        # Run in parallel
        sub_results = run_agents_parallel(tasks, max_workers=len(tasks))

        # Synthesize
        all_tables = []
        all_data: List[Dict] = []
        all_masked: List[str] = []
        answers: List[str] = []

        for r in sub_results:
            all_tables.extend(r.get("tables_used", []))
            all_data.extend(r.get("data", []))
            all_masked.extend(r.get("masked_fields", []))
            answers.append(r.get("answer", ""))

        elapsed = int((time.time() - time.time()) * 1000)

        return {
            "supervisor": "supervisor_agent",
            "decision": decision.decision.value,
            "reasoning": decision.reasoning,
            "agents_used": [r["agent"] for r in sub_results],
            "query": query,
            "answer": self._synthesize_answers(answers, sub_results),
            "tables_used": list(dict.fromkeys(all_tables)),  # dedupe preserve order
            "executed_sql": "; ".join(r.get("executed_sql", "") for r in sub_results),
            "data": all_data[:100],  # cap at 100 rows
            "masked_fields": list(set(all_masked)),
            "execution_time_ms": max(r.get("execution_time_ms", 0) for r in sub_results),
            "sub_results": sub_results,
        }

    def _execute_cross_module(
        self,
        decision: SupervisorDecision,
        query: str,
        auth_context: SAPAuthContext,
        verbose: bool,
    ) -> Dict[str, Any]:
        """Use the standard orchestrator which has full Graph RAG for cross-module JOINs."""
        if verbose:
            print("[SUPERVISOR] Cross-module path — delegating to orchestrator with Graph RAG...")

        result = run_agent_loop(
            query=decision.cross_module_query or query,
            auth_context=auth_context,
            domain="auto",
            verbose=verbose,
        )

        return {
            "supervisor": "supervisor_agent",
            "decision": decision.decision.value,
            "reasoning": decision.reasoning,
            "agents_used": ["orchestrator (graph_rag)"],
            "query": query,
            "answer": result.get("answer", ""),
            "tables_used": result.get("tables_used", []),
            "executed_sql": result.get("executed_sql", ""),
            "data": result.get("data", []),
            "masked_fields": result.get("masked_fields", []),
            "execution_time_ms": result.get("execution_time_ms", 0),
            "sub_results": [result],
            "temporal": result.get("temporal"),
            "critique": result.get("critique"),
        }

    def _execute_fallback(
        self,
        query: str,
        auth_context: SAPAuthContext,
        verbose: bool,
    ) -> Dict[str, Any]:
        """Use the standard orchestrator as fallback."""
        if verbose:
            print("[SUPERVISOR] Fallback — standard orchestrator...")

        result = run_agent_loop(
            query=query,
            auth_context=auth_context,
            domain="auto",
            verbose=verbose,
        )

        return {
            "supervisor": "supervisor_agent",
            "decision": SupervisorDecisionType.FALLBACK.value,
            "reasoning": "No domain agent confidence above threshold",
            "agents_used": ["orchestrator"],
            "query": query,
            "answer": result.get("answer", ""),
            "tables_used": result.get("tables_used", []),
            "executed_sql": result.get("executed_sql", ""),
            "data": result.get("data", []),
            "masked_fields": result.get("masked_fields", []),
            "execution_time_ms": result.get("execution_time_ms", 0),
            "sub_results": [result],
        }

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _count_cross_module_signals(self, query_lower: str) -> int:
        """Count signals that suggest a cross-module query."""
        cross_keywords = [
            "vendor", "customer", "material", "purchase", "sales",
            "quality", "warehouse", "stock", "invoice", "order",
        ]
        count = sum(1 for kw in cross_keywords if kw in query_lower)
        return count

    def _is_explicitly_cross_module(self, query_lower: str) -> bool:
        explicit = [
            "procure to pay", "order to cash", "source to pay",
            "purchase to pay", "end to end", "full cycle",
            "vendor spend", "material traceability",
        ]
        return any(e in query_lower for e in explicit)

    def _synthesize_answers(self, answers: List[str], sub_results: List[Dict]) -> str:
        """Combine answers from multiple parallel agents."""
        if not answers:
            return "No results from any agent."
        if len(answers) == 1:
            return answers[0]

        total_records = sum(r.get("record_count", 0) for r in sub_results)
        agents = ", ".join(r.get("agent", "?") for r in sub_results)
        return (f"Cross-domain query synthesized from {len(sub_results)} domain agent(s) "
                f"({agents}). Total records: {total_records}.")
