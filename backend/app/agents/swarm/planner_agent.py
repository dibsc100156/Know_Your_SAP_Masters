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


from app.agents.domain_agents import DomainAgent, BPAgent, MMAgent, PURAgent, SDAgent, QMAgent, WMAgent, CROSSAgent





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


# Agent as a Graph Routing (1.5:1 Scoring)


# ============================================================================





AGENT_TOOL_GRAPH = {


    "bp_agent": {


        "context": ["customer", "business partner", "bp", "account group", "reconciliation account"],


        "tools": ["LFA1", "KNA1", "BUT000", "ADRC", "credit limit", "payment terms", "blocked vendor", "tax number", "duns", "vendor master", "customer master"]


    },


    "mm_agent": {


        "context": ["material", "stock", "inventory", "mm", "valuation"],


        "tools": ["MARA", "MARC", "MARD", "MBEW", "MSKA", "valuation price", "material master", "stock quantity", "material type", "industry sector"]


    },


    "pur_agent": {


        "context": ["vendor", "purchasing", "procurement", "pur", "spend", "po", "purchase order", "open po", "rfq", "quotation", "info record", "contract", "source list"],


        "tools": ["EKKO", "EKPO", "EINA", "EINE", "EORD", "goods receipt", "invoice verification", "lifetime value", "vendor evaluation"]


    },


    "sd_agent": {


        "context": ["sales", "distribution", "sd", "sell", "order to cash"],


        "tools": ["VBAK", "VBAP", "LIKP", "KNVL", "KONV", "sales order", "delivery", "billing", "pricing", "discount", "incoterm"]


    },


    "qm_agent": {


        "context": ["quality", "inspection", "qm", "defect", "nonconformance"],


        "tools": ["QALS", "QMEL", "MAPL", "QAMV", "QAVE", "usage decision", "inspection lot", "control chart", "capability"]


    },


    "wm_agent": {


        "context": ["warehouse", "bin", "wm", "storage", "transfer"],


        "tools": ["LAGP", "LQUA", "VEKP", "MLGT", "handling unit", "transfer order", "physical inventory", "fifo", "lifo"]


    },


    "cross_agent": {


        "context": ["cross-module", "supply chain", "multi-entity", "consolidation", "procure to pay", "order to cash", "vendor performance", "spend analysis"],


        "tools": ["procurement analysis", "delivery performance", "material traceability", "material cost rollup", "vendor quality", "customer lifetime value"]


    }


}





