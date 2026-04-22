import unittest
from types import SimpleNamespace

from app.core.memory_context import MemoryContext
from app.core.retrieval_quality import RetrievalQualityScorer


class RetrievalQualityArchitectureTests(unittest.TestCase):
    def test_retrieval_quality_ranks_tables_and_selects_best_pattern(self):
        schema_result = SimpleNamespace(data={"tables_used": ["LFA1", "LFB1"]})
        graph_result = SimpleNamespace(data={
            "tables_discovered": ["LFA1", "EKKO", "LFB1"],
            "tables": [
                {"table": "LFA1", "is_cross_module_bridge": True},
                {"table": "EKKO", "is_cross_module_bridge": False},
            ],
        })
        sql_result = SimpleNamespace(data={
            "patterns": [
                {"intent": "vendor_master_basic", "tables": ["LFA1", "LFB1"], "sql": "SELECT * FROM LFA1", "distance": 0.10},
                {"intent": "open_purchase_orders", "tables": ["EKKO", "EKPO"], "sql": "SELECT * FROM EKKO", "distance": 0.45},
            ]
        })
        exploration_result = SimpleNamespace(tables_found=["LFA1", "ADRC"], new_tables=["ADRC"], confidence=0.9)
        memory_context = MemoryContext(session_id="s1", query="vendor payment terms", role_id="AP_CLERK")
        memory_context.metadata["prior_tables"] = ["LFA1", "LFB1"]

        assessment = RetrievalQualityScorer().assess(
            query="vendor payment terms",
            domain="vendor",
            schema_result=schema_result,
            graph_result=graph_result,
            sql_result=sql_result,
            exploration_result=exploration_result,
            memory_context=memory_context,
        )

        self.assertGreater(assessment.composite_score, 0.7)
        self.assertEqual(assessment.recommended_pattern["intent"], "vendor_master_basic")
        self.assertEqual(assessment.recommended_tables[0], "LFA1")
        self.assertTrue(any(entry["event"] == "retrieval_quality_ready" for entry in assessment.trace))
        self.assertEqual(len(assessment.summary()["artifacts"]), 5)


if __name__ == "__main__":
    unittest.main()
