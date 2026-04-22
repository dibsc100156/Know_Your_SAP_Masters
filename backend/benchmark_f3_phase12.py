import json
from dataclasses import dataclass
from pathlib import Path

from app.core.complexity_router import RoutingDecision, RoutingTier
from app.core.harness_runs import HarnessRun, PhaseState
from app.core.model_driven_sequencer import build_model_driven_plan, refine_model_driven_plan
from app.core.quality_evaluator import QualityEvaluator


REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

AVAILABLE_TOOLS = [
    {"name": "meta_path_match", "description": "Fast semantic SAP template lookup"},
    {"name": "schema_lookup", "description": "Discover grounded SAP tables before SQL generation"},
    {"name": "graph_enhanced_schema_discovery", "description": "Cross-module graph-aware table expansion"},
    {"name": "sql_pattern_lookup", "description": "Retrieve proven SQL patterns"},
    {"name": "temporal_graph_search", "description": "Apply temporal filters and fiscal logic"},
    {"name": "all_paths_explore", "description": "Explore join paths across tables"},
    {"name": "steiner_tree_explore", "description": "Plan 3+ terminal join paths"},
    {"name": "sql_validate", "description": "Validate SQL security and syntax"},
    {"name": "sql_execute", "description": "Execute validated SQL"},
]
BASELINE_TOOLS = [
    "meta_path_match",
    "schema_lookup",
    "graph_enhanced_schema_discovery",
    "sql_pattern_lookup",
    "temporal_graph_search",
    "all_paths_explore",
    "steiner_tree_explore",
    "sql_validate",
    "sql_execute",
]


@dataclass
class F3Scenario:
    name: str
    query: str
    routing: RoutingDecision
    tables: list
    temporal_mode: str
    expected_tools: set


F3_SCENARIOS = [
    F3Scenario(
        name="simple-vendor",
        query="show vendor payment terms",
        routing=RoutingDecision(tier=RoutingTier.COMPLEX, score=0.61, dimensions={"cross_module_join": 0.1, "multi_entity": 0.1, "temporal": 0.0, "qm_long_text": 0.0, "negotiation": 0.0}, enabled_tools=[t["name"] for t in AVAILABLE_TOOLS]),
        tables=["LFA1"],
        temporal_mode="none",
        expected_tools={"meta_path_match", "schema_lookup", "sql_pattern_lookup", "sql_validate", "sql_execute"},
    ),
    F3Scenario(
        name="cross-module-temporal",
        query="compare vendor open items and bank details last fiscal year",
        routing=RoutingDecision(tier=RoutingTier.EXPERT, score=0.91, dimensions={"cross_module_join": 0.8, "multi_entity": 0.7, "temporal": 0.8, "qm_long_text": 0.0, "negotiation": 0.0}, enabled_tools=[t["name"] for t in AVAILABLE_TOOLS]),
        tables=["LFA1", "LFBK", "BSAK"],
        temporal_mode="fiscal_year",
        expected_tools={"meta_path_match", "schema_lookup", "graph_enhanced_schema_discovery", "sql_pattern_lookup", "temporal_graph_search", "all_paths_explore", "steiner_tree_explore", "sql_validate", "sql_execute"},
    ),
    F3Scenario(
        name="cross-module-no-temporal",
        query="vendors supplying the same material across plants",
        routing=RoutingDecision(tier=RoutingTier.EXPERT, score=0.84, dimensions={"cross_module_join": 0.7, "multi_entity": 0.8, "temporal": 0.0, "qm_long_text": 0.0, "negotiation": 0.0}, enabled_tools=[t["name"] for t in AVAILABLE_TOOLS]),
        tables=["LFA1", "EINA", "MARA"],
        temporal_mode="none",
        expected_tools={"meta_path_match", "schema_lookup", "graph_enhanced_schema_discovery", "sql_pattern_lookup", "all_paths_explore", "steiner_tree_explore", "sql_validate", "sql_execute"},
    ),
]


def _precision(selected, expected):
    return len(set(selected) & set(expected)) / max(len(set(selected)), 1)


def _recall(selected, expected):
    return len(set(selected) & set(expected)) / max(len(set(expected)), 1)


