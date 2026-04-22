import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

from app.core.eval_alerting import EvalAlertMonitor

router = APIRouter()

# Import the real 8-phase orchestrator
from app.agents.deep_research import run_deep_research
from app.agents.orchestrator import run_agent_loop
from app.core.security import security_mesh
from app.core.quality_evaluator import QualityEvaluator
from app.core.harness_runs import get_harness_runs
from app.core.router_cost_tracker import route_with_cost, get_router_cost_tracker


# =============================================================================
# Request / Response Models
# =============================================================================

class ChatRequest(BaseModel):
    query: str = Field(..., description="Natural language question about SAP master data")
    domain: str = Field(default="auto", description="Routing domain (auto or explicit)")
    user_role: str = Field(default="AP_CLERK", description="SAP Role Key")
    use_swarm: bool = Field(default=False, description="Use Multi-Agent Domain Swarm")
    # Phase 22: Dynamic Query Prioritization
    urgency: str = Field(default="normal", description="Urgency: critical | high | normal | low")
    contract_type: str = Field(default="standard", description="SLA: enterprise premium standard")


class DeepResearchRequest(BaseModel):
    query: str = Field(..., description="Natural language research question about SAP data")
    domain: str = Field(default="auto", description="Routing domain hint")
    user_role: str = Field(default="AP_CLERK", description="SAP Role Key")
    research_depth: int = Field(default=3, ge=1, le=5, description="How aggressively to materialize and verify evidence")
    max_evidence: int = Field(default=15, ge=5, le=30, description="Maximum evidence items to retain in the pack")
    time_horizon: str = Field(default="auto", description="Optional research horizon, e.g. auto | 30d | 90d | 1y | 3y")


class ChatResponse(BaseModel):
    # Core answer
    answer: str
    query: str

    # SQL & tables
    sql_generated: Optional[str] = None
    tables_used: List[str] = Field(default_factory=list)

    # Data
    data: Optional[List[Dict[str, Any]]] = None

    # Security
    masked_fields: List[str] = Field(default_factory=list)

    # Phase 4: Critique
    critique: Optional[Dict[str, Any]] = None

    # Phase 5: Tool trace
    tool_trace: Optional[List[Dict[str, Any]]] = None

    # Phase 7: Temporal
    temporal: Optional[Dict[str, Any]] = None

    # Phase 8: QM Semantic
    qm_semantic: Optional[Dict[str, Any]] = None

    # Phase 8: Negotiation
    negotiation_brief: Optional[Dict[str, Any]] = None

    # Self-heal events
    self_heal: Optional[Dict[str, Any]] = None

    # Phase 18: Exploration & Discovery
    exploration: Optional[Dict[str, Any]] = None
    decomposition_plan: Optional[Dict[str, Any]] = None

    # Meta
    execution_time_ms: Optional[int] = None
    token_tracking: Optional[Dict[str, Any]] = None

    # Confidence breakdown (new — multi-signal composite)
    confidence_score: Optional[Dict[str, Any]] = None

    # Routing intelligence (new)
    routing_path: Optional[str] = None   # "fast_path" | "cross_module" | "standard" | swarm routing
    pattern_name: Optional[str] = None   # SQL pattern that fired, or "ad_hoc"

    # Swarm-specific fields (populated when use_swarm=True)
    swarm_routing: Optional[str] = None  # "single" | "parallel" | "cross_module" | "negotiation" | "escalated"
    planner_reasoning: Optional[str] = None
    agent_summary: Optional[Dict[str, Any]] = None  # {agent_name: {status, record_count, ...}}
    domain_coverage: Optional[List[str]] = None     # ["bp_agent", "mm_agent", ...]
    conflicts: Optional[List[Dict[str, Any]]] = None  # value conflicts across agents
    model_driven_plan: Optional[Dict[str, Any]] = None
    model_driven_plan_history: Optional[List[Dict[str, Any]]] = None
    complexity_score: Optional[float] = None

    # Phase L5: Complexity Routing intelligence returned to frontend
    routing_tier: Optional[str] = None    # "trivial" | "simple" | "complex" | "expert"
    routing_score: Optional[float] = None  # 0.0–1.0 composite score

    # Phase 6c: Threat Sentinel
    sentinel: Optional[Dict[str, Any]] = None      # {verdict, flags, session_tightness}
    sentinel_stats: Optional[Dict[str, Any]] = None  # per-engine detection counts

    # Phase 19: Agent-as-Tool Dynamic Override
    tool_mode: Optional[bool] = None
    tool_mode_reason: Optional[str] = None

    # Harness Runs tracking
    run_id: Optional[str] = None                  # Redis harness run identifier

    # Phase 21: Formal Revision Loop
    formal_trace: Optional[List[Dict[str, Any]]] = None
    revision_summary: Optional[Dict[str, Any]] = None

    # Synthesis validation summary (populated when use_swarm=True)
    validation_summary: Optional[Dict[str, Any]] = None  # {agents_validated, agents_passed, agents_failed, per_agent}

    # Phase 22: Dynamic Query Prioritization
    priority_score: Optional[float] = None  # Urgency x Role-Authority score
    queue_target: Optional[str] = None      # Celery queue: agent | priority
    priority_breakdown: Optional[Dict[str, Any]] = None

    # Phase 23 / 24 platform extras
    guardrails: Optional[Dict[str, Any]] = None
    episodic_context: Optional[str] = None
    episodic_memory: Optional[Dict[str, Any]] = None
    prior_turns: Optional[int] = None
    prior_tables: Optional[List[str]] = None
    urgency: Optional[str] = None            # Urgency level applied

    # Phase 20: Resource-Aware Cost Router
    cost_stats: Optional[Dict[str, Any]] = None
    routing_bypass_reason: Optional[str] = None

    # Role context returned for frontend display
    role_applied: str
    user_id: str

    # Quality Metrics
    quality_metrics: Optional[Dict[str, float]] = None
    trajectory_log: Optional[List[Dict[str, Any]]] = None


