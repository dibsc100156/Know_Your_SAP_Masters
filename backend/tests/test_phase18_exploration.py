import unittest

from app.core.exploration_engine import ExplorationCandidate, ExplorationEngine
from app.core.hierarchical_decomposer import decompose_query
from app.core.security import security_mesh


class Phase18ExplorationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = security_mesh.get_context("AP_CLERK")

    def test_exploration_engine_returns_new_tables_for_weak_schema_query(self):
        engine = ExplorationEngine()
        engine._budget._probe_counts.clear()
        engine._budget._cache.clear()

        engine._probe_ddic_field_match = lambda query, domain: [
            ExplorationCandidate(
                table="LFBK",
                description="Vendor bank details",
                domain="business_partner",
                module="BP",
                fields=[{"name": "BANKN", "type": "CHAR", "description": "Bank account"}],
                score=0.82,
                probe_source="PROBE_A",
                field_hits=["BANKN"],
                confidence=0.82,
            )
        ]
        engine._probe_graph_expansion = lambda anchors, query, domain: [
            ExplorationCandidate(
                table="LFA1",
                description="Vendor master",
                domain="business_partner",
                module="BP",
                fields=[{"name": "LIFNR", "type": "CHAR", "description": "Vendor"}],
                score=0.77,
                probe_source="PROBE_B",
                field_hits=["LIFNR"],
                fk_paths=[["LFA1", "LFBK"]],
                confidence=0.77,
            )
        ]
        engine._probe_semantic_ddic = lambda query, domain, auth_context: []

        result = engine.explore(
            query="vendor bank account details",
            auth_context=self.ctx,
            domain="business_partner",
            already_found=["LFA1"],
            schema_rag_confidence=0.25,
        )

        self.assertIn("LFBK", result.tables_found)
        self.assertIn("LFBK", result.new_tables)
        self.assertGreaterEqual(result.confidence, 0.77)
        self.assertIn("PROBE_A", result.probes_used)

    def test_hierarchical_decomposer_builds_cross_module_plan(self):
        plan = decompose_query(
            query="show vendor open purchase orders with material data",
            tables_discovered=["LFA1", "EKKO", "MARA"],
            exploration_tables=["EINA"],
            auth_context=self.ctx,
            meta_path_used=False,
        )

        self.assertEqual(plan.task_type.value, "cross_module")
        self.assertGreaterEqual(len(plan.sub_tasks), 2)
        self.assertIn("EINA", plan.exploration_candidates)
        self.assertTrue(plan.execution_order)
        self.assertGreater(plan.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