def run_f3_benchmark():
    rows = []
    for s in F3_SCENARIOS:
        bootstrap = build_model_driven_plan(s.query, "auto", s.routing, AVAILABLE_TOOLS)
        refined = refine_model_driven_plan(bootstrap, s.routing, s.query, "auto", s.tables, ["schema_lookup", "graph_enhanced_schema_discovery"], s.temporal_mode)
        rows.append({
            "scenario": s.name,
            "baseline_precision": round(_precision(BASELINE_TOOLS, s.expected_tools), 3),
            "bootstrap_precision": round(_precision(bootstrap.selected_tools, s.expected_tools), 3),
            "refined_precision": round(_precision(refined.selected_tools, s.expected_tools), 3),
            "baseline_recall": round(_recall(BASELINE_TOOLS, s.expected_tools), 3),
            "bootstrap_recall": round(_recall(bootstrap.selected_tools, s.expected_tools), 3),
            "refined_recall": round(_recall(refined.selected_tools, s.expected_tools), 3),
            "bootstrap_tools": bootstrap.selected_tools,
            "refined_tools": refined.selected_tools,
            "iterations": refined.iteration,
        })
    avg_baseline_precision = sum(r["baseline_precision"] for r in rows) / len(rows)
    avg_refined_precision = sum(r["refined_precision"] for r in rows) / len(rows)
    return {
        "scenarios": rows,
        "summary": {
            "avg_baseline_precision": round(avg_baseline_precision, 3),
            "avg_refined_precision": round(avg_refined_precision, 3),
            "precision_delta": round(avg_refined_precision - avg_baseline_precision, 3),
        },
    }


def _legacy_phase_only_score(run: HarnessRun):
    phase_states = run.phase_states or []
    return {
        "correctness_score": round(min(1.0, 0.4 + 0.1 * len(phase_states) + (run.confidence_score or 0.0) * 0.2), 2),
        "trajectory_adherence": 0.0,
    }


def run_phase12_benchmark():
    runs = [
        HarnessRun(
            run_id="q1",
            query="vendor payment terms",
            user_role="AP_CLERK",
            status="completed",
            swarm_routing="monolithic",
            confidence_score=0.82,
            phase_states=[
                PhaseState(phase="phase_1", status="completed"),
                PhaseState(phase="phase_2", status="completed"),
                PhaseState(phase="phase_6", status="completed"),
            ],
            trajectory_log=[
                {"step": "phase_0_meta_path", "decision": "miss", "reasoning": "no template", "metadata": {}},
                {"step": "phase_1_schema_rag", "decision": "success", "reasoning": "grounded", "metadata": {}},
                {"step": "phase_2_sql_pattern", "decision": "success", "reasoning": "pattern", "metadata": {}},
                {"step": "phase_8_finalization", "decision": "success", "reasoning": "answer", "metadata": {}},
            ],
        ),
        HarnessRun(
            run_id="q2",
            query="cross module vendor material query",
            user_role="AP_CLERK",
            status="completed",
            swarm_routing="monolithic",
            confidence_score=0.74,
            phase_states=[
                PhaseState(phase="phase_1", status="completed"),
                PhaseState(phase="phase_1_5", status="completed"),
                PhaseState(phase="phase_2", status="completed"),
                PhaseState(phase="phase_6", status="completed"),
            ],
            trajectory_log=[
                {"step": "phase_1_schema_rag", "decision": "success", "reasoning": "grounded", "metadata": {}},
                {"step": "phase_1_5_graph_discovery", "decision": "success", "reasoning": "expanded", "metadata": {}},
                {"step": "phase_2_sql_pattern", "decision": "success", "reasoning": "pattern", "metadata": {}},
                {"step": "phase_4_5_self_critique", "decision": "success", "reasoning": "checked", "metadata": {}},
                {"step": "phase_6_execution", "decision": "success", "reasoning": "executed", "metadata": {}},
                {"step": "phase_8_finalization", "decision": "success", "reasoning": "answer", "metadata": {}},
            ],
        ),
    ]
    rows = []
    for run in runs:
        legacy = _legacy_phase_only_score(run)
        current = QualityEvaluator.evaluate_run(run)
        rows.append({
            "run_id": run.run_id,
            "legacy_correctness": legacy["correctness_score"],
            "current_correctness": current["correctness_score"],
            "current_trajectory_adherence": current["trajectory_adherence"],
            "trajectory_event_count": current["trajectory_event_count"],
        })
    return {
        "runs": rows,
        "summary": {
            "avg_legacy_correctness": round(sum(r["legacy_correctness"] for r in rows) / len(rows), 3),
            "avg_current_correctness": round(sum(r["current_correctness"] for r in rows) / len(rows), 3),
            "avg_current_trajectory_adherence": round(sum(r["current_trajectory_adherence"] for r in rows) / len(rows), 3),
        },
    }


def main():
    report = {
        "f3": run_f3_benchmark(),
        "phase12": run_phase12_benchmark(),
    }
    out = REPORTS_DIR / "benchmark_f3_phase12.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out), "summary": {"f3": report["f3"]["summary"], "phase12": report["phase12"]["summary"]}}, indent=2))


if __name__ == "__main__":
    main()
