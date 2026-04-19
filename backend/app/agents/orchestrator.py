"""

orchestrator.py — Agentic RAG Orchestrator (Pillar 2)

======================================================

Coordinates all 5 Pillars via the unified tool registry:

  Pillar 1: Role-Aware Security (sql_validate, result_mask)

  Pillar 3: Schema RAG (schema_lookup)

  Pillar 4: SQL RAG (sql_pattern_lookup)

  Pillar 5: Graph RAG (graph_traverse, all_paths_explore, temporal_graph_search)

  Phase 7: Temporal Engine (FY analysis, CLV, supplier SPI)

  Phase 8: QM Semantic Search (20yr QM notification long-text)

  Phase 8: Negotiation Briefing (CLV, PSI, churn risk, BATNA)

  Execution: sql_execute



Execution flow:

  Step 0: Meta-Path Match (fast-path — pre-computed JOIN templates)

  Step 1: Schema RAG (table discovery via Qdrant)

  Step 1.5: Graph Embedding Search (Pillar 5½ — Node2Vec structural discovery)

  Step 1.75: QM Semantic Search (Phase 8 — 20yr QM notification long-text search)

  Step 2: SQL Pattern RAG (proven patterns via ChromaDB)

  Step 2b: Temporal Detection (date/fiscal period → temporal SQL filters)

  Step 2c: Temporal Analysis Engine (Phase 7 — FY analysis, CLV, supplier SPI)

  Step 2d: Negotiation Briefing (Phase 8 — CLV, PSI, churn risk, BATNA, tactics)

  Step 3: Graph RAG (all-ranked-paths → best JOIN)

  Step 4: SQL Assembly + AuthContext + Temporal filter injection

  Step 5: Validate → Execute → Mask



The orchestrator can be used:

  1. Directly: run_agent_loop(query, auth_context, domain)

  2. Via API: POST /api/v1/chat/master-data

  3. Via CLI: python -m sap_tools /agent "your question" --role AP_CLERK

"""



import json

import re

import time

from typing import Dict, Any, List, Optional, Union



from app.agents.orchestrator_tools import (

    TOOL_REGISTRY,

    call_tool,

    list_tools,

    ToolResult,

    ToolStatus,

)

from app.agents.critique_agent import critique_agent

from app.core.memory_layer import sap_memory

from app.core.self_healer import self_healer

from app.core.schema_auto_discover import schema_auto_discoverer

from app.core.self_improver import self_improver

from app.core.temporal_engine import TemporalEngine

from app.core.security import SAPAuthContext

from app.core.harness_runs import get_harness_runs
from app.core.quality_evaluator import QualityEvaluator

import logging

logger = logging.getLogger(__name__)



# =============================================================================

# Harness Phase Tracking Helper

# =============================================================================



def _update_harness_phase(

    hr, run_id: str, phase: str, status: str,

    artifacts: Optional[Dict[str, Any]] = None,

    error: Optional[str] = None,

    duration_ms: int = 0,

    validator_fired: bool = False,

    validator_errors: Optional[List[str]] = None,

    verbose: bool = False,

) -> None:

    """"Log a phase completion to Redis (idempotent — safe to call even if Redis is down)."""

    if not run_id:

        return

    try:

        hr.update_phase(

            run_id=run_id,

            phase=phase,

            status=status,

            artifacts=artifacts or {},

            error=error,

            validator_fired=validator_fired,

            validator_errors=validator_errors or [],

        )

        if verbose:

            icon = "[OK]" if status == "completed" else "[FAIL]" if status == "failed" else "[SKIP]"

            logger.debug(f"  {icon} [HARNESS] phase={phase} status={status} dur={duration_ms}ms")

    except Exception as e:

        if verbose:

            logger.warning(f"  [WARN] [HARNESS] phase={phase} update failed: {e}")







# =============================================================================

# Confidence Score Computer

# =============================================================================



def _compute_confidence_score(

    critique_score: int,

    data_records: List[Any],

    meta_path_used: bool,

    self_heal_applied: bool,

    temporal_mode: str,

    tables_involved: List[str],

    execution_time_ms: int,

) -> Dict[str, Any]:

    """

    Computes a multi-signal composite confidence score (0.0–1.0) plus sub-scores

    for each signal. Exposed to the frontend for display.

    """

    signals = {}



    # Signal 1: SQL Critique Gate (weight 30%)

    # 7-point gate → normalize to 0-1

    critique_norm = critique_score / 7.0

    signals["critique"] = {

        "raw": critique_score,

        "max": 7,

        "weight": 0.30,

        "weighted": critique_norm * 0.30,

        "label": "SQL Critique",

        "detail": "SELECT-only, MANDT, AuthContext, JOIN sanity, LIMIT guard" if critique_norm >= 0.71 else "SQL gate issues detected",

    }



    # Signal 2: Data Quality (weight 25%)

    # More rows = higher confidence (query hit real data)

    row_count = len(data_records)

    if row_count == 0:

        data_score = 0.0   # empty result → uncertain

    elif row_count <= 5:

        data_score = 0.60  # sparse but valid

    elif row_count <= 100:

        data_score = 0.85  # healthy result set

    else:

        data_score = 1.0   # rich result

    signals["data_quality"] = {

        "raw": row_count,

        "score": data_score,

        "weight": 0.25,

        "weighted": data_score * 0.25,

        "label": "Result Density",

        "detail": f"{row_count} record(s) returned",

    }



    # Signal 3: Fast Path Bonus (weight 15%)

    # Pre-computed meta-path = proven, high-confidence route

    fast_path_score = 1.0 if meta_path_used else 0.65

    signals["routing_path"] = {

        "score": fast_path_score,

        "weight": 0.15,

        "weighted": fast_path_score * 0.15,

        "label": "Routing Path",

        "detail": "Meta-Path Fast Path (pre-assembled template)" if meta_path_used else "Orchestrator Standard Path (Schema + SQL RAG)",

    }



    # Signal 4: Self-Heal Penalty (weight 10%)

    # If autonomous repair fired, reduce confidence slightly

    heal_score = 0.60 if self_heal_applied else 1.0

    signals["self_heal"] = {

        "score": heal_score,

        "weight": 0.10,

        "weighted": heal_score * 0.10,

        "label": "Autonomous Repair",

        "detail": "Self-heal applied — see banner above" if self_heal_applied else "No autonomous repair needed",

    }



    # Signal 5: Temporal Awareness (weight 10%)

    # Temporal filters = query specificity → higher confidence

    temporal_score = 1.0 if temporal_mode != "none" else 0.70

    signals["temporal"] = {

        "score": temporal_score,

        "weight": 0.10,

        "weighted": temporal_score * 0.10,

        "label": "Temporal Precision",

        "detail": f"Temporal mode: {temporal_mode}" if temporal_mode != "none" else "No date/fiscal filter detected",

    }



    # Signal 6: Schema Breadth (weight 10%)

    # More tables involved = broader cross-module confidence

    table_count = len(tables_involved)

    if table_count <= 1:

        schema_score = 0.75

    elif table_count <= 3:

        schema_score = 0.90

    else:

        schema_score = 1.0

    signals["schema_breadth"] = {

        "score": schema_score,

        "weight": 0.10,

        "weighted": schema_score * 0.10,

        "label": "Cross-Module Breadth",

        "detail": f"{table_count} table(s) involved: {', '.join(tables_involved[:3])}",

    }



    composite = sum(s["weighted"] for s in signals.values())



    # Overall label

    if composite >= 0.85:

        grade = "HIGH"

    elif composite >= 0.65:

        grade = "MEDIUM"

    else:

        grade = "LOW"



    return {

        "composite": round(composite, 3),

        "grade": grade,

        "signals": signals,

        "critique_raw": critique_score,

        "row_count": row_count,

        "execution_time_ms": execution_time_ms,

    }





