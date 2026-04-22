import unittest

from app.core.replanner import Replanner


class AdaptiveReplanningArchitectureTests(unittest.TestCase):
    def test_replanner_inserts_graph_and_path_steps_when_findings_justify_it(self):
        replanner = Replanner()
        plan = replanner.build_initial_plan(
            ["schema_lookup", "sql_pattern_lookup", "sql_validate", "sql_execute"],
            metadata={"source": "unit-test"},
        )

        revised = replanner.revise_plan(
            plan,
            {
                "stage": "post_schema",
                "schema_confidence": 0.4,
                "retrieval_quality": 0.5,
                "new_tables": 3,
                "temporal_mode": "none",
            },
        )

        step_names = revised.step_names()
        self.assertIn("graph_enhanced_schema_discovery", step_names)
        self.assertIn("all_paths_explore", step_names)
        self.assertGreaterEqual(len(revised.revisions), 1)
        self.assertEqual(revised.revisions[-1].stage, "post_schema")

    def test_replanner_skips_revision_when_benefit_too_low(self):
        replanner = Replanner()
        plan = replanner.build_initial_plan(["schema_lookup", "sql_pattern_lookup", "sql_validate", "sql_execute"])

        revised = replanner.revise_plan(
            plan,
            {
                "stage": "post_schema",
                "schema_confidence": 0.95,
                "retrieval_quality": 0.92,
                "new_tables": 0,
                "temporal_mode": "none",
            },
        )

        self.assertEqual(revised.to_dict(), plan.to_dict())


if __name__ == "__main__":
    unittest.main()
