"""
model_driven_sequencer.py - Feature 3: Model-Driven Tool Sequencing
===================================================================
Bootstrap implementation of the "Strands" pattern for KYSM.

Goal:
- Stop treating tool order as fully hardcoded.
- Let routing signals + tool descriptions decide which tools matter.
- Keep execution safe by preserving validation/execute guardrails.

This first version is intentionally lightweight. It produces a dynamic execution
plan from plain-English tool descriptions, routing dimensions, and query cues,
then lets the main orchestrator honor that plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set
import re

from app.core.complexity_router import RoutingDecision, RoutingTier


@dataclass
class ModelDrivenPlan:
    enabled: bool
    selected_tools: List[str]
    skipped_tools: List[str]
    rationale: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)

    def allows(self, tool_name: str) -> bool:
        return tool_name in set(self.selected_tools)


TOOL_ORDER = {
    "search_sap_notes": 5,
    "meta_path_match": 10,
    "schema_lookup": 20,
    "graph_enhanced_schema_discovery": 30,
    "sql_pattern_lookup": 40,
    "temporal_graph_search": 50,
    "all_paths_explore": 60,
    "steiner_tree_explore": 65,
    "voting_sql_generate": 70,
    "sql_validate": 90,
    "sql_execute": 100,
    "result_mask": 110,
}


def should_enable_model_driven_mode(routing: RoutingDecision) -> bool:
    return routing.tier in (RoutingTier.COMPLEX, RoutingTier.EXPERT)


def _tokenize(text: str) -> Set[str]:
    return set(re.findall(r"[a-zA-Z_]+", (text or "").lower()))


def _description_score(query_tokens: Set[str], description: str) -> float:
    desc_tokens = _tokenize(description)
    if not desc_tokens:
        return 0.0
    overlap = len(query_tokens.intersection(desc_tokens))
    return overlap / max(len(query_tokens), 1)


def _has_any(query: str, patterns: List[str]) -> bool:
    q = query.lower()
    return any(re.search(p, q) for p in patterns)


def build_model_driven_plan(
    query: str,
    domain: str,
    routing: RoutingDecision,
    available_tools: List[Dict[str, Any]],
) -> ModelDrivenPlan:
    """
    Build a dynamic tool sequence from routing signals + tool descriptions.

    This is a safe first cut of the Strands pattern. It is "model-driven" in the
    sense that the plan is derived from the natural-language tool descriptions and
    query semantics, instead of a single fixed pipeline. The main orchestrator can
    honor or skip tool blocks based on this plan.
    """
    if not should_enable_model_driven_mode(routing):
        return ModelDrivenPlan(enabled=False, selected_tools=[], skipped_tools=[])

    enabled_pool = set(routing.enabled_tools or [t["name"] for t in available_tools])
    tool_map = {t["name"]: t for t in available_tools if t["name"] in enabled_pool}
    query_tokens = _tokenize(query)
    dims = routing.dimensions or {}

    temporal = float(dims.get("temporal", 0.0))
    cross_module = float(dims.get("cross_module_join", 0.0))
    multi_entity = float(dims.get("multi_entity", 0.0))
    qm_long_text = float(dims.get("qm_long_text", 0.0))
    negotiation = float(dims.get("negotiation", 0.0))

    selected: Set[str] = set()
    rationale: List[str] = []

    def choose(tool_name: str, why: str) -> None:
        if tool_name in tool_map:
            selected.add(tool_name)
            rationale.append(f"{tool_name}: {why}")

    # Always start by asking whether a trusted fast-path exists.
    choose("meta_path_match", "start with the cheapest semantic fast-path before deeper retrieval")

    if _has_any(query, [r"\b(error|dump|exception|raise|message|short dump|note|oss)\b", r"\b\w+\s*\d{3}\b"]):
        choose("search_sap_notes", "query looks like an SAP error/symptom and may need Notes/OSS guidance")

    # Schema discovery is foundational in this system.
    choose("schema_lookup", "discover grounded SAP tables before SQL generation")

    if cross_module >= 0.35 or multi_entity >= 0.35 or _has_any(query, [
        r"vendor.*material", r"material.*vendor", r"vendor.*payment", r"invoice.*material",
        r"goods receipt.*invoice", r"sales.*delivery.*invoice", r"across plants", r"cross[- ]module",
    ]):
        choose("graph_enhanced_schema_discovery", "cross-module signal detected, use graph-aware table expansion")

    choose("sql_pattern_lookup", "prefer proven SQL patterns when a validated pattern exists")

    if temporal >= 0.25 or _has_any(query, [
        r"\b(as of|between|during|before|after|trend|year|month|quarter|fy|fiscal|today|yesterday)\b"
    ]):
        choose("temporal_graph_search", "query includes temporal anchors or time-series intent")

    if cross_module >= 0.45 or multi_entity >= 0.45:
        choose("all_paths_explore", "multiple entities/modules suggest join-path reasoning is needed")

    if multi_entity >= 0.70 and "steiner_tree_explore" in tool_map:
        choose("steiner_tree_explore", "high multi-entity score suggests 3+ terminal join planning")

    # Guardrails stay in the plan even though execution remains protected in orchestrator.
    choose("sql_validate", "every generated SQL must pass security validation")
    choose("sql_execute", "execute only after validation passes")

    # Description-aware ranking inside the selected set.
    ordered = sorted(
        selected,
        key=lambda name: (
            TOOL_ORDER.get(name, 999),
            -_description_score(query_tokens, tool_map[name].get("description", "")),
            name,
        ),
    )

    # Preserve hard dependencies.
    if "sql_execute" in ordered and "sql_validate" not in ordered:
        ordered.insert(max(len(ordered) - 1, 0), "sql_validate")
    if "graph_enhanced_schema_discovery" in ordered and "schema_lookup" not in ordered:
        ordered.insert(0, "schema_lookup")
    if "all_paths_explore" in ordered and "schema_lookup" not in ordered:
        ordered.insert(0, "schema_lookup")

    skipped = sorted(enabled_pool.difference(ordered))

    signals = {
        "tier": routing.tier.value,
        "domain": domain,
        "score": routing.score,
        "cross_module": round(cross_module, 3),
        "multi_entity": round(multi_entity, 3),
        "temporal": round(temporal, 3),
        "qm_long_text": round(qm_long_text, 3),
        "negotiation": round(negotiation, 3),
        "description_aware": True,
    }

    return ModelDrivenPlan(
        enabled=True,
        selected_tools=ordered,
        skipped_tools=skipped,
        rationale=rationale,
        signals=signals,
    )