def run_agent_loop(

    query: str,

    auth_context: SAPAuthContext,

    domain: str = "auto",

    verbose: bool = False,

    use_supervisor: bool = True,

    use_swarm: bool = False,

) -> Dict[str, Any]:

    """

    Agentic RAG Orchestrator (Pillar 2).



    Coordinates Pillar 3 (Schema), Pillar 4 (SQL), Pillar 5 (Graph),

    Pillar 1 (Security), and Execution in a unified loop.



    Args:

        query: Natural language user question

        auth_context: SAPAuthContext with role permissions

        domain: Routing domain (auto, business_partner, purchasing, etc.)

        verbose: Print detailed reasoning steps

        use_supervisor: Use supervisor agent for routing decisions

        use_swarm: Use Multi-Agent Domain Swarm (PlannerAgent) instead of

                   the monolithic single-orchestrator path.

                   When True, delegates to the swarm architecture with

                   PlannerAgent → Domain Agents → SynthesisAgent.



    Returns:

        Dict with: answer, tables_used, executed_sql, masked_fields, data, tool_trace

    """

    # ============================================================================

    # [Phase 6] SWARM GATE — Delegate to Multi-Agent Domain Swarm if enabled

    # ============================================================================
    # [Harness] Track every swarm execution in Redis
    # ============================================================================
    hr = get_harness_runs()
    swarm_run_id = None
    try:
        hr_run = hr.start_run(
            run_id=None,
            query=query,
            user_role=auth_context.role_id,
            swarm_routing="swarm",
            planner_reasoning="",
            complexity_score=0.0,
        )
        swarm_run_id = hr_run.run_id
        if verbose:
            logger.debug(f"\n[HARNESS] Starting swarm run {swarm_run_id}")
    except Exception as e:
        hr_run = None
        swarm_run_id = None
        if verbose:
            logger.debug(f"[HARNESS] Swarm run tracking unavailable: {e}")

    # ============================================================================
    # [Phase 6] SWARM GATE - Delegate to Multi-Agent Domain Swarm if enabled
    # ============================================================================
    if use_swarm:
        from app.agents.swarm import run_swarm
        result = run_swarm(
            query=query,
            auth_context=auth_context,
            domain_hint=domain,
            verbose=verbose,
            run_id=swarm_run_id,
        )
        # Complete harness run with swarm result metadata
        if swarm_run_id and hr_run:
            try:
                hr.complete_run(
                    run_id=swarm_run_id,
                    status="completed" if result.get("status") != "error" else "failed",
                    confidence_score=result.get("confidence_score", {}).get("composite", 0.0) if result.get("confidence_score") else 0.0,
                    execution_time_ms=result.get("execution_time_ms", 0),
                )
            except Exception:
                pass
        return result

    # ============================================================================

    # [Harness] Track every orchestrator execution in Redis

    # ============================================================================

    hr = get_harness_runs()

    try:

        hr_run = hr.start_run(

            run_id=None,

            query=query,

            user_role=auth_context.role_id,

            swarm_routing="monolithic",

            planner_reasoning="",

            complexity_score=0.0,

        )

        current_run_id = hr_run.run_id

        if verbose:

            logger.debug(f"\n[HARNESS] Starting run {current_run_id}")

    except Exception as e:

        hr_run = None

        current_run_id = None

        if verbose:

            logger.warning(f"\n[WARN] Harness tracking unavailable: {e}")





    start_time = time.time()



    def _traj(step, decision, reasoning, metadata=None):

        """Log a trajectory event to the harness run if active."""

        if not current_run_id:

            return

        try:

            hr = get_harness_runs()

            hr.add_trajectory_event(current_run_id, step, decision, reasoning, metadata or {})

        except Exception:

            pass





    from app.core.token_tracker import TokenTracker

    token_tracker = TokenTracker(model_name="claude-3-opus")

    # Mock token usage for orchestrator prompt (varies by query length + schema context)

    token_tracker.add_call(prompt_tokens=450 + len(query)//4, completion_tokens=0)



    # Initialize variables used by sentinel BEFORE sentinel evaluation

    tables_involved: List[str] = []

    temporal_mode: str = "none"



    # [Phase 6] Security Sentinel — Proactive Threat Evaluation

    from app.core.security_sentinel import get_sentinel, ThreatSeverity

    sentinel = get_sentinel()

    session_id = auth_context.role_id + "_" + str(hash(query) % 100000)  # simplified session key

    

    # Run threat evaluation BEFORE query executes

    sentinel_verdict = sentinel.evaluate(

        query=query,

        auth_context=auth_context,

        session_id=session_id,

        tables_accessed=tables_involved,

        domains_accessed=[domain],

        graph_hop_depth=len(tables_involved) if tables_involved else 0,

        row_count=0,  # Will be updated post-execution

        temporal_mode=temporal_mode,

        denied_table_access=False,  # Will be set if sql_validate found denied tables

    )

    if sentinel_verdict.threat_detected:

        sev_label = sentinel_verdict.severity.value.upper()

        logger.info(f"\n[!!] SECURITY SENTINEL [{sev_label}]: {sentinel_verdict.threat_type.value if sentinel_verdict.threat_type else 'unknown'} detected!")

        for ev in sentinel_verdict.evidence[:3]:

            logger.info(f"    Evidence: {ev}")

        if sentinel_verdict.severity in (ThreatSeverity.HIGH, ThreatSeverity.CRITICAL):

            sentinel.alert_security_team(sentinel_verdict, session_id, auth_context.role_id)

        if sentinel_verdict.recommended_action in ("tighten", "block"):

            # Dynamically tighten auth context

            sentinel.apply_tightening_to_auth_context(sentinel_verdict, auth_context)

            logger.info(f"    [!!] AuthContext tightened for role {auth_context.role_id}. Denied tables expanded.")



    tool_trace = []

    graph_scores_data = None

    # Default sql_result for fast-path (meta-path matched) where Pillar 4 is skipped

    sql_result = ToolResult(status=ToolStatus.SUCCESS, message="fast_path", data={"patterns": []}, metadata={})

    top_pattern: Dict[str, Any] = {"intent": "unknown", "tables": []}



    # ========================================================================

    # [Phase 4] SUPERVISOR GATE — Try domain agents first

    # ========================================================================

    if use_supervisor:

        try:

            from app.agents.supervisor_agent import SupervisorAgent

            supervisor = SupervisorAgent()

            decision = supervisor.decide(query, auth_context, domain_hint=domain)

            if decision.decision.value in ("single", "parallel", "cross_module"):

                if verbose:

                    logger.debug(f"\n[SUPERVISOR] Routing to {decision.decision.value.upper()} path")

                    logger.debug(f"  Reasoning: {decision.reasoning}")

                supervisor_result = supervisor.execute(decision, query, auth_context, verbose=verbose)

                # Merge supervisor result into standard result shape

                supervisor_result["tool_trace"] = []  # agents manage their own trace

                supervisor_result["execution_time_ms"] = supervisor_result.get("execution_time_ms",

                                                                                  int((time.time() - start_time) * 1000))

                supervisor_result["memory_logged"] = True

                token_tracker.add_call(prompt_tokens=800, completion_tokens=300)

                supervisor_result["token_tracking"] = token_tracker.get_summary()

                return supervisor_result

            elif verbose:

                logger.info(f"\n[SUPERVISOR] Falling through to standard orchestrator")

                logger.info(f"  Reasoning: {decision.reasoning}")

        except Exception as e:

            if verbose:

                logger.debug(f"\n[SUPERVISOR] Error — falling back to standard orchestrator: {e}")



    def trace(tool: str, result: ToolResult):

        step = {"tool": tool, "status": result.status.value,

                "message": result.message, "metadata": result.metadata}

        tool_trace.append(step)

        if verbose:

            icon = "[OK]" if result.status == ToolStatus.SUCCESS else "[ERROR]" if result.status == ToolStatus.ERROR else "[PARTIAL]"

            logger.debug(f"  {icon} {tool}: {result.message}")



    # =========================================================================

    # PHASE 1: DISPATCH — Which tools does this query need?

    # =========================================================================

    if verbose:

        logger.debug(f"\n[*] Orchestrator starting for: '{query}'")

        logger.debug(f"[*] Role: {auth_context.role_id} | Domain: {domain}")



    # =========================================================================

    # STEP 0: META-PATH MATCH (Fast-path)

    # =========================================================================

    phase_0_start = time.time()

    logger.info("\n[0/5] [Pillar 5] Meta-Path Match — meta_path_match()")

    meta_result = call_tool("meta_path_match", {

        "query": query,

        "domain": domain,

    }, auth_context=auth_context)

    trace("meta_path_match", meta_result)

    meta_path_used = False
    _traj("phase_0_meta_path", "hit" if meta_path_used else "miss", "tables set after meta_path")




    base_sql = ""

    tables_involved: List[str] = []

    temporal_filters: List[str] = []

    temporal_mode: str = "none"





    if meta_result.status == ToolStatus.SUCCESS:

        match_data = meta_result.data["match"]

        logger.info(f"    HIT: '{match_data['name']}' (Score: {match_data['match_score']})")

        base_sql = match_data["sql_template"]

        tables_involved = match_data["tables"]

        meta_path_used = True



        logger.info("    [FAST PATH] Skipping Schema & SQL RAG — using Meta-Path template.")



        if len(tables_involved) >= 2:

            temporal_result = call_tool("temporal_graph_search", {

                "query": query,

                "start_table": tables_involved[0],

                "end_table": tables_involved[-1],

            })

            trace("temporal_graph_search", temporal_result)

            if temporal_result.status == ToolStatus.SUCCESS:

                temporal_filters = temporal_result.data["temporal_filters"]

                temporal_mode = temporal_result.data.get("temporal_mode", "key_date")

                logger.info(f"    [TEMPORAL] Fast-path resolved: {temporal_result.data.get('resolved')} | Mode: {temporal_mode}")

    else:

        logger.info("    MISS: No strong meta-path found. Proceeding to dynamic RAG.")





    if current_run_id:

        _update_harness_phase(

            hr, current_run_id, "phase_0", "completed",

            artifacts={

                "meta_path_used": meta_path_used,

                "tables": tables_involved,

                "sql_template": base_sql[:200] if base_sql else "",

                "match_score": meta_result.data.get("match", {}).get("match_score", 0) if meta_result.status == ToolStatus.SUCCESS else 0,

            },

            duration_ms=int((time.time() - phase_0_start) * 1000),

            verbose=verbose,

        )



    # Only run dynamic steps if we didn't hit a meta-path



    qm_semantic_results: List[Dict[str, Any]] = []

    # STEP 1.75: [Phase 8] QM LONG-TEXT SEMANTIC SEARCH



    # =========================================================================



    # For QM-domain queries: search 20yr of mechanic notes (QMEL-QMTXT) for



    # semantically relevant historical context — failures, defects, warnings.



    # Example: "bearing vibration fatigue" → finds 2009 note: "Bearing B-2047



    # showing fatigue signs — recommend replacement at next planned shutdown."



    qm_intent_keywords = [



        "quality", "qm", "inspection", "nonconformance", "ncr",



        "quality notification", "qm notification", "defect", "reject",



        "quality issue", "qa", "quality assurance", "material defect",



        "quality defect", "complaint", "quality complaint", "qmel",



    ]



    is_qm_query = any(kw in query.lower() for kw in qm_intent_keywords)





    qm_semantic_results: List[Dict[str, Any]] = []



    if is_qm_query:



        logger.info(f"\n[1.75/5] [Phase 8] QM Semantic Search — searching 20yr of mechanic notes")



        try:



            import re as _re_qm



            from app.core.qm_semantic_search import QMSemanticSearch



            qm_search = QMSemanticSearch()





            # Extract equipment ID if present (e.g., "equipment B-2047")



            equip_match = _re_qm.search(r'(?:equipment|equip|machine|asset)\s+(?:ID\s+)?([A-Z0-9-]+)', query, _re_qm.I)



            equipment_filter = equip_match.group(1) if equip_match else None





            qm_results = qm_search.search(



                query=query,



                equipment=equipment_filter,



                year_range=(2005, 2025),



                top_k=5,



            )



            qm_semantic_results = qm_results





            if qm_results:



                logger.info(f"    [QM] Found {len(qm_results)} relevant QM notification chunk(s)")



                top_qm = qm_results[0]



                logger.info(f"    Top match: [{top_qm['year']}] {top_qm['equipment']} — "



                      f"score={top_qm['similarity_score']:.3f}")



                logger.info(f"    Text: {top_qm['text'][:100]}...")



                trace("qm_semantic_search", ToolResult(



                    status=ToolStatus.SUCCESS,



                    message=f"Found {len(qm_results)} QM chunks",



                    data={"results": qm_results, "count": len(qm_results)},



                    metadata={"equipment": equipment_filter},



                ))



            else:



                logger.info(f"    [QM] No QM semantic matches (index may be empty)")



                trace("qm_semantic_search", ToolResult(



                    status=ToolStatus.SUCCESS,



                    message="No QM semantic matches",



                    data={"results": [], "count": 0},



                    metadata={"equipment": equipment_filter},



                ))



        except Exception as e:



            logger.info(f"    [QM] Semantic search error (non-fatal): {e}")



            trace("qm_semantic_search", ToolResult(



                status=ToolStatus.ERROR,



                message=f"QM semantic search failed: {e}",



                data={},



                metadata={},



            ))



    else:



        trace("qm_semantic_search", ToolResult(



            status=ToolStatus.SKIPPED,



            message="Not a QM-domain query",



            data={},



            metadata={},



        ))





    # =========================================================================





    if not meta_path_used:

        # =========================================================================

        # STEP 1: SCHEMA RETRIEVAL (Pillar 3)

        # =========================================================================

        phase_1_start = time.time()

        logger.info("\n[1/5] [Pillar 3] Schema RAG — schema_lookup()")

        schema_result = call_tool("schema_lookup", {

            "query": query,

            "domain": domain,

            "n_results": 4,

        }, auth_context=auth_context)

        trace("schema_lookup", schema_result)

        _traj("phase_1_schema_rag", "success" if schema_result.status.value == "success" else "fail", f"Schema RAG found tables")



        if schema_result.status == ToolStatus.ERROR:

            return {

                "answer": schema_result.message,

                "tables_used": [],

                "executed_sql": None,

                "masked_fields": [],

                "data": [],

                "tool_trace": tool_trace,

                "execution_time_ms": int((time.time() - start_time) * 1000),

            }



        tables_involved = schema_result.data["tables_used"]

        logger.info(f"    Tables found: {tables_involved}")

        if current_run_id:

            _update_harness_phase(hr, current_run_id, "phase_1", "completed",

                artifacts={"tables_found": tables_involved, "domain": domain},

                duration_ms=int((time.time() - phase_1_start) * 1000),

                verbose=verbose)



        # =========================================================================

        # STEP 1b: [Phase 5] SCHEMA AUTO-DISCOVERY (DDIC fallback)

        # =========================================================================

        # Fire when schema RAG finds nothing — last resort before generating SELECT *

        if not tables_involved:

            logger.info("\n[1b/5] [Phase 5] Schema Auto-Discovery — DDIC fallback")

            try:

                ddic_results = schema_auto_discoverer.search(

                    query=query,

                    auth_context=auth_context,

                    domain_hint=domain,

                    top_k=5,

                )

                if ddic_results["tables"]:

                    top_result = ddic_results["tables"][0]

                    tables_involved = [top_result["table"]]

                    logger.info(f"    [DDIC] Discovered: {top_result['table']} "

                          f"({top_result['description']}) "

                          f"confidence={top_result['confidence']}")

                    logger.info(f"    [DDIC] Fields: {', '.join(top_result['fields'][:4])}...")

                    # Build SQL from discovered table

                    base_sql = schema_auto_discoverer.build_select_sql(

                        table_name=top_result["table"],

                        fields=top_result["fields"],

                        auth_context=auth_context,

                    )

                    logger.info(f"    [DDIC] Generated SQL: {base_sql[:80]}...")

                    trace("schema_auto_discover", ToolResult(

                        status=ToolStatus.SUCCESS,

                        message=f"Discovered {len(ddic_results['tables'])} DDIC table(s)",

                        data=ddic_results,

                        metadata={},

                    ))

                else:

                    logger.info("    [DDIC] No tables found in DDIC mirror. Falling back to SELECT *.")

                    tables_involved = ["LFA1"]  # ultimate fallback

            except Exception as e:

                logger.info(f"    [DDIC] Auto-discovery failed: {e}")

                tables_involved = ["LFA1"]



        # =========================================================================

        # STEP 1.5: GRAPH-ENHANCED SCHEMA DISCOVERY (Pillar 5½)

        # =========================================================================

        # Run graph embedding search in parallel with SQL pattern lookup.

        # Even if text-schema finds tables, graph embeddings surface cross-module

        # bridges and structurally central tables that naive text-match would miss.

        phase_1b_start = time.time()

        logger.info("\n[1.5/5] [Pillar 5\u00bd] Graph Embedding Search — graph_enhanced_schema_discovery()")

        graph_result = call_tool("graph_enhanced_schema_discovery", {

            "query": query,

            "domain": domain,

            "top_k": 5,

            "expand_neighbors": 2,

        }, auth_context=auth_context)

        trace("graph_enhanced_schema_discovery", graph_result)



        if graph_result.status == ToolStatus.SUCCESS:

            graph_scores_data = graph_result.data.get("tables", [])

            graph_tables = graph_result.data.get("tables_discovered", [])

            # Merge graph-discovered tables into tables_involved if not already present

            merged_count = 0

            for gt in graph_tables:

                if gt not in tables_involved:

                    tables_involved.append(gt)

                    merged_count += 1

            if merged_count > 0:

                logger.info(f"    [MERGE] Added {merged_count} graph-discovered table(s): "

                      f"{[t for t in graph_tables if t not in schema_result.data['tables_used']]}")



            # Show top structural discovery

            top_graph = graph_result.data["tables"][0]

            logger.info(f"    Top result: {top_graph['table']} [{top_graph['domain']}] "

                  f"role={top_graph['structural_role']} "

                  f"bridge={top_graph['is_cross_module_bridge']} "

                  f"score={top_graph['composite_score']:.3f} "

                  f"(struct={top_graph['structural_score']:.3f}, text={top_graph['text_score']:.3f})")

        else:

            logger.info(f"    [WARN] Graph embedding search returned no results: {graph_result.message}")





        # =========================================================================

        # STEP 2: SQL PATTERN RETRIEVAL (Pillar 4)

        # =========================================================================

        phase_2_start = time.time()

        logger.info("\n[2/5] [Pillar 4] SQL RAG — sql_pattern_lookup()")

        

        # [Phase 4] Memory Layer: pull boosted patterns for this domain

        boosted = sap_memory.get_boosted_patterns(domain=domain, top_k=3)

        if boosted:

            logger.info(f"    [MEMORY] Found {len(boosted)} boosted pattern(s) for '{domain}': "

                  f"{', '.join(p['pattern_name'] for p in boosted[:3])}")

        

        sql_result = call_tool("sql_pattern_lookup", {

            "query": query,

            "domain": domain,

            "n_results": 2,

        }, auth_context=auth_context)

        trace("sql_pattern_lookup", sql_result)



        base_sql = ""

        if sql_result.status == ToolStatus.SUCCESS and sql_result.data.get("patterns"):

            # Use the top-ranked pattern

            top_pattern = sql_result.data["patterns"][0]

            base_sql = top_pattern["sql"]

            logger.info(f"    Pattern: {top_pattern['intent']}")

            logger.info(f"    Tables: {top_pattern['tables']}")

            logger.info(f"    Distance: {top_pattern.get('distance', 0):.3f}")

        elif tables_involved:
            logger.info("    [WARN] No pattern found. Generating SELECT * FROM primary table.")
            base_sql = f"SELECT * FROM {tables_involved[0]} "
        else:
            logger.info("    [WARN] No tables found. Skipping SQL generation.")
            base_sql = ""



        # =========================================================================

        # STEP 2b: TEMPORAL DETECTION (Pillar 5 — Temporal)

        # =========================================================================

        if len(tables_involved) >= 2:

            logger.info(f"\n[2b/5] [Pillar 5] Temporal Detection — checking for date anchors in query")

            temporal_result = call_tool("temporal_graph_search", {

                "query": query,

                "start_table": tables_involved[0],

                "end_table": tables_involved[-1],

            })

            trace("temporal_graph_search", temporal_result)

            if temporal_result.status == ToolStatus.SUCCESS:

                temporal_filters = temporal_result.data["temporal_filters"]

                temporal_mode = temporal_result.data.get("temporal_mode", "key_date")

                logger.info(f"    [TEMPORAL] Resolved: {temporal_result.data.get('resolved')} | Mode: {temporal_mode}")

                logger.info(f"    [TEMPORAL] Filters: {temporal_filters[:4]}")

            else:

                logger.info(f"    [TEMPORAL] No temporal anchor in query — proceeding without temporal filters")



        # =========================================================================

        # STEP 2c: [Phase 7] TEMPORAL ANALYSIS ENGINE

        # =========================================================================

        # Detect: multi-FY queries, supplier performance, CLV, economic cycle analysis

        temporal_analysis_keywords = [

            "fiscal year", "fy", "fy2020", "fy2021", "fy2022", "fy2023", "fy2024", "fy2025",

            "last 3 years", "last 5 years", "last year", "prior year",

            "yearly", "monthly", "quarterly", "trend", "time series",

            "supplier performance", "vendor performance", "delivery reliability",

            "on-time delivery", "quality accept rate", "price competitiveness",

            "customer lifetime value", "clv", "revenue trend", "payment behavior",

            "churn", "return rate", "discount rate",

            "2008 crisis", "covid", "inflation", "supply chain crisis",

            "during the", "during crisis", "post-pandemic",

            "economic cycle", "boom period", "recession",

            "period-over-period", "vs prior year", "vs last year",

        ]

        is_temporal_analysis = any(kw in query.lower() for kw in temporal_analysis_keywords)



        if is_temporal_analysis and len(tables_involved) >= 1:

            logger.info(f"\n[2c/5] [Phase 7] Temporal Analysis Engine — detected temporal analysis query")

            te = TemporalEngine()

            try:

                # Detect which temporal analysis type

                q_lower = query.lower()



                if any(kw in q_lower for kw in ["supplier performance", "vendor performance",

                                                  "delivery reliability", "on-time delivery", "spi"]):

                    # Supplier Performance Index

                    # Extract vendor ID if present

                    vendor_match = re.search(r'(?:vendor|vendors?)\s+(?:ID\s+)?(?:LIFNR[-_]?)?(\w{3,12})', q_lower, re.I)

                    vendor_id = vendor_match.group(1) if vendor_match else "LIFNR-001"

                    spi_result = te.supplier_performance_index(vendor_id, start_fy="last 3 years")

                    temporal_sql = spi_result["delivery_sql"]

                    logger.info(f"    [PHASE 7] Supplier Performance Index for {vendor_id}")

                    temporal_analysis_meta = {"type": "supplier_performance", "vendor_id": vendor_id}



                elif any(kw in q_lower for kw in ["customer lifetime value", "clv", "churn",

                                                    "revenue trend", "payment behavior"]):

                    # Customer Lifetime Value

                    customer_match = re.search(r'(?:customer|KUNNR[-_]?)(\w{3,12})', q_lower, re.I)

                    customer_id = customer_match.group(1) if customer_match else "KUNNR-10000142"

                    clv_result = te.customer_lifetime_value(customer_id, years_back=20)

                    temporal_sql = clv_result["revenue_sql"]

                    logger.info(f"    [PHASE 7] Customer Lifetime Value for {customer_id}")

                    temporal_analysis_meta = {"type": "clv", "customer_id": customer_id}



                elif any(kw in q_lower for kw in ["economic cycle", "2008", "covid", "inflation",

                                                     "during crisis", "boom period", "recession"]):

                    # Economic Cycle Analysis

                    econ_result = te.economic_cycle_analysis(

                        date_range=(date(2008, 1, 1), date.today()),

                        entity_column=tables_involved[0][:3] + "NR" if tables_involved else "LIFNR",

                        value_column="NETWR" if tables_involved[0] in ["EKKO", "VBAK"] else "MENGE",

                        table=tables_involved[0],

                        date_column="AEDAT" if tables_involved[0] in ["EKKO", "VBAK"] else "BUDAT",

                    )

                    temporal_sql = econ_result["events"][0]["comparison_sql"] if econ_result["events"] else base_sql

                    logger.info(f"    [PHASE 7] Economic Cycle Analysis — {econ_result['events_found']} event(s) found")

                    temporal_analysis_meta = {"type": "economic_cycle", "events_found": econ_result['events_found']}



                elif any(kw in q_lower for kw in ["fy202", "fy201", "fiscal year", "last 3 years",

                                                     "last 5 years", "last year", "prior year",

                                                     "year-over-year", "yearly", "quarterly", "monthly"]):

                    # Fiscal Year Analysis

                    from datetime import date

                    # Detect FY range from query

                    fy_match = re.search(r'FY(20\d{2})\s*[-–]\s*FY(20\d{2})', q_lower)

                    if fy_match:

                        fy_expr = f"FY{fy_match.group(1)}-FY{fy_match.group(2)}"

                    elif "last 3 years" in q_lower:

                        fy_expr = "last 3 years"

                    elif "last 5 years" in q_lower:

                        fy_expr = "last 5 years"

                    else:

                        fy_expr = "last 3 years"



                    # Detect granularity

                    granularity = "monthly"

                    if any(k in q_lower for k in ["yearly", "year-over-year", "annually"]):

                        granularity = "yearly"

                    elif any(k in q_lower for k in ["quarterly", "quarter", "QoQ"]):

                        granularity = "quarterly"



                    fy_analysis = te.fiscal_year_analysis(

                        query=query,

                        tables=tables_involved,

                        date_column="AEDAT" if tables_involved[0] in ["EKKO", "VBAK"] else "BUDAT",

                        value_column="NETWR" if tables_involved[0] in ["EKKO", "VBAK"] else "MENGE",

                        entity_column=tables_involved[0][:3] + "NR" if tables_involved else "LIFNR",

                        fy_expression=fy_expr,

                        granularity=granularity,

                    )

                    temporal_sql = fy_analysis["aggregation_sql"]

                    logger.info(f"    [PHASE 7] FY Analysis: {fy_analysis['fy_range']['label']} @ {granularity}")

                    temporal_analysis_meta = {"type": "fiscal_year", "fy_range": fy_analysis['fy_range'], "granularity": granularity}



                else:

                    # Generic temporal — default FY analysis

                    from datetime import date

                    fy_analysis = te.fiscal_year_analysis(

                        query=query,

                        tables=tables_involved,

                        date_column="AEDAT" if tables_involved[0] in ["EKKO", "VBAK"] else "BUDAT",

                        value_column="NETWR" if tables_involved[0] in ["EKKO", "VBAK"] else "MENGE",

                        entity_column=tables_involved[0][:3] + "NR" if tables_involved else "LIFNR",

                        fy_expression="last 3 years",

                        granularity="monthly",

                    )

                    temporal_sql = fy_analysis["aggregation_sql"]

                    temporal_analysis_meta = {"type": "fiscal_year", "fy_range": fy_analysis['fy_range']}

                    logger.info(f"    [PHASE 7] Generic FY Analysis: {fy_analysis['fy_range']['label']}")



                # Override base_sql with temporal SQL if we generated one

                if temporal_sql:

                    base_sql = temporal_sql

                    if verbose:

                        logger.debug(f"    [PHASE 7] Temporal SQL: {temporal_sql[:120]}...")

                    trace("temporal_analysis_engine", ToolResult(

                        status=ToolStatus.SUCCESS,

                        message=f"Temporal analysis: {temporal_analysis_meta.get('type', 'unknown')}",

                        data={"temporal_analysis_meta": temporal_analysis_meta, "sql": temporal_sql},

                        metadata={},

                    ))



            except Exception as e:

                logger.info(f"    [PHASE 7] Temporal engine error: {e}")

                trace("temporal_analysis_engine", ToolResult(

                    status=ToolStatus.ERROR,

                    message=f"Temporal engine error: {e}",

                    data={},

                    metadata={},

                ))

        else:

            temporal_analysis_meta = {"type": "none"}





        # =========================================================================

        # STEP 2d: [Phase 8] NEGOTIATION BRIEFING GENERATOR

        # =========================================================================

        # When negotiation intent is detected: synthesize a structured negotiation

        # brief from 20yr of SAP data — CLV, PSI, churn risk, BATNA, tactics.

        # Fires on: "negotiate", "contract renewal", "price increase",

        # "supplier review", "customer review", "vendor briefing"

        negotiation_keywords = [

            "negotiate", "negotiation", "contract renewal", "price increase",

            "supplier review", "vendor review", "customer review",

            "negotiation brief", "briefing", "clv", "customer lifetime",

            "supplier performance", "vendor performance", "price sensitivity",

            "batna", "churn risk", "vendor scorecard", "supplier scorecard",

            "contract", "renewal", "pricing power", "leverage",

        ]

        is_negotiation_query = any(kw in query.lower() for kw in negotiation_keywords)



        negotiation_brief: Optional[Dict[str, Any]] = None

        if is_negotiation_query:

            logger.info(f"\n[2d/5] [Phase 8] Negotiation Briefing Generator — synthesizing 20yr brief")

            try:

                import re as _re_nego

                from app.core.negotiation_briefing import (

                    NegotiationBriefingGenerator, NegotiationBriefFormatter,

                    EntityType, NegotiationType,

                )

                gen = NegotiationBriefingGenerator()

                fmt = NegotiationBriefFormatter()



                # Extract entity ID and type from query

                customer_match = _re_nego.search(r'(?:customer|KUNNR|KUN?)[-_]?(\w{3,12})', query, _re_nego.I)

                vendor_match = _re_nego.search(r'(?:vendor|LIFNR|VEND?)[-_]?(\w{3,12})', query, _re_nego.I)

                entity_id = (customer_match or vendor_match or type('', (), {'group': lambda s: 'KUNNR-10000142'})()).group()

                entity_type = EntityType.CUSTOMER if customer_match else EntityType.VENDOR

                entity_name = entity_id  # SAP name lookup deferred to real connection



                # Determine negotiation type

                q_lower = query.lower()

                if any(k in q_lower for k in ["price increase", "pricing"]):

                    neg_type = NegotiationType.PRICE_INCREASE

                elif any(k in q_lower for k in ["contract renewal", "renewal"]):

                    neg_type = NegotiationType.CONTRACT_RENEWAL

                elif any(k in q_lower for k in ["volume"]):

                    neg_type = NegotiationType.VOLUME_REVISION

                elif any(k in q_lower for k in ["terms", "payment terms", "terms revision"]):

                    neg_type = NegotiationType.TERMS_REVISION

                else:

                    neg_type = NegotiationType.CONTRACT_RENEWAL



                # Build mock data dicts (replace with real SAP queries in production)

                mock_rel = {

                    "relationship": [

                        {"ORDER_YEAR": yr, "ANNUAL_REVENUE": 100000 + yr * 5000,

                         "ORDER_COUNT": 12, "AVG_ORDER_VALUE": 9000, "DISCOUNT_PCT": 3.5,

                         "ACTIVE_MONTHS": 10, "RETURN_RATE": 1.0}

                        for yr in range(2020, 2025)

                    ],

                    "payment": [

                        {"PAYMENT_YEAR": yr, "AVG_DAYS_TO_PAY": 40, "PAYMENT_SCORE": 80}

                        for yr in range(2020, 2025)

                    ],

                }

                mock_pi = [

                    {"PRICING_YEAR": 2021, "AVG_PRICE_INCREASE_PCT": 3.5},

                    {"PRICING_YEAR": 2022, "AVG_PRICE_INCREASE_PCT": 5.0},

                    {"PRICING_YEAR": 2024, "AVG_PRICE_INCREASE_PCT": 4.0},

                ]



                brief = gen.generate(

                    entity_id=entity_id,

                    entity_name=entity_name,

                    entity_type=entity_type,

                    negotiation_type=neg_type,

                    relationship_data=mock_rel,

                    price_increase_data=mock_pi,

                    payment_data=mock_rel["payment"],

                )



                negotiation_brief = fmt.format_structured(brief)

                brief_text = fmt.format_text(brief)



                logger.info(f"    [BRIEF] Entity: {brief.entity_name} ({brief.entity_type.value})")

                logger.info(f"    [BRIEF] CLV Tier: {brief.clv_tier} | PSI: {brief.price_sensitivity_index}/10")

                logger.info(f"    [BRIEF] Churn Risk: {brief.churn_risk} | BATNA Strength: {brief.batna_strength:.0f}/10")

                logger.info(f"    [BRIEF] Target: +{brief.recommended_increase_pct:.1f}% increase | "

                      f"Accept min: +{brief.max_acceptable_increase_pct:.1f}%")

                logger.info(f"    [BRIEF] Top tactic: {brief.top_tactics[0][:80]}")



                trace("negotiation_briefing", ToolResult(

                    status=ToolStatus.SUCCESS,

                    message=f"Negotiation brief: {brief.entity_name} ({brief.clv_tier} CLV)",

                    data={"brief": negotiation_brief, "brief_text": brief_text},

                    metadata={"entity_id": entity_id, "entity_type": entity_type.value,

                              "neg_type": neg_type.value, "clv_tier": brief.clv_tier,

                              "psi": brief.price_sensitivity_index},

                ))

            except Exception as e:

                logger.info(f"    [BRIEF] Error generating negotiation brief: {e}")

                trace("negotiation_briefing", ToolResult(

                    status=ToolStatus.ERROR,

                    message=f"Negotiation brief error: {e}",

                    data={},

                    metadata={},

                ))

        else:

            trace("negotiation_briefing", ToolResult(

                status=ToolStatus.SKIPPED,

                message="Not a negotiation query",

                data={},

                metadata={},

            ))



        # =========================================================================

        # STEP 3: GRAPH TRAVERSAL (Pillar 5) — if multi-table

        # =========================================================================

        join_clause = ""

        if sql_result.status != ToolStatus.SUCCESS or not sql_result.data.get("patterns"):

            # Only use Graph RAG when we have no pattern — build JOIN from scratch

            if len(tables_involved) > 1:

                phase_3_start = time.time()

                logger.info(f"\n[3/5] [Pillar 5] Graph RAG — all_paths_explore({tables_involved[0]}, {tables_involved[1]}) [FALLBACK]")

                graph_result = call_tool("all_paths_explore", {

                    "start_table": tables_involved[0],

                    "end_table": tables_involved[1],

                    "max_depth": 5,

                    "top_k": 3

                })

                trace("all_paths_explore", graph_result)

                if graph_result.status == ToolStatus.SUCCESS:

                    join_clause = graph_result.data["best_join_clause"]

                    base_sql += f"\n{join_clause}"

                    logger.info(f"    JOIN path chosen: {' → '.join(graph_result.data['best_path_tables'])}")

                else:

                    logger.info(f"    [WARN] {graph_result.message}")

                if current_run_id:

                    _update_harness_phase(hr, current_run_id, "phase_3", "completed",

                        artifacts={

                            "tables": tables_involved,

                            "join_clause": join_clause[:200] if join_clause else "",

                        },

                        duration_ms=int((time.time() - phase_3_start) * 1000),

                        verbose=verbose)

            else:

                logger.info("\n[3/5] [Pillar 5] Graph RAG — Skipped (single table, no traversal needed)")

        else:

            logger.info("\n[3/5] [Pillar 5] Graph RAG — Skipped (pattern found, JOIN already in SQL)")



    # =========================================================================

    # STEP 4: SQL ASSEMBLY + AUTHCONTEXT INJECTION

    # =========================================================================

    phase_4_start = time.time()

    logger.info("\n[4/5] [Pillar 1] SQL Assembly + AuthContext Injection")



    # Build WHERE clauses from AuthContext

    where_clauses = ["MANDT = '100'"]



    if any(t in tables_involved for t in ["LFB1", "BSIK", "BSAK"]):

        if auth_context.allowed_company_codes and "*" not in auth_context.allowed_company_codes:

            b = "', '".join(auth_context.allowed_company_codes)

            where_clauses.append(f"BUKRS IN ('{b}')")



    # Inject temporal validity filters (key-date / fiscal period / FY)

    if temporal_filters:

        for tf in temporal_filters:

            if tf not in where_clauses:

                where_clauses.append(tf)

        logger.info(f"    [TEMPORAL] Applied {len(temporal_filters)} filter(s): {temporal_mode}")



    if any(t in tables_involved for t in ["EKKO", "EKPO", "EINA", "EINE"]):

        if auth_context.allowed_purchasing_orgs and "*" not in auth_context.allowed_purchasing_orgs:

            e = "', '".join(auth_context.allowed_purchasing_orgs)

            where_clauses.append(f"EKORG IN ('{e}')")



    if any(t in tables_involved for t in ["MARC", "MARD", "MBEW"]):

        if auth_context.allowed_plants and "*" not in auth_context.allowed_plants:

            w = "', '".join(auth_context.allowed_plants)

            where_clauses.append(f"WERKS IN ('{w}')")



    # Inject AuthContext WHERE clauses into the pattern SQL

    # Replace {MANDT} placeholder and append org-level filters

    generated_sql = base_sql



    # Replace {MANDT} placeholder

    generated_sql = generated_sql.replace("{MANDT}", "'100'")



    # Replace {vendor_id} placeholder with a safe wildcard (will be overridden by LLM in real use)

    # In scaffold mode, we use '%' to match all or add a specific filter

    if "{vendor_id}" in generated_sql:

        generated_sql = generated_sql.replace("{vendor_id}", "'1000'")



    # Replace any other common placeholders with safe defaults

    generated_sql = generated_sql.replace("{max_rows}", "1000")

    generated_sql = generated_sql.replace("{start_date}", "'20250101'")

    generated_sql = generated_sql.replace("{end_date}", "'20251231'")

    generated_sql = generated_sql.replace("{plant_id}", "'1000'")

    generated_sql = generated_sql.replace("{company_code}", "'1000'")

    generated_sql = generated_sql.replace("{purchasing_org}", "'1000'")

    generated_sql = generated_sql.replace("{allowed_bukrs}", "'1000', '1010'")

    generated_sql = generated_sql.replace("{allowed_ekorgs}", "'1000'")

    generated_sql = generated_sql.replace("{country_code}", "'US'")

    generated_sql = generated_sql.replace("{region_code}", "'CA'")

    generated_sql = generated_sql.replace("{sales_district}", "'SD01'")

    generated_sql = generated_sql.replace("{material_id}", "'RM-100'")

    generated_sql = generated_sql.replace("{valuation_area}", "'1000'")

    generated_sql = generated_sql.replace("{inspection_lot}", "'QL000001'")

    generated_sql = generated_sql.replace("{notification_number}", "'QM000001'")

    generated_sql = generated_sql.replace("{network_number}", "'PN000001'")

    generated_sql = generated_sql.replace("{project_definition}", "'PRJ001'")

    generated_sql = generated_sql.replace("{wbs_element}", "'WBS001'")

    generated_sql = generated_sql.replace("{contract_number}", "'CTR001'")

    generated_sql = generated_sql.replace("{sales_order}", "'SO000001'")

    generated_sql = generated_sql.replace("{customer_id}", "'CU001'")

    generated_sql = generated_sql.replace("{partner_id}", "'BP001'")

    generated_sql = generated_sql.replace("{equipment_number}", "'EQ001'")

    generated_sql = generated_sql.replace("{functional_location}", "'FL001'")

    generated_sql = generated_sql.replace("{contract_number}", "'CR001'")

    generated_sql = generated_sql.replace("{handling_unit}", "'HU001'")

    generated_sql = generated_sql.replace("{transfer_order}", "'TO001'")

    generated_sql = generated_sql.replace("{shipment_number}", "'SH001'")

    generated_sql = generated_sql.replace("{delivery_document}", "'DL001'")

    generated_sql = generated_sql.replace("{carrier_id}", "'CA001'")

    generated_sql = generated_sql.replace("{device_number}", "'MT001'")

    generated_sql = generated_sql.replace("{installation_id}", "'IN001'")

    generated_sql = generated_sql.replace("{connection_object}", "'CO001'")

    generated_sql = generated_sql.replace("{patient_number}", "'PAT001'")

    generated_sql = generated_sql.replace("{case_number}", "'CS001'")

    generated_sql = generated_sql.replace("{org_unit_id}", "'OU001'")

    generated_sql = generated_sql.replace("{tank_number}", "'TK001'")

    generated_sql = generated_sql.replace("{jv_code}", "'JV001'")

    generated_sql = generated_sql.replace("{assortment_id}", "'AS001'")

    generated_sql = generated_sql.replace("{article_number}", "'AR001'")

    generated_sql = generated_sql.replace("{site_number}", "'SI001'")

    generated_sql = generated_sql.replace("{incident_uuid}", "'INC001'")

    generated_sql = generated_sql.replace("{substance_uuid}", "'SUB001'")

    generated_sql = generated_sql.replace("{configuration_object}", "'CFG001'")

    generated_sql = generated_sql.replace("{bom_number}", "'BOM001'")

    generated_sql = generated_sql.replace("{rent_document}", "'RD001'")

    generated_sql = generated_sql.replace("{customs_entry_number}", "'CE001'")

    generated_sql = generated_sql.replace("{ewaybill_number}", "'EWB001'")

    generated_sql = generated_sql.replace("{hsn_code}", "'1234'")

    generated_sql = generated_sql.replace("{tax_code}", "'TX001'")



    # Clean up comment artifacts from patterns

    generated_sql = generated_sql.replace("-- Exclude deleted POs\n  AND ekko.LOEKZ = ''  -- Exclude deleted POs\n  AND ekpo.LOEKZ = ''  -- Exclude deleted lines\n  AND ekpo.ELIKZ = ''  -- Delivery not completed", "")

    generated_sql = generated_sql.replace("  {vendor_filter} -- e.g. AND bsik.LIFNR = '1000'", "")

    generated_sql = generated_sql.replace("{vendor_filter}", "")



    # Remove any remaining unresolved placeholders (fallback)

    import re

    generated_sql = re.sub(r"\{[^}]+\}", "'UNKNOWN'", generated_sql)



    # Strip excess whitespace

    lines = [l.strip() for l in generated_sql.split("\n") if l.strip()]

    generated_sql = "\n".join(lines)



    if verbose:

        logger.debug(f"    Generated SQL: {generated_sql[:100]}...")



    # =========================================================================

    # STEP 4.5: SELF-CRITIQUE LOOP (Phase 4 — Gatekeeper)

    # =========================================================================

        logger.info("\n[4.5/5] [Phase 4] Self-Critique — critique_agent.critique()")

    

    # Initialize heal_info upfront (may be updated by self-healer during critique or validation)

    heal_info: Dict[str, Any] = {"applied": False, "code": None, "reason": None}

    

    # Retrieve schema context for the involved tables (needed for JOIN key validation)

    schema_context = []

    for tbl in tables_involved:

        schema_context.append({"table": tbl})

    

    critique_result = critique_agent.critique(

        query=query,

        sql=generated_sql,

        schema_context=schema_context,

        auth_context={

            "role_id": auth_context.role_id,

            "filters": auth_context.get_where_clauses() if hasattr(auth_context, "get_where_clauses") else {},

            "allowed_company_codes": auth_context.allowed_company_codes,

            "allowed_plants": auth_context.allowed_plants,

            "allowed_purchasing_orgs": auth_context.allowed_purchasing_orgs,

        }

    )

    

    trace("critique_agent", ToolResult(

        status=ToolStatus.SUCCESS if critique_result["passed"] else ToolStatus.ERROR,

        message=f"Score: {critique_result['score']} — {'PASS' if critique_result['passed'] else 'FAIL'}",

        data=critique_result,

        metadata={},

    ))

    

    if not critique_result["passed"]:

        logger.info(f"    [!!] Critique FAILED (score={critique_result['score']})")

        for issue in critique_result["issues"]:

            logger.info(f"        • {issue}")

        logger.info("    [!!] Attempting self-heal...")

        # Use self-healer to auto-correct based on detected issues

        combined_error = "; ".join(critique_result["issues"])

        corrected_sql, heal_reason, heal_code = self_healer.heal(

            sql=generated_sql,

            error=combined_error,

            schema_context=schema_context,

        )

        heal_info = {"applied": bool(heal_code), "code": heal_code, "reason": heal_reason}

        if heal_code and corrected_sql != generated_sql:

            logger.info(f"    [OK] Self-healed ({heal_code}): {heal_reason}")

            generated_sql = corrected_sql

            # Re-score after healing

            re_critique = critique_agent.critique(

                query=query,

                sql=corrected_sql,

                schema_context=schema_context,

                auth_context={

                    "role_id": auth_context.role_id,

                    "filters": auth_context.get_where_clauses() if hasattr(auth_context, "get_where_clauses") else {},

                    "allowed_company_codes": auth_context.allowed_company_codes,

                    "allowed_plants": auth_context.allowed_plants,

                    "allowed_purchasing_orgs": auth_context.allowed_purchasing_orgs,

                },

            )

            if re_critique["passed"]:

                logger.info(f"    [OK] Healed SQL passed re-score ({re_critique['score']})")

                critique_result = re_critique

            else:

                logger.info(f"    [WARN] Healed SQL still failing. Proceeding with warning.")

                logger.info(f"    [WARN] Remaining issues: {re_critique['issues']}")

        else:

            logger.info(f"    [WARN] No self-heal rule matched: {heal_reason}")

            heal_info = {"applied": False, "code": None, "reason": heal_reason}

    else:

        logger.info(f"    [OK] Critique PASSED (score={critique_result['score']})")

    

    # Track if self-healing was applied (for result metadata)

    heal_info: Dict[str, Any] = {"applied": False, "code": None, "reason": None}



    # =========================================================================

    # STEP 5: SQL VALIDATION (Security Check)

    # =========================================================================

    phase_5_start = time.time()

    logger.info("\n[5/5] [Security] sql_validate()")

    validate_result = call_tool("sql_validate", {

        "sql": generated_sql,

        "strict": False,

    }, auth_context=auth_context)

    trace("sql_validate", validate_result)



    if validate_result.status == ToolStatus.ERROR:

        # Attempt self-heal on validation error

        validation_error = validate_result.message or "SQL validation failed"

        healed_sql, heal_reason, heal_code = self_healer.heal(

            sql=generated_sql,

            error=validation_error,

            schema_context=schema_context,

        )

        if heal_code and healed_sql != generated_sql:

            logger.info(f"    [!!] Validation failed — self-healed ({heal_code}): {heal_reason}")

            logger.info(f"    [OK] Retrying with healed SQL...")

            generated_sql = healed_sql

            validate_result = call_tool("sql_validate", {

                "sql": generated_sql,

                "strict": False,

            }, auth_context=auth_context)

            trace("sql_validate(retry)", validate_result)

            if validate_result.status == ToolStatus.ERROR:

                validation_error = validate_result.message

        

        if validate_result.status == ToolStatus.ERROR:

            return {

                "answer": f"SQL validation failed (self-heal attempted): {validation_error}",

                "tables_used": tables_involved,

                "executed_sql": generated_sql,

                "masked_fields": [],

                "data": [],

                "validation_errors": validate_result.data.get("errors", []),

                "tool_trace": tool_trace,

                "execution_time_ms": int((time.time() - start_time) * 1000),

                "self_heal": {"applied": True, "code": heal_code, "reason": heal_reason},

            }



    if validate_result.data.get("suggestions"):

        logger.info(f"    AuthContext suggestions: {validate_result.data['suggestions']}")



    # =========================================================================

    # STEP 5.5: DRY-RUN VALIDATION HARNESS (Phase 6)

    # =========================================================================

    phase_5b_start = time.time()

    logger.info("\n[5.5/5] [Phase 6] Validation Harness — SELECT COUNT(*) Dry-Run")

    validation_sql = f"SELECT COUNT(*) FROM (\n{generated_sql}\n) AS dry_run_sub"

    val_exec_result = call_tool("sql_execute", {

        "sql": validation_sql,

        "dry_run": True,

        "max_rows": 1,

    }, auth_context=auth_context)

    trace("sql_execute(dry_run)", val_exec_result)



    if val_exec_result.status == ToolStatus.ERROR:

        val_error = val_exec_result.message or "SQL validation execution failed"

        logger.info(f"    [!!] Dry-Run Validation failed: {val_error[:60]}")

        logger.info(f"    [!!] Attempting autonomous self-heal...")

        healed_sql, heal_reason, heal_code = self_healer.heal(

            sql=generated_sql,

            error=val_error,

            schema_context=schema_context,

        )

        heal_info = {"applied": bool(heal_code), "code": heal_code, "reason": heal_reason}

        if heal_code and healed_sql != generated_sql:

            logger.info(f"    [OK] Self-healed ({heal_code}): {heal_reason}")

            generated_sql = healed_sql

            # Re-test the healed SQL

            validation_sql = f"SELECT COUNT(*) FROM (\n{generated_sql}\n) AS dry_run_sub"

            reval_exec_result = call_tool("sql_execute", {

                "sql": validation_sql,

                "dry_run": True,

                "max_rows": 1,

            }, auth_context=auth_context)

            trace("sql_execute(dry_run_retry)", reval_exec_result)

            if reval_exec_result.status == ToolStatus.SUCCESS:

                logger.info(f"    [OK] Healed SQL passed the Validation Harness!")

            else:

                logger.info(f"    [WARN] Healed SQL still failing validation dry-run.")

        else:

            logger.info(f"    [WARN] No autonomous heal possible: {heal_reason}")



    # =========================================================================
    # [Phase 14] VOTING EXECUTOR - 3-path consensus for low-confidence or critical queries
    # Laurie Voss pattern: 3 LLMs seldom hallucinate to the same wrong answer
    # Trigger: composite confidence < 0.70 OR compliance_critical domain
    # =========================================================================
    phase_voting_start = time.time()

    _current_confidence = _compute_confidence_score(
        critique_score=critique_result["score"],
        data_records=[],
        meta_path_used=meta_path_used,
        self_heal_applied=heal_info.get("applied", False) if "heal_info" in dir() else False,
        temporal_mode=temporal_mode,
        tables_involved=tables_involved,
        execution_time_ms=0,
    ).get("composite", 0.80)

    _compliance_critical = domain.lower() in {
        "finance", "tax", "treasury", "compliance",
        "vendor_payment", "customer_credit", "pricing"
    }

    if _current_confidence < 0.70 or _compliance_critical:
        logger.info("\n[15/5] [Phase 14] VOTING EXECUTOR triggered (confidence={:.3f}, critical={})".format(_current_confidence, _compliance_critical))

        from app.core.voting_executor import run_voting_sql_generation
        vote_result = run_voting_sql_generation(
            query=query,
            auth_context=auth_context,
            domain=domain,
            tables_involved=tables_involved,
            confidence_before_vote=_current_confidence,
            compliance_critical=_compliance_critical,
        )

        logger.info("    [VOTE] outcome={} winning={} delta={:.3f} table_vote={} escalation={}".format(
            vote_result.vote_outcome,
            vote_result.winning_path,
            vote_result.confidence_after_vote - vote_result.confidence_before_vote,
            vote_result.table_vote,
            vote_result.escalation_required,
        ))

        if vote_result.consensus_sql:
            logger.info("    [VOTE] Consensus found: {} (confidence {:.3f} -> {:.3f})".format(vote_result.winning_path, _current_confidence, vote_result.confidence_after_vote))
            generated_sql = vote_result.consensus_sql
        elif vote_result.escalation_required:
            logger.warning("    [VOTE-ESCALATE] Disagreement across paths - manual review required")
            result_dict["_voting_escalation"] = {
                "required": True,
                "alert": vote_result.disagreement_alert,
                "votes": [{"path": v.path_name, "sql": v.sql[:80], "status": v.status} for v in vote_result.votes],
            }
        voting_time_ms = int((time.time() - phase_voting_start) * 1000)
        logger.info("    [VOTE] Voting completed in {}ms".format(voting_time_ms))
    else:
        vote_result = None
        logger.info("\n[--] [Phase 14] VOTING EXECUTOR skipped - confidence={:.3f} >= 0.70, non-critical".format(_current_confidence))

    # =========================================================================
    # STEP 6: EXECUTION
    # =========================================================================
    phase_exec_start = time.time()

    logger.info("\n[*] Executing Final SQL against SAP HANA (mock)...")

    exec_result = call_tool("sql_execute", {

        "sql": generated_sql,

        "dry_run": True,

        "max_rows": 1000,

    }, auth_context=auth_context)

    trace("sql_execute", exec_result)

    

    # [Phase 6] Autonomous Recovery — attempt self-heal on execution errors

    if exec_result.status == ToolStatus.ERROR:

        exec_error = exec_result.message or "SQL execution failed"

        logger.info(f"    [!!] Execution failed: {exec_error[:60]}")

        logger.info(f"    [!!] Attempting autonomous self-heal...")

        healed_sql, heal_reason, heal_code = self_healer.heal(

            sql=generated_sql,

            error=exec_error,

            schema_context=schema_context,

        )

        heal_info = {"applied": bool(heal_code), "code": heal_code, "reason": heal_reason}

        if heal_code and healed_sql != generated_sql:

            logger.info(f"    [OK] Self-healed ({heal_code}): {heal_reason}")

            generated_sql = healed_sql

            # Re-validate and retry execution

            revalidate = call_tool("sql_validate", {"sql": generated_sql, "strict": False}, auth_context=auth_context)

            if revalidate.status == ToolStatus.SUCCESS:

                logger.info(f"    [OK] Retrying execution with healed SQL...")

                exec_result = call_tool("sql_execute", {"sql": generated_sql, "dry_run": True, "max_rows": 1000}, auth_context=auth_context)

                trace("sql_execute(retry)", exec_result)

        else:

            logger.info(f"    [WARN] No autonomous heal possible: {heal_reason}")



    # =========================================================================

    # STEP 7: MASKING (Pillar 1 — Post-Execution)

    # =========================================================================

    masked_fields = []

    data_records = []



    if exec_result.status == ToolStatus.SUCCESS and exec_result.data.get("rows"):

        data_records = exec_result.data["rows"]

        masked_fields = exec_result.data.get("masked_fields", [])



        if masked_fields:

            logger.info(f"    [Pillar 1] Masked fields: {masked_fields}")



    # =========================================================================

    # STEP 8: SYNTHESIS

    # =========================================================================

    execution_time = int((time.time() - start_time) * 1000)



    if not data_records:

        final_answer = (

            f"I could not find any records for your query '{query}' "

            f"in the {domain} domain. "

            f"Tables searched: {', '.join(tables_involved)}."

        )

    else:

        final_answer = (

            f"Found {len(data_records)} record(s) from the SAP system. "

            f"Tables used: {', '.join(tables_involved)}. "

            f"Showing authorized data only."

        )

        if masked_fields:

            final_answer += f" Some fields masked per your role ({auth_context.role_id})."



    logger.info(f"\n[DONE] {final_answer}")

    logger.info(f"    Execution time: {execution_time}ms")

    logger.info(f"    Tools called: {len(tool_trace)}")



    # Add mock completion tokens based on final answer + SQL generated

    token_tracker.add_call(prompt_tokens=0, completion_tokens=120 + len(final_answer)//4 + len(generated_sql)//4)



    result_dict = {

        "answer": final_answer,

        "tables_used": tables_involved,

        "executed_sql": generated_sql.strip(),

        "masked_fields": masked_fields,

        "data": data_records,

        "tool_trace": tool_trace,

        "token_tracking": token_tracker.get_summary(),

        "execution_time_ms": execution_time,

        "temporal": {

            "mode": temporal_mode,

            "filters": temporal_filters,

            "phase7_analysis": temporal_analysis_meta if 'temporal_analysis_meta' in dir() else {"type": "none"},

        },

        "critique": {

            "score": critique_result["score"],

            "passed": critique_result["passed"],

            "issues": critique_result["issues"],

            "suggestions": critique_result["suggestions"],

        },

        "memory": {

            "logged": True,

        },

        "self_heal": heal_info if 'heal_info' in locals() else {"applied": False},

        # [Phase 6] Proactive Threat Sentinel verdict — surfaced in API response

        "sentinel": {

            "threat_detected": sentinel_verdict.threat_detected,

            "threat_type": sentinel_verdict.threat_type.value if sentinel_verdict.threat_type else None,

            "severity": sentinel_verdict.severity.value if sentinel_verdict.severity else None,

            "confidence": round(sentinel_verdict.confidence, 3),

            "evidence": sentinel_verdict.evidence[:4],

            "session_flags": sentinel_verdict.session_flags,

            "tightness_level": get_sentinel().get_session_profile(session_id).tightness_level if sentinel_verdict.threat_detected else 0,

        } if 'sentinel_verdict' in dir() and sentinel_verdict.threat_detected else {"threat_detected": False},

        "graph_scores": graph_scores_data,

        "qm_semantic": {

            "count": len(qm_semantic_results) if 'qm_semantic_results' in dir() else 0,

            "results": qm_semantic_results if 'qm_semantic_results' in dir() else [],

        },

        "negotiation_brief": negotiation_brief if 'negotiation_brief' in dir() else None,

        "confidence_score": _compute_confidence_score(

            critique_score=critique_result["score"],

            data_records=data_records,

            meta_path_used=meta_path_used,

            self_heal_applied=heal_info.get("applied", False) if 'heal_info' in dir() else False,

            temporal_mode=temporal_mode,

            tables_involved=tables_involved,

            execution_time_ms=execution_time,

        ),

        "routing_path": (

            "fast_path"

            if meta_path_used

            else "cross_module"

            if len(tables_involved) > 2

            else "standard"

        ),

        "pattern_name": (

            top_pattern.get("intent", "ad_hoc")

            if sql_result.status == ToolStatus.SUCCESS and sql_result.data.get("patterns")

            else "ad_hoc"

        ),

        "sentinel_stats": get_sentinel().get_threat_stats() if 'get_sentinel' in dir() else {},

        "run_id": current_run_id or "",

        # [Phase 6] Swarm routing metadata

        "swarm_routing": "monolithic" if not use_swarm else "swarm_delegated",

    }

    

    # ========================================================================

    # [Phase 4] STEP 8b: PERSISTENT MEMORY LOGGING & COMPOUNDING

    # ========================================================================

    if exec_result.status == ToolStatus.SUCCESS and data_records:

        result_status = "success"

        pattern_name = top_pattern.get("intent", "unknown") if sql_result.status == ToolStatus.SUCCESS and sql_result.data.get("patterns") else "ad_hoc"

        

        sap_memory.log_pattern_success(

            domain=domain,

            pattern_name=pattern_name,

            sql=generated_sql,

            tables=tables_involved,

        )



        # [Harness Engineering] Automated Qdrant Vectorization

        # If this was self-healed, we inject the fixed pattern back into the Qdrant store

        if heal_info.get("applied", False):

            logger.info(f"\n    [MEMORY COMPOUNDING] Vectorizing newly-healed pattern to Qdrant: {pattern_name}")

            try:

                from app.core.vector_store import store_manager

                # Generate an intent string to encode for the search index

                new_intent = f"{pattern_name} (Auto-Healed: {heal_info.get('reason')})"

                

                # Load back into the active vector backend (Qdrant by default)

                store_manager.load_domain(

                    domain_name=domain,

                    tables={}, # No schema updates, just SQL

                    patterns=[{"intent": new_intent, "sql": generated_sql}]

                )

                logger.info(f"    [MEMORY COMPOUNDING] Healed SQL successfully indexed into '{store_manager.backend_name}' store.")

            except Exception as e:

                logger.info(f"    [WARN] Failed to index healed SQL into vector store: {e}")



    elif exec_result.status == ToolStatus.ERROR or validate_result.status == ToolStatus.ERROR:

        result_status = "error"

        sap_memory.log_pattern_failure(

            domain=domain,

            pattern_name=top_pattern.get("intent", "unknown") if sql_result.status == ToolStatus.SUCCESS and sql_result.data.get("patterns") else "ad_hoc",

            sql=generated_sql,

            tables=tables_involved,

            error=exec_result.message or validate_result.message,

            critique_score=critique_result["score"],

        )

        # [Phase 11] Failure trigger — non-blocking, async MetaHarnessLoop on cascade
        if heal_info.get("applied", False) is False:
            try:
                from app.core.failure_trigger import check_and_trigger_meta_harness
                check_and_trigger_meta_harness(
                    run_id=current_run_id or "",
                    query=query,
                    error_message=exec_result.message or validate_result.message or "",
                    error_code="",
                    tables_involved=tables_involved,
                    generated_sql=generated_sql,
                    async_mode=True,
                )
            except Exception:
                pass

    else:

        result_status = "empty"

    

    # [Phase 6] Autonomous Self-Improvement — review and improve after every query

    self_improver.review_and_improve(

        query=query,

        sql_generated=generated_sql,

        sql_executed=generated_sql,

        critique_score=critique_result["score"],

        result_status=result_status,

        execution_time_ms=execution_time,

        auth_context=auth_context,

        domain=domain,

        tables_used=tables_involved,

        self_heal_applied=heal_info.get("applied", False),

        feedback_applied=False,
        run_id=current_run_id,
    )

    

    sap_memory.log_query(

        query=query,

        role=auth_context.role_id,

        domain=domain,

        sql=generated_sql,

        tables_used=tables_involved,

        critique_score=critique_result["score"],

        result=result_status,

        execution_time_ms=execution_time,

        error=exec_result.message if exec_result.status == ToolStatus.ERROR else None,

    )

    

    # [Harness] Mark run complete

    if current_run_id:

        try:

            hr.complete_run(

                current_run_id,

                status="completed",

                confidence_score=result_dict.get("confidence_score", {}).get("composite", 0.0),

                execution_time_ms=execution_time,

            )

        except Exception as e:

            if verbose:

                logger.warning(f"  [WARN] [HARNESS] complete_run failed: {e}")



    # [Phase 12] QualityEvaluator — compute and store quality metrics from trajectory

    if current_run_id:

        try:

            hr = get_harness_runs()

            run_obj = hr.get_run(current_run_id)

            if run_obj:

                eval_result = QualityEvaluator.evaluate_run(run_obj)

                result_dict["quality_metrics"] = eval_result

                hr.hset_run_field(current_run_id, "quality_score", str(eval_result["correctness_score"]))

                hr.hset_run_field(current_run_id, "trajectory_adherence", str(eval_result["trajectory_adherence"]))

                if verbose:

                    logger.debug(f"  [HARNESS] QualityEvaluator => correctness={eval_result['correctness_score']} adherence={eval_result['trajectory_adherence']}")

        except Exception as e:

            if verbose:

                logger.warning(f"  [WARN] [HARNESS] QualityEvaluator failed: {e}")



    result_dict["run_id"] = current_run_id

    # Fetch trajectory log from harness run for API response

    if current_run_id:

        try:

            hr = get_harness_runs()

            run_obj = hr.get_run(current_run_id)

            if run_obj:

                result_dict["trajectory_log"] = run_obj.trajectory_log

        except Exception:

            result_dict["trajectory_log"] = []

    else:

        result_dict["trajectory_log"] = []

    return result_dict





# =============================================================================

# CLI Integration — Run agent via command line

# =============================================================================



def main():

    import argparse

    import sys



    parser = argparse.ArgumentParser(description="[Agentic RAG] Run SAP Master Data query")

    parser.add_argument("query", type=str, help="Natural language query")

    parser.add_argument("--role", default="AP_CLERK",

                        choices=["AP_CLERK", "PROCUREMENT_MANAGER_EU", "CFO_GLOBAL", "HR_ADMIN"])

    parser.add_argument("--domain", default="auto",

                        help="Domain (auto, purchasing, material_master, etc.)")

    parser.add_argument("--verbose", action="store_true", help="Print full tool trace")



    args = parser.parse_args()



    from app.core.security import security_mesh



    auth_context = security_mesh.get_context(args.role)



    result = run_agent_loop(

        query=args.query,

        auth_context=auth_context,

        domain=args.domain,

        verbose=args.verbose,

    )



    logger.info("\n" + "=" * 60)

    logger.info("  FINAL RESULT")

    logger.info("=" * 60)

    logger.info(f"\n  Answer: {result['answer']}")

    logger.info(f"\n  SQL:\n  {result['executed_sql']}")

    if result["masked_fields"]:

        logger.info(f"\n  Masked: {result['masked_fields']}")

    logger.info(f"\n  Execution: {result['execution_time_ms']}ms | {len(result['tool_trace'])} tools")





if __name__ == "__main__":

    main()

