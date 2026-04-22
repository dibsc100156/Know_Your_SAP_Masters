import unittest
from unittest.mock import patch

from app.core.episodic_memory import EpisodicMemoryStore
from app.core.memory_orchestrator import MemoryOrchestrator
from app.core.memory_writeback import MemoryEvent, MemoryWriteRouter
from app.core.security import security_mesh


class UnifiedMemoryArchitectureTests(unittest.TestCase):
    def test_memory_orchestrator_builds_context_and_applies_policy(self):
        store = EpisodicMemoryStore(force_backend="memory", context_window=4, query_history_limit=5)
        session_id = "memctx-phase24-plus"

        store.record_query(
            session_id=session_id,
            query="show material valuation",
            domain="material",
            role_id="AP_CLERK",
            tables_used=["MBEW", "MARA"],
            answer="valuation details",
        )
        store.set_scratchpad(session_id, "last_tables", ["MBEW", "LFA1"])
        auth_context = security_mesh.get_context("AP_CLERK")

        with patch("app.core.memory_orchestrator.sap_memory.get_boosted_patterns", return_value=[
            {"pattern_name": "material_value", "success_count": 2, "failure_count": 0, "tables": ["MBEW", "MARA"]}
        ]), patch("app.core.memory_orchestrator.sap_memory.get_gotchas", return_value=[
            {"severity": "warn", "pattern": "Always mask vendor bank fields"}
        ]):
            orchestrator = MemoryOrchestrator(memory_store=store)
            context = orchestrator.build_context(
                query="show material valuation",
                session_id=session_id,
                auth_context=auth_context,
                domain_hint="material",
            )

        summary = context.summary()
        self.assertTrue(summary["metadata"]["dedup_hit"])
        self.assertIn("MARA", summary["metadata"]["prior_tables"])
        self.assertNotIn("MBEW", summary["metadata"]["prior_tables"])
        self.assertIn("policy_redactions", summary["metadata"])
        self.assertTrue(any(entry["event"] == "memory_context_ready" for entry in context.memory_trace()))
        self.assertIn("Recent Query Pairs", context.prompt_text())

    def test_memory_writeback_router_records_result_and_updates_scratchpad(self):
        store = EpisodicMemoryStore(force_backend="memory")
        router = MemoryWriteRouter(memory_store=store)

        decisions = router.record_result(MemoryEvent(
            event_type="result",
            session_id="writeback-session",
            query="show vendor payment terms",
            role_id="AP_CLERK",
            domain="vendor",
            tables_used=["LFA1", "LFB1"],
            sql_generated="SELECT * FROM LFA1",
            confidence=0.91,
            answer="ok",
            routing_tier="simple",
            metadata={"pattern_name": "vendor_master_basic"},
        ))

        history = store.get_history("writeback-session")
        scratchpad = store.get_all_scratchpad("writeback-session")

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].query, "show vendor payment terms")
        self.assertEqual(scratchpad["last_domain"], "vendor")
        self.assertEqual(scratchpad["last_routing_tier"], "simple")
        self.assertEqual(scratchpad["last_tables"], ["LFA1", "LFB1"])
        self.assertTrue(any(decision.target == "episodic_memory" for decision in decisions))


if __name__ == "__main__":
    unittest.main()