@router.post("/chat/master-data", response_model=ChatResponse)
async def chat_master_data_endpoint(request: ChatRequest, http_request: Request):
    """
    Unified endpoint — wires directly to the 8-phase orchestrator.
    Returns the full richness of Phases 1-8 for the modernized frontend.
    """
    # Validate role
    try:
        base_context = security_mesh.get_context(request.user_role)
        session_id = getattr(http_request.state, "session_id", None)
        user_id = http_request.headers.get("X-User-ID") or session_id or f"user:{request.user_role.lower()}"
        auth_context = base_context.model_copy(update={
            "session_id": session_id,
            "user_id": user_id,
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # [Phase L5 + Phase 20] Compute cost-aware routing before calling orchestrator
        routing = route_with_cost(
            query=request.query,
            domain_hint=request.domain,
        )

        # [Phase 22] Compute priority for sync endpoint (informational only)
        from app.core.query_priority_scorer import compute_priority
        priority_result = compute_priority(
            query=request.query,
            user_role=request.user_role,
            routing_tier=routing.tier.value,
            domain=request.domain,
            urgency=request.urgency,
            contract_type=request.contract_type,
            is_critical_report=request.urgency.lower() == "critical",
            user_id=user_id,
        )

        result = run_agent_loop(
            query=request.query,
            auth_context=auth_context,
            domain=request.domain,
            use_supervisor=False,   # NOTE: use_supervisor=True returns a simplified result
                                   # missing confidence_score, critique, temporal, qm_semantic,
                                   # tool_trace, and all other enrichment fields needed by the
                                   # frontend. Keep disabled until the SupervisorAgent is updated
                                   # to return the full 8-phase result dict.
            use_swarm=request.use_swarm,  # Multi-Agent Domain Swarm vs monolithic orchestrator
            routing=routing,           # Phase L5+20: pre-computed cost-aware routing
        )

        router_tracker = get_router_cost_tracker()
        result.setdefault("cost_stats", router_tracker.get_cost_stats())
        result["routing_bypass_reason"] = router_tracker.get_bypass_alert()

        # [Phase 22] Attach priority metadata to result
        result["priority_score"] = round(priority_result.score, 3)
        result["queue_target"] = priority_result.queue
        result["priority_breakdown"] = priority_result.breakdown.to_dict()
        result["urgency"] = request.urgency

        # [Phase L4] Record query metrics for monitoring dashboard
        # Must be recorded BEFORE enrichment so result_dict has orchestrator's raw fields
        try:
            from app.core.monitoring_dashboard import record_query
            record_query(result)
        except Exception:
            pass  # monitoring must never affect API responses

        # negotiation_brief can be a NegotiationBrief dataclass or dict
        neg_brief = result.get("negotiation_brief")
        if neg_brief is not None and not isinstance(neg_brief, dict):
            # Convert dataclass to dict for JSON serialization
            neg_brief = {
                "entity_id": neg_brief.entity_id,
                "entity_name": neg_brief.entity_name,
                "entity_type": neg_brief.entity_type.value if hasattr(neg_brief.entity_type, "value") else str(neg_brief.entity_type),
                "negotiation_type": neg_brief.negotiation_type.value if hasattr(neg_brief.negotiation_type, "value") else str(neg_brief.negotiation_type),
                "relationship_years": neg_brief.relationship_years,
                "price_sensitivity_index": neg_brief.price_sensitivity_index,
                "sensitivity_tier": neg_brief.sensitivity_tier.value if hasattr(neg_brief.sensitivity_tier, "value") else str(neg_brief.sensitivity_tier),
                "payment_reliability_score": neg_brief.payment_reliability_score,
                "clv_tier": neg_brief.clv_tier,
                "total_revenue_20yr": neg_brief.total_revenue_20yr,
                "avg_annual_revenue": neg_brief.avg_annual_revenue,
                "current_year_revenue": neg_brief.current_year_revenue,
                "revenue_trend_5yr": neg_brief.revenue_trend_5yr,
                "total_discounts_20yr": neg_brief.total_discounts_20yr,
                "avg_discount_pct": neg_brief.avg_discount_pct,
                "churn_risk": neg_brief.churn_risk,
                "churn_evidence": neg_brief.churn_evidence,
                "concentration_risk": neg_brief.concentration_risk,
                "competitive_threat": neg_brief.competitive_threat,
                "batna": neg_brief.batna,
                "batna_strength": neg_brief.batna_strength,
                "recommended_increase_pct": neg_brief.recommended_increase_pct,
                "max_acceptable_increase_pct": neg_brief.max_acceptable_increase_pct,
                "recommended_discount": neg_brief.recommended_discount,
                "top_tactics": neg_brief.top_tactics,
                "bottom_line": neg_brief.bottom_line,
                "generated_at": neg_brief.generated_at,
                "data_quality": neg_brief.data_quality,
            }

        quality_metrics = None
        run_id = result.get("run_id")
        if run_id:
            try:
                harness_runs = get_harness_runs()
                run_obj = harness_runs.get_run(run_id)
                if run_obj:
                    quality_metrics = QualityEvaluator.evaluate_run(run_obj)
            except Exception as e:
                import logging
                logging.error(f"Failed to compute quality metrics for {run_id}: {e}")

        return ChatResponse(
            query=request.query,
            answer=result.get("answer", ""),
            sql_generated=result.get("executed_sql"),
            tables_used=result.get("tables_used", []),
            data=result.get("data"),
            masked_fields=result.get("masked_fields", []),
            critique=result.get("critique"),
            tool_trace=result.get("tool_trace"),
            temporal=result.get("temporal"),
            qm_semantic=result.get("qm_semantic"),
            negotiation_brief=neg_brief,
            self_heal=result.get("self_heal"),
            exploration=result.get("exploration"),
            decomposition_plan=result.get("decomposition_plan"),
            execution_time_ms=result.get("execution_time_ms"),
            token_tracking=result.get("token_tracking"),
            confidence_score=result.get("confidence_score"),
            routing_path=result.get("routing_path") or result.get("swarm_routing"),
            pattern_name=result.get("pattern_name"),
            swarm_routing=result.get("swarm_routing"),
            planner_reasoning=result.get("planner_reasoning"),
            agent_summary=result.get("agent_summary"),
            domain_coverage=result.get("domain_coverage"),
            conflicts=result.get("conflicts"),
            model_driven_plan=result.get("model_driven_plan"),
            model_driven_plan_history=result.get("model_driven_plan_history"),
            complexity_score=result.get("complexity_score"),
            routing_tier=routing.tier.value if routing else None,
            routing_score=routing.score if routing else None,
            sentinel=result.get("sentinel"),
            sentinel_stats=result.get("sentinel_stats"),
            tool_mode=result.get("tool_mode"),
            tool_mode_reason=result.get("tool_mode_reason"),
            run_id=result.get("run_id"),
            formal_trace=result.get("formal_trace"),
            revision_summary=result.get("revision_summary"),
            validation_summary=result.get("validation_summary"),
            role_applied=auth_context.role_id,
            user_id=auth_context.user_id or f"user:{auth_context.role_id.lower()}",
            quality_metrics=quality_metrics,
            trajectory_log=result.get("trajectory_log"),
            # Phase 22: Dynamic Query Prioritization
            priority_score=result.get("priority_score"),
            queue_target=result.get("queue_target"),
            priority_breakdown=result.get("priority_breakdown"),
            guardrails=result.get("guardrails"),
            episodic_context=result.get("episodic_context"),
            episodic_memory=result.get("episodic_memory"),
            prior_turns=result.get("prior_turns"),
            prior_tables=result.get("prior_tables"),
            urgency=result.get("urgency"),
            cost_stats=result.get("cost_stats"),
            routing_bypass_reason=result.get("routing_bypass_reason"),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orchestrator error: {str(e)}")


@router.post("/chat/deep-research")
async def deep_research_endpoint(request: DeepResearchRequest, http_request: Request):
    """Deep Research entrypoint.

    Runs the new evidence-first workflow, currently with live search-stage wiring
    to meta-paths, graph embeddings, and graph traversal.
    """
    try:
        base_context = security_mesh.get_context(request.user_role)
        session_id = getattr(http_request.state, "session_id", None)
        user_id = http_request.headers.get("X-User-ID") or session_id or f"user:{request.user_role.lower()}"
        auth_context = base_context.model_copy(update={
            "session_id": session_id,
            "user_id": user_id,
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = run_deep_research(
            question=request.query,
            auth_context=auth_context,
            context={
                "domain": request.domain,
                "user_role": request.user_role,
                "research_depth": request.research_depth,
                "max_evidence": request.max_evidence,
                "time_horizon": request.time_horizon,
            },
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deep Research error: {str(e)}")


@router.get("/domains")
async def list_supported_domains():
    """Returns all 18 supported SAP master data domains."""
    return [
        "auto",
        "business_partner",
        "material_master",
        "purchasing",
        "sales_distribution",
        "warehouse_management",
        "quality_management",
        "financial_accounting",
        "project_system",
        "transportation",
        "customer_service",
        "ehs",
        "variant_configuration",
        "real_estate",
        "gts",
        "is_oil",
        "is_retail",
        "is_utilities",
        "is_health",
        "taxation_india",
        "cross_module",
    ]


@router.get("/roles")
async def list_supported_roles():
    """Returns available SAP roles with their auth scopes."""
    return {
        "AP_CLERK": {
            "description": "Accounts Payable Clerk — US Operations",
            "company_codes": ["1000", "1010"],
            "plants": [],
            "purchasing_orgs": [],
        },
        "PROCUREMENT_MANAGER_EU": {
            "description": "Procurement Manager — Europe",
            "company_codes": ["2000", "2010"],
            "plants": [],
            "purchasing_orgs": ["EU01", "EU02"],
        },
        "CFO_GLOBAL": {
            "description": "Global Chief Financial Officer",
            "company_codes": ["*"],
            "plants": ["*"],
            "purchasing_orgs": ["*"],
        },
        "HR_ADMIN": {
            "description": "Human Resources Administrator",
            "company_codes": ["*"],
            "plants": [],
            "purchasing_orgs": [],
        },
    }


# ── Eval Alerting Endpoints ───────────────────────────────────────────────────


@router.get("/alerts", tags=["system"])
async def get_eval_alerts():
    """
    Returns all unresolved eval alerts (benchmark regressions).
    Frontend polls this every ~30s to show notification badges.
    """
    monitor = EvalAlertMonitor()
    alerts = monitor.get_active_alerts()
    summary = monitor.get_alert_summary()
    last_run = monitor.get_last_run()
    return {
        "alerts": alerts,
        "summary": summary,
        "last_run": last_run,
    }



@router.delete("/alerts/{alert_id}", tags=["system"])
async def resolve_alert(alert_id: str):
    """Acknowledge and resolve a specific alert."""
    monitor = EvalAlertMonitor()
    success = monitor.resolve_alert(alert_id)
    if success:
        return {"status": "resolved", "alert_id": alert_id}
    raise HTTPException(status_code=404, detail="Alert not found")



@router.delete("/alerts", tags=["system"])
async def clear_resolved_alerts():
    """Delete all resolved alerts from Redis."""
    monitor = EvalAlertMonitor()
    monitor.clear_resolved()
    return {"status": "cleared"}
