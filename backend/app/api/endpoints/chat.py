from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from app.core.eval_alerting import EvalAlertMonitor

router = APIRouter()

# Import the real 8-phase orchestrator
from app.agents.orchestrator import run_agent_loop
from app.core.security import security_mesh


# =============================================================================
# Request / Response Models
# =============================================================================

class ChatRequest(BaseModel):
    query: str = Field(..., description="Natural language question about SAP master data")
    domain: str = Field(default="auto", description="Routing domain (auto or explicit)")
    user_role: str = Field(default="AP_CLERK", description="SAP Role Key")


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

    # Meta
    execution_time_ms: Optional[int] = None
    token_tracking: Optional[Dict[str, Any]] = None

    # Confidence breakdown (new — multi-signal composite)
    confidence_score: Optional[Dict[str, Any]] = None

    # Routing intelligence (new)
    routing_path: Optional[str] = None   # "fast_path" | "cross_module" | "standard"
    pattern_name: Optional[str] = None   # SQL pattern that fired, or "ad_hoc"

    # Role context returned for frontend display
    role_applied: str
    user_id: str


@router.post("/chat/master-data", response_model=ChatResponse)
async def chat_master_data_endpoint(request: ChatRequest):
    """
    Unified endpoint — wires directly to the 8-phase orchestrator.
    Returns the full richness of Phases 1-8 for the modernized frontend.
    """
    # Validate role
    try:
        auth_context = security_mesh.get_context(request.user_role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = run_agent_loop(
            query=request.query,
            auth_context=auth_context,
            domain=request.domain,
            use_supervisor=False,   # NOTE: use_supervisor=True returns a simplified result
                                   # missing confidence_score, critique, temporal, qm_semantic,
                                   # tool_trace, and all other enrichment fields needed by the
                                   # frontend. Keep disabled until the SupervisorAgent is updated
                                   # to return the full 8-phase result dict.
        )

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
            execution_time_ms=result.get("execution_time_ms"),
            token_tracking=result.get("token_tracking"),
            confidence_score=result.get("confidence_score"),
            routing_path=result.get("routing_path"),
            pattern_name=result.get("pattern_name"),
            role_applied=auth_context.role_id,
            user_id=f"user:{auth_context.role_id.lower()}",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orchestrator error: {str(e)}")


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
