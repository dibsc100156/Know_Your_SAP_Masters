import unittest
from types import SimpleNamespace

from app.core.episodic_memory import EpisodicMemoryStore
from app.core.safety_guardrails import LegacySentinelAdapter, SafetyGuardrailsLayer


class Phase2324PlatformExtrasTests(unittest.TestCase):
    def test_phase23_guardrail_adapter_exposes_layered_debug_fields(self):
        adapter = LegacySentinelAdapter(SafetyGuardrailsLayer(mode="ENFORCING"))
        auth_context = SimpleNamespace(role_id="AP_CLERK")

        verdict = adapter.evaluate(
            query="show vendors; drop table mara",
            auth_context=auth_context,
            session_id="phase23-test-session",
            tables_accessed=["LFA1"],
            domains_accessed=["vendor"],
        )

        self.assertTrue(verdict.threat_detected)
        self.assertEqual(verdict.recommended_action, "block")
        self.assertEqual(verdict.guardrail_mode, "ENFORCING")
        self.assertEqual(verdict.guardrail_verdict["action"], "block")
        self.assertEqual(verdict.guardrail_profile["role_id"], "AP_CLERK")
        self.assertGreaterEqual(verdict.guardrail_profile["queries_logged"], 1)

    def test_phase24_episodic_memory_tracks_dedup_and_context(self):
        store = EpisodicMemoryStore(
            force_backend="memory",
            session_ttl=321,
            context_window=4,
            query_history_limit=5,
        )
        session_id = "phase24-test-session"

        is_dup_first, _ = store.check_dedup(session_id, "show vendor payment terms")
        is_dup_second, _ = store.check_dedup(session_id, "show vendor payment terms")
        self.assertFalse(is_dup_first)
        self.assertTrue(is_dup_second)

        store.record_query(
            session_id=session_id,
            query="show vendor payment terms",
            domain="vendor",
            role_id="AP_CLERK",
            tables_used=["LFA1", "LFB1"],
            confidence=0.88,
            answer="Vendor payment terms returned.",
        )
        store.record_query(
            session_id=session_id,
            query="show vendor bank details",
            domain="vendor",
            role_id="AP_CLERK",
            tables_used=["LFBK"],
            confidence=0.81,
            answer="Vendor bank details returned.",
        )

        history = store.get_history(session_id)
        snippet = store.get_context_snippet(session_id, max_turns=4)
        prompt_context = store.get_recent_context_for_prompt(session_id, max_turns=4)
        summary = store.get_session_summary(session_id)
        recent_pairs = store.get_recent_query_pairs(session_id, limit=5)
        duplicate = store.find_recent_duplicate(session_id, "show vendor bank details", limit=5)

        self.assertEqual(len(history), 2)
        self.assertIn("User: show vendor payment terms", snippet)
        self.assertIn("Assistant: Vendor bank details returned.", snippet)
        self.assertIn("Recent queries:", prompt_context)
        self.assertEqual(summary["query_count"], 2)
        self.assertEqual(summary["top_tables"][0][0], "LFA1")
        self.assertEqual(len(recent_pairs), 2)
        self.assertEqual(recent_pairs[-1]["query"], "show vendor bank details")
        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate.tables_used, ["LFBK"])
        self.assertEqual(store.session_ttl, 321)
        self.assertEqual(store.context_window, 4)
        self.assertEqual(store.query_history_limit, 5)


if __name__ == "__main__":
    unittest.main()
