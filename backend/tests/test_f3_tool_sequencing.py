import unittest

from app.core.complexity_router import RoutingDecision, RoutingTier
from app.core.model_driven_sequencer import (
    build_model_driven_plan,
    refine_model_driven_plan,
)


AVAILABLE_TOOLS = [
    {"name": "meta_path_match", "description": "Fast semantic SAP template lookup"},
    {"name": "schema_lookup", "description": "Discover grounded SAP tables before SQL generation"},
    {"name": "graph_enhanced_schema_discovery", "description": "Cross-module graph-aware table expansion"},
    {"name": "sql_pattern_lookup", "description": "Retrieve proven SQL patterns"},
    {"name": "temporal_graph_search", "description": "Apply temporal filters and fiscal logic"},
    {"name": "all_paths_explore", "description": "Explore join paths across tables"},
    {"name": "sql_validate", "description": "Validate SQL security and syntax"},
    {"name": "sql_execute", "description": "Execute validated SQL"},
]


class F3ToolSequencingTests(unittest.TestCase):
    def _routing(self):
        return RoutingDecision(
            tier=RoutingTier.COMPLEX,
            score=0.82,
            dimensions={
                "cross_module_join": 0.2,
                "multi_entity": 0.2,
                "temporal": 0.0,
                "qm_long_text": 0.0,
                "negotiation": 0.0,
            },
            enabled_tools=[t["name"] for t in AVAILABLE_TOOLS],
        )

    def test_bootstrap_plan_starts_with_safe_core_sequence(self):
        plan = build_model_driven_plan(
            query="show vendor payment terms",
            domain="auto",
            routing=self._routing(),
            available_tools=AVAILABLE_TOOLS,
        )

        self.assertTrue(plan.enabled)
        self.assertIn("meta_path_match", plan.selected_tools)
        self.assertIn("schema_lookup", plan.selected_tools)
        self.assertIn("sql_validate", plan.selected_tools)
        self.assertIn("sql_execute", plan.selected_tools)
        self.assertEqual(plan.iteration, 1)

    def test_refinement_adds_join_reasoning_after_grounding_multiple_tables(self):
        plan = build_model_driven_plan(
            query="show vendor payment terms",
            domain="auto",
            routing=self._routing(),
            available_tools=AVAILABLE_TOOLS,
        )

        refined = refine_model_driven_plan(
            plan=plan,
            routing=self._routing(),
            query="show vendor payment terms",
            domain="auto",
            tables_involved=["LFA1", "LFB1", "BSAK"],
            completed_tools=["schema_lookup", "graph_enhanced_schema_discovery"],
            temporal_mode="none",
        )

        self.assertGreater(refined.iteration, plan.iteration)
        self.assertIn("all_paths_explore", refined.selected_tools)
        self.assertTrue(refined.signals["iterative_refinement"])
        self.assertEqual(refined.signals["tables_involved"], 3)


if __name__ == "__main__":
    unittest.main()