def graph_route_query(query: str, domain_hint: str, domain_agents: Dict[str, DomainAgent], top_k: int) -> List[tuple[DomainAgent, float]]:


    """


    Implements 1.5:1 Agent:Tool scoring from 'Agent as a Graph' research.


    Restructures tool registry as a graph, scoring Agent Context 1.5x over Tool Specificity.


    """


    query_lower = query.lower()


    scored = []


    


    for agent_name, graph_node in AGENT_TOOL_GRAPH.items():


        # 1. Agent Context Relevance (Weight 1.5)


        # Use word-boundary matching for short keywords (<=3 chars) to avoid substring false matches


        agent_context_score = 0.0


        for kw in graph_node["context"]:


            if len(kw) <= 3:


                # Word-boundary match: surround with spaces


                if f" {kw} " in f" {query_lower} ":


                    agent_context_score += 0.5


            elif kw.lower() in query_lower:


                agent_context_score += 0.5


        if domain_hint in agent_name or domain_hint in graph_node["context"]:


            agent_context_score += 0.5


        agent_context_score = min(1.0, agent_context_score)





        # 2. Tool Specificity Score (Weight 1.0)


        tool_spec_score = 0.0


        for tool in graph_node["tools"]:


            if len(tool) <= 3:


                if f" {tool} " in f" {query_lower} ":


                    tool_spec_score += 0.5


            elif tool.lower() in query_lower:


                tool_spec_score += 0.5


        tool_spec_score = min(1.0, tool_spec_score)





        # 3. 1.5:1 Ratio Scoring


        if agent_context_score > 0 or tool_spec_score > 0:


            final_score = ((1.5 * agent_context_score) + (1.0 * tool_spec_score)) / 2.5


            if final_score >= 0.25:


                agent_instance = domain_agents.get(agent_name)


                if agent_instance:


                    scored.append((agent_instance, final_score))


                    


    scored.sort(key=lambda x: x[1], reverse=True)


    return scored[:top_k]





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


        harness_run_id: str = None,


    ) -> SwarmDecision:


        """


        Analyze the query and produce a SwarmDecision — the routing plan.


        This is the main entry point for the planner.


        """


        if verbose:


            print(f"\n[PLANNER] Analyzing: '{query[:80]}'")


            


        reasoning_log = []





        # Step 1: Route to domain agents — 1.5:1 Agent:Tool graph scoring


        routed = graph_route_query(query, domain_hint, self._domain_agents, self.max_parallel_agents)


        agent_scores = {name: conf for name, conf in [(n, s) for (a, s) in routed for n in [a.name]]}


        reasoning_log.append(f"Domain scoring: {', '.join(f'{k}={v:.2f}' for k, v in agent_scores.items())}")





        # Expand routed to dict format


        routed_agents = [(a, s) for a, s in routed]





        # Step 2: Complexity analysis


        complexity = QueryComplexityAnalyzer.total_score(query)


        complexity_details = QueryComplexityAnalyzer.analyze(query)


        reasoning_log.append(f"Complexity: {complexity:.2f}. Details: {complexity_details}")





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


        run_id: Optional[str] = None,


    ) -> Dict[str, Any]:


        """


        Dispatch to a single domain agent.


        Used when routing == SINGLE.


        """


        import json, tempfile, os


        plan_state = {


            "query": decision.query,


            "routing": decision.routing.value,


            "reasoning": decision.reasoning,


            "primary_domain": decision.primary_domain,


            "complexity": decision.complexity_score,


            "assignments": [{"agent": a.agent_name, "task": a.task} for a in decision.assignments]


        }


        fd, plan_path = tempfile.mkstemp(prefix=f"plan_{run_id or 'local'}_", suffix=".json", dir=".")


        with os.fdopen(fd, 'w') as f:


            json.dump(plan_state, f)





        if not decision.assignments:
            return {
                "error": "No domain agents assigned for this query.",
                "supervisor": "planner_agent",
                "decision": decision.routing.value if decision.routing else "unknown",
                "reasoning": decision.reasoning,
            }

        assignment = decision.assignments[0]


        agent = self._domain_agents.get(assignment.agent_name)


        if not agent:


            return {"error": f"Unknown agent: {assignment.agent_name}"}





        if verbose:


            print(f"\n[SWARM] Dispatching SINGLE to {agent.display_name} | State file: {plan_path}")





        phase_start = time.time()


        result = agent.run(


            query=decision.query,


            auth_context=auth_context,


            tables_hint=assignment.tables_hint,


            verbose=verbose,


            run_id=run_id,


            plan_path=plan_path,


        )





        try:


            os.remove(plan_path)


        except Exception:


            pass


        elapsed = int((time.time() - phase_start) * 1000)





        # [Harness] Track single-agent phase


        if run_id:


            try:


                from app.core.harness_runs import get_harness_runs


                hr = get_harness_runs()


                hr.update_phase(


                    run_id=run_id,


                    phase=f"domain_{assignment.agent_name}",


                    status="completed" if "error" not in result else "failed",


                    artifacts={


                        "agent": assignment.agent_name,


                        "tables_used": result.get("tables_used", []),


                        "record_count": result.get("record_count", 0),


                        "validation_passed": result.get("validation_passed"),


                    },


                    error=result.get("error"),


                    duration_ms=elapsed,


                )


            except Exception:


                pass





        result["swarm_routing"] = decision.routing.value


        result["planner_reasoning"] = decision.reasoning


        result["run_id"] = run_id or ""


        return result





    def dispatch_parallel(

        self,

        decision: SwarmDecision,

        auth_context: SAPAuthContext,

        verbose: bool = False,

        max_workers: int = 4,

        run_id: Optional[str] = None,

    ) -> Dict[str, Any]:

        """

        Dispatch to multiple domain agents as independent Celery tasks, each

        routed to its domain-specific queue (pur_queue, bp_queue, etc.).



        Used when routing == PARALLEL or CROSS_MODULE.



        Each agent runs in its own Celery worker process - completely isolated,

        independently scalable. Workers can be added per-queue via:



            celery -A app.workers.celery_app worker -Q pur_queue --concurrency=4



        Results are collected once all tasks complete, then passed to the

        Synthesis Agent for merging.



        Autoscaling: Each queue maps to one Kubernetes HPA / KEDA ScaledObject.

        During procurement peak, scale pur_queue to 10 replicas. During month-end

        close, scale fi_queue. Zero cross-interference between domain pools.

        """

        import json, tempfile, os



        plan_state = {

            "query": decision.query,

            "routing": decision.routing.value,

            "reasoning": decision.reasoning,

            "primary_domain": decision.primary_domain,

            "complexity": decision.complexity_score,

            "assignments": [{"agent": a.agent_name, "task": a.task} for a in decision.assignments]

        }

        fd, plan_path = tempfile.mkstemp(prefix=f"plan_{run_id or 'local'}_", suffix=".json", dir=".")

        with os.fdopen(fd, "w") as f:

            json.dump(plan_state, f)



        # Map agent_name -> queue for verbose display

        _agent_to_queue = {

            "pur_agent": "pur_queue", "bp_agent": "bp_queue",

            "mm_agent": "mm_queue", "sd_agent": "sd_queue",

            "qm_agent": "qm_queue", "wm_agent": "wm_queue",

            "cross_agent": "cross_queue",

        }

        if verbose:

            print(f"\n[SWARM] Dispatching {decision.routing.value.upper()} to {len(decision.assignments)} agents (Celery) | queues={{[_agent_to_queue.get(a.agent_name, 'agent') for a in decision.assignments]}} | plan_path={{plan_path}}")



        start = time.time()



                # -- ThreadPoolExecutor dispatch (reliable, cross-platform) ----------
        # On Windows + Celery solo pool, async result communication is broken.
        # Fall back to ThreadPoolExecutor for in-process parallel execution.
        # Swarm autoscaling via Celery workers remains available for Linux/production.
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run_agent_task(assignment):
            """Run one domain agent in a thread."""
            agent = self._domain_agents.get(assignment.agent_name)
            if not agent:
                return {
                    "error": f"Unknown agent: {assignment.agent_name}",
                    "status": "agent_not_found",
                    "agent_name": assignment.agent_name,
                }
            try:
                result = agent.run(
                    query=decision.query,
                    auth_context=auth_context,
                    tables_hint=assignment.tables_hint,
                    run_id=run_id,
                    plan_path=plan_path,
                    verbose=False,
                )
                result["status"] = result.get("status", "success")
                result["agent_name"] = assignment.agent_name
                return result
            except Exception as e:
                logger.exception(f"[_run_agent_task] {assignment.agent_name} error: {e}")
                return {
                    "error": str(e),
                    "status": "error",
                    "agent_name": assignment.agent_name,
                }

        start = time.time()
        raw_results = []
        with ThreadPoolExecutor(max_workers=min(len(decision.assignments), max_workers)) as pool:
            futures = {
                pool.submit(_run_agent_task, assignment): assignment
                for assignment in decision.assignments
            }
            for future in as_completed(futures):
                raw_results.append(future.result())

