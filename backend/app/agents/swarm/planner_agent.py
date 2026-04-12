"""
planner_agent.py — Multi-Agent Domain Swarm: Planner Agent
=========================================================
The Planner is the entry point for every user query in the new swarm architecture.

Responsibilities:
  1. ANALYZE — Parse query intent, detect domain scope, identify complexity
  2. ROUTE   — Decide: single-agent | parallel-domains | cross-module | escalation
  3. DISPATCH — Hand off to selected Domain Agents with precise task instructions
  4. MONITOR  — Track agent progress, handle timeouts, collect partial results

Decision Tree:
  query
    ├─ SINGLE DOMAIN (confidence ≥ 0.85 from one agent)
    │     └─→ Domain Agent directly → Synthesis Agent → Response
    ├─ PARALLEL DOMAINS (2+ agents, score ≥ 0.5, no cross-module JOIN needed)
    │     └─→ Domain Agents [parallel] → Synthesis Agent → Response
    ├─ CROSS-MODULE (CROSS_AGENT score ≥ 0.7 OR multi-domain JOIN detected)
    │     └─→ CROSS_AGENT → Synthesis Agent → Response
    └─ COMPLEX / NEGOTIATION (contains negotiation, temporal, QM keywords)
          └─→ Specialist Agent(s) → Synthesis Agent → Response

Usage:
    from app.agents.swarm.planner_agent import PlannerAgent, SwarmDecision
    planner = PlannerAgent()
    decision = planner.plan(query, auth_context, domain_hint)
    if decision.routing == "parallel":
        results = planner.dispatch_parallel(decision)
"""

from __future__ import annotations