# -- Results already collected via ThreadPoolExecutor (above)



        # Map to agent_name-keyed dict (same shape as old ThreadPoolExecutor output)

        results = {}

        for i, result in enumerate(raw_results):

            agent_name = decision.assignments[i].agent_name if i < len(decision.assignments) else "unknown"

            if result.get("status") in ("error", "timeout", "role_error", "agent_not_found", "celery_error"):

                logger.warning(

                    f"[PLANNER] Agent {agent_name} returned status={result.get('status')} - result={result}"

                )

            results[agent_name] = result



        elapsed = int((time.time() - start) * 1000)





        # [Harness] Track synthesis phase


        synth_start = time.time()


        # Synthesis


        synthesis = self._synthesize(decision, results, auth_context)


        synth_elapsed = int((time.time() - synth_start) * 1000)





        try:


            os.remove(plan_path)


        except Exception:


            pass





        if run_id:


            try:


                from app.core.harness_runs import get_harness_runs


                hr = get_harness_runs()


                hr.update_phase(


                    run_id=run_id,


                    phase="synthesis",


                    status="completed" if synthesis.get("merged_data") else "failed",


                    artifacts={


                        "merged_records": len(synthesis.get("merged_data", [])),


                        "domain_coverage": synthesis.get("domain_coverage", []),


                        "conflicts": len(synthesis.get("conflicts", [])),


                        "synthesis_status": synthesis.get("status", "unknown"),


                    },


                    duration_ms=synth_elapsed,


                )


                # Complete the full run


                hr.complete_run(


                    run_id=run_id,


                    status="completed",


                    confidence_score=0.9,  # synthesis doesn't compute confidence


                    execution_time_ms=elapsed + synth_elapsed,


                )


            except Exception:


                pass





        ret = {


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


            "run_id": run_id or "",


        }


        return ret





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


        run_id: Optional[str] = None,


    ) -> Dict[str, Any]:


        """


        Main entry point — plan AND execute the swarm.


        Returns the final synthesized result.


        """


        # [Harness] Start run tracking (if run_id not already provided)


        hr = None


        if not run_id:


            try:


                from app.core.harness_runs import get_harness_runs


                hr = get_harness_runs()


                hr_run = hr.start_run(


                    run_id=None,


                    query=query,


                    user_role=auth_context.role_id,


                    swarm_routing="swarm",


                    planner_reasoning="",


                    complexity_score=0.0,


                )


                run_id = hr_run.run_id


                if verbose:


                    print(f"\n[HARNESS] Starting swarm run {run_id}")


            except Exception as e:


                if verbose:


                    print(f"\n[WARN] Harness unavailable: {e}")





        # Plan


        decision = self.plan(query, auth_context, domain_hint, verbose=verbose, harness_run_id=run_id)





        if verbose:


            print(f"[PLANNER] Decision: {decision.routing.value}")


            print(f"[PLANNER] Reasoning: {decision.reasoning}")





        # Log planner trajectory event


        if run_id:


            try:


                from app.core.harness_runs import get_harness_runs


                hr = get_harness_runs()


                hr.add_trajectory_event(


                    run_id=run_id,


                    step="planner_decision",


                    decision=decision.routing.value,


                    reasoning=decision.reasoning,


                    metadata={


                        "complexity": getattr(decision, "complexity", 0.0),


                        "agents_selected": [a.agent_name for a in decision.assignments],


                    }


                )


            except Exception as e:


                import logging


                logging.error(f"Failed to log planner trajectory for {run_id}: {e}")





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


            return self.dispatch_single(decision, auth_context, verbose=verbose, run_id=run_id)


        else:


            return self.dispatch_parallel(decision, auth_context, verbose=verbose, run_id=run_id)





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