import re
import time
import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.security import SAPAuthContext
from app.agents.orchestrator_tools import call_tool, ToolResult, ToolStatus
from app.agents.domain_agents import (
    DomainAgent, BPAgent, MMAgent, PURAgent, SDAgent, QMAgent, WMAgent, CROSSAgent,
    route_query, list_domain_agents,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Swarm Routing Decision
# ============================================================================

class RoutingType(Enum):
    SINGLE      = "single"       # One domain agent handles alone
    PARALLEL    = "parallel"     # Multiple domain agents, no inter-agent JOINs
    CROSS_MODULE = "cross_module" # Graph traversal required across domains
    NEGOTIATION  = "negotiation"  # Negotiation/temporal/QM specialist path
    ESCALATE     = "escalate"     # Fall back to monolithic orchestrator


@dataclass
class AgentAssignment:
    agent_name: str
    agent_display: str
    confidence: float
    task: str                    # What specifically to do
    tables_hint: List[str] = field(default_factory=list)
    priority: int = 1            # 1=primary, 2=secondary


@dataclass
class SwarmDecision:
    routing: RoutingType
    query: str
    primary_domain: str
    assignments: List[AgentAssignment] = field(default_factory=list)
    requires_temporal: bool = False
    requires_negotiation: bool = False
    requires_qm_semantic: bool = False
    complexity_score: float = 0.0   # 0.0 = trivial, 1.0 = maximally complex
    reasoning: str = ""
    fallback_routing: RoutingType = RoutingType.ESCALATE


# ============================================================================
# Query Complexity Analyzer
# ============================================================================

class QueryComplexityAnalyzer:
    """
    Scores query complexity to determine whether the swarm overhead
    is justified vs. falling back to the monolithic orchestrator.
    """

    COMPLEXITY_INDICATORS = {
        "multi_entity": [
            r"\band\b.*\bor\b", r"both.*and", r"between.*and",
            r"vendor.*customer", r"material.*vendor",
        ],
        "aggregation": [
            r"total", r"sum", r"count", r"average", r"aggregate",
            r"by month", r"by year", r"by quarter", r"trend",
            r"fiscal year", r"fy\d{4}",
        ],
        "comparison": [
            r"compare", r"versus", r"vs\.?", r"difference between",
            r"more than", r"less than", r"greater than",
            r"top 5", r"bottom 10", r"rank",
        ],
        "temporal": [
            r"last year", r"prior year", r"ytd", r"year to date",
            r"last 3 years", r"last 5 years", r"trend",
            r"fy202", r"fy201", r"period \d+",
            r"during (covid|the crisis|the recession)",
        ],
        "cross_module_join": [
            r"vendor.*material", r"material.*vendor",
            r"po.*invoice", r"invoice.*payment",
            r"order.*delivery.*invoice",
            r"purchase.*finance", r"vendor.*accounting",
        ],
        "negotiation": [
            r"negotiat", r"contract renewal", r"price increase",
            r"leverage", r"batna", r"churn", r"clv",
            r"supplier scorecard", r"vendor review",
            r"customer lifetime", r"renewal",
        ],
        "qm_long_text": [
            r"quality issue", r"defect", r"nonconform",
            r"qm notification", r"mechanic note", r"complaint",
            r"failure.*history", r"inspection.*lot",
        ],
    }

    @classmethod
    def analyze(cls, query: str) -> Dict[str, float]:
        q = query.lower()
        scores = {}
        for dimension, patterns in cls.COMPLEXITY_INDICATORS.items():
            score = 0.0
            for pat in patterns:
                if re.search(pat, q, re.IGNORECASE):
                    score = max(score, 0.8)
            scores[dimension] = score
        return scores

    @classmethod
    def total_score(cls, query: str) -> float:
        scores = cls.analyze(query)
        weights = {
            "multi_entity": 0.15,
            "aggregation": 0.10,
            "comparison": 0.10,
            "temporal": 0.15,
            "cross_module_join": 0.25,
            "negotiation": 0.10,
            "qm_long_text": 0.15,
        }
        return sum(scores.get(k, 0) * weights.get(k, 0) for k in weights)


# ============================================================================
# Planner Agent
# ============================================================================

class PlannerAgent:
    """
    Swarm Planner — the intelligent routing layer that replaces
    the monolithic single-orchestrator entry point.
    """

    def __init__(self, min_single_confidence: float = 0.85,
                 min_parallel_confidence: float = 0.5,
                 max_parallel_agents: int = 3,
                 complexity_threshold: float = 0.6):
        """
        Args:
            min_single_confidence: Score needed for single-agent routing
            min_parallel_confidence: Minimum score for a domain agent to be included in parallel
            max_parallel_agents: Cap on parallel agents (avoid broadcast storms)
            complexity_threshold: Above this → escalate to monolithic orchestrator
        """
        self.min_single_confidence = min_single_confidence
        self.min_parallel_confidence = min_parallel_confidence
        self.max_parallel_agents = max_parallel_agents
        self.complexity_threshold = complexity_threshold

        # Instantiate domain agents
        self._domain_agents: Dict[str, DomainAgent] = {
            "bp_agent": BPAgent(),
            "mm_agent": MMAgent(),
            "pur_agent": PURAgent(),
            "sd_agent": SDAgent(),
            "qm_agent": QMAgent(),
            "wm_agent": WMAgent(),
            "cross_agent": CROSSAgent(),
        }

    def plan(
        self,
        query: str,
        auth_context: SAPAuthContext,
        domain_hint: str = "auto",
        verbose: bool = False,
    ) -> SwarmDecision:
        """
        Analyze the query and produce a SwarmDecision — the routing plan.
        This is the main entry point for the planner.
        """
        if verbose:
            print(f"\n[PLANNER] Analyzing: '{query[:80]}'")

        # Step 1: Route to domain agents
        routed = route_query(query, domain_hint=domain_hint, top_k=self.max_parallel_agents)
        agent_scores = {name: conf for name, conf in [(n, s) for (a, s) in routed for n in [a.name]]}

        # Expand routed to dict format
        routed_agents = [(a, s) for a, s in routed]

        # Step 2: Complexity analysis
        complexity = QueryComplexityAnalyzer.total_score(query)
        complexity_details = QueryComplexityAnalyzer.analyze(query)

        # Step 3: Check for specialist paths first (these override generic routing)
        requires_negotiation = complexity_details["negotiation"] >= 0.5
        requires_qm_semantic  = complexity_details["qm_long_text"] >= 0.5
        requires_temporal     = complexity_details["temporal"] >= 0.5

        # Step 4: Cross-module detection
        needs_cross_module = (
            complexity_details["cross_module_join"] >= 0.6
            or complexity_details["multi_entity"] >= 0.7
            or any(name == "cross_agent" for name, _ in routed_agents)
            and len(routed_agents) >= 2
        )

        # Step 5: Build assignments
        assignments = []
        for agent, score in routed_agents:
            a = AgentAssignment(
                agent_name=agent.name,
                agent_display=agent.display_name,
                confidence=float(score),
                task=self._build_task(query, agent, complexity_details),
                tables_hint=agent.primary_tables[:3],
                priority=1 if score == routed_agents[0][1] else 2,
            )
            assignments.append(a)

        # Step 6: Determine routing type
        if requires_negotiation or requires_qm_semantic:
            routing = RoutingType.NEGOTIATION
            reasoning = (
                "Specialist path: negotiation/QM keywords detected. "
                f"Negotiation={requires_negotiation}, QM={requires_qm_semantic}"
            )
        elif len(assignments) == 1 and assignments[0].confidence >= self.min_single_confidence and not needs_cross_module:
            routing = RoutingType.SINGLE
            reasoning = (
                f"Single agent routing: '{assignments[0].agent_name}' "
                f"confidence={assignments[0].confidence:.2f} >= {self.min_single_confidence}"
            )
        elif needs_cross_module or (len(assignments) >= 2 and any(a.confidence >= 0.7 for a in assignments)):
            routing = RoutingType.CROSS_MODULE
            reasoning = (
                f"Cross-module routing: {len(assignments)} agents involved, "
                f"cross_module_indicator={complexity_details['cross_module_join']:.2f}"
            )
            # Add CROSS_AGENT if not already present
            if not any(a.agent_name == "cross_agent" for a in assignments):
                cross = self._domain_agents["cross_agent"]
                assignments.append(AgentAssignment(
                    agent_name="cross_agent",
                    agent_display="Cross-Module Agent",
                    confidence=0.85,
                    task=self._build_task(query, cross, complexity_details),
                    tables_hint=[],
                    priority=1,
                ))
        elif len(assignments) >= 2:
            routing = RoutingType.PARALLEL
            reasoning = (
                f"Parallel domains: {len(assignments)} agents, "
                f"scores={[f'{a.agent_name}={a.confidence:.2f}' for a in assignments]}"
            )
        elif complexity >= self.complexity_threshold:
            routing = RoutingType.ESCALATE
            reasoning = (
                f"Complexity {complexity:.2f} >= threshold {self.complexity_threshold}. "
                "Escalating to monolithic orchestrator."
            )
        else:
            routing = RoutingType.SINGLE
            if assignments:
                assignments[0].priority = 1
            reasoning = f"Single agent fallback: {assignments[0].agent_name if assignments else 'none'}"

        decision = SwarmDecision(
            routing=routing,
            query=query,
            primary_domain=assignments[0].agent_name.split("_")[0] if assignments else "unknown",
            assignments=assignments,
            requires_temporal=requires_temporal,
            requires_negotiation=requires_negotiation,
            requires_qm_semantic=requires_qm_semantic,
            complexity_score=complexity,
            reasoning=reasoning,
        )

        if verbose:
            self._print_decision(decision)

        return decision

    def dispatch_single(
        self,
        decision: SwarmDecision,
        auth_context: SAPAuthContext,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Dispatch to a single domain agent.
        Used when routing == SINGLE.
        """
        assignment = decision.assignments[0]
        agent = self._domain_agents.get(assignment.agent_name)
        if not agent:
            return {"error": f"Unknown agent: {assignment.agent_name}"}

        result = agent.run(
            query=decision.query,
            auth_context=auth_context,
            tables_hint=assignment.tables_hint,
            verbose=verbose,
        )
        result["swarm_routing"] = decision.routing.value
        result["planner_reasoning"] = decision.reasoning
        return result

    def dispatch_parallel(
        self,
        decision: SwarmDecision,
        auth_context: SAPAuthContext,
        verbose: bool = False,
        max_workers: int = 4,
    ) -> Dict[str, Any]:
        """
        Dispatch to multiple domain agents in parallel threads.
        Used when routing == PARALLEL or CROSS_MODULE.

        Each agent runs its own Pillar 3+4 pipeline independently.
        Results are collected and passed to the Synthesis Agent.
        """
        start = time.time()

        def run_agent(assignment: AgentAssignment) -> Dict[str, Any]:
            agent = self._domain_agents.get(assignment.agent_name)
            if not agent:
                return {"error": f"Unknown agent: {assignment.agent_name}"}
            return agent.run(
                query=decision.query,
                auth_context=auth_context,
                tables_hint=assignment.tables_hint,
                verbose=verbose,
            )

        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_agent, a): a.agent_name
                for a in decision.assignments
            }
            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    results[agent_name] = future.result()
                except Exception as e:
                    logger.error(f"[PLANNER] Agent {agent_name} failed: {e}")
                    results[agent_name] = {"error": str(e), "agent": agent_name}

        elapsed = int((time.time() - start) * 1000)

        # Synthesis
        synthesis = self._synthesize(decision, results, auth_context)

        return {
            "swarm_routing": decision.routing.value,
            "planner_reasoning": decision.reasoning,
            "complexity_score": decision.complexity_score,
            "parallel_results": results,
            "synthesis": synthesis,
            # Flatten synthesis fields to top-level for API compatibility
            "answer": synthesis.get("answer", ""),
            "data": synthesis.get("merged_data", []),
            "tables_used": self._collect_tables_used(results),
            "executed_sql": self._collect_sql(results),
            "masked_fields": synthesis.get("masked_fields", []),
            "agent_summary": synthesis.get("agent_summary"),
            "domain_coverage": synthesis.get("domain_coverage"),
            "conflicts": synthesis.get("conflicts"),
            "execution_time_ms": elapsed,
            "agent_count": len(results),
        }

    def _synthesize(
        self,
        decision: SwarmDecision,
        agent_results: Dict[str, Any],
        auth_context: SAPAuthContext,
    ) -> Dict[str, Any]:
        """
        Synthesis Agent — combines results from multiple domain agents
        into a single coherent response.

        Handles:
        - Merging data from multiple domains
        - Deduplicating overlapping records
        - Generating a unified natural language answer
        - Ranking results by relevance
        """
        from app.agents.swarm.synthesis_agent import SynthesisAgent
        synthesizer = SynthesisAgent()
        return synthesizer.synthesize(
            query=decision.query,
            agent_results=agent_results,
            auth_context=auth_context,
            routing=decision.routing,
        )

    def execute(
        self,
        query: str,
        auth_context: SAPAuthContext,
        domain_hint: str = "auto",
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """
        Main entry point — plan AND execute the swarm.
        Returns the final synthesized result.
        """
        # Plan
        decision = self.plan(query, auth_context, domain_hint, verbose=verbose)

        if verbose:
            print(f"[PLANNER] Decision: {decision.routing.value}")
            print(f"[PLANNER] Reasoning: {decision.reasoning}")

        # Fallback to orchestrator for escalation
        if decision.routing == RoutingType.ESCALATE:
            if verbose:
                print("[PLANNER] Escalating to monolithic orchestrator...")
            from app.agents.orchestrator import run_agent_loop
            result = run_agent_loop(
                query=query,
                auth_context=auth_context,
                domain=domain_hint,
                verbose=verbose,
                use_supervisor=False,
            )
            result["swarm_routing"] = "escalated"
            result["planner_reasoning"] = decision.reasoning
            return result

        # Execute based on routing type
        if decision.routing == RoutingType.SINGLE:
            return self.dispatch_single(decision, auth_context, verbose=verbose)
        else:
            return self.dispatch_parallel(decision, auth_context, verbose=verbose)

    @staticmethod
    def _build_task(
        query: str,
        agent: DomainAgent,
        complexity: Dict[str, float],
    ) -> str:
        """Build a precise task description for the agent."""
        task = f"Answer the query using your domain expertise in {agent.domain}. "
        task += f"Focus on these tables: {', '.join(agent.primary_tables[:3])}. "
        if complexity.get("aggregation"):
            task += "Include aggregations, groupings, and totals where relevant. "
        if complexity.get("temporal"):
            task += "Apply temporal filters if date anchors are present in the query. "
        if complexity.get("comparison"):
            task += "Include comparisons or rankings if requested. "
        return task

    @staticmethod
    def _collect_tables_used(results: Dict[str, Any]) -> List[str]:
        """Collect unique tables from all agent results."""
        seen = set()
        tables = []
        for r in results.values():
            for t in r.get("tables_used", []):
                if t not in seen:
                    seen.add(t)
                    tables.append(t)
        return tables

    @staticmethod
    def _collect_sql(results: Dict[str, Any]) -> str:
        """Collect SQL from all agent results as a multi-statement string."""
        stmts = []
        for r in results.values():
            sql = r.get("executed_sql", "")
            if sql:
                stmts.append(sql)
        return "\n\n-- -.-\n\n".join(stmts) if stmts else ""

    @staticmethod
    def _print_decision(decision: SwarmDecision):
        print(f"\n{'='*60}")
        print(f"  SWARM DECISION: {decision.routing.value.upper()}")
        print(f"{'='*60}")
        print(f"  Query: {decision.query[:80]}")
        print(f"  Complexity: {decision.complexity_score:.2f}")
        print(f"  Reasoning: {decision.reasoning}")
        print(f"  Assignments:")
        for a in decision.assignments:
            print(f"    [{a.priority}] {a.agent_display} (conf={a.confidence:.2f}) — {a.task[:50]}...")
        print(f"  Flags: temporal={decision.requires_temporal} "
              f"negotiation={decision.requires_negotiation} "
              f"qm={decision.requires_qm_semantic}")
        print(f"{'='*60}\n")
