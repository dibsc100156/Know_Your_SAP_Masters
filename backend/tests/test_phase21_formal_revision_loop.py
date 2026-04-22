import unittest

from app.core.formal_revision_loop import create_revision_loop, RevisionPhase


class Phase21FormalRevisionLoopTests(unittest.TestCase):
    def test_converges_when_confidence_threshold_is_met(self):
        loop = create_revision_loop("vendor payment terms", max_iterations=3)
        loop.until_confidence(0.90).until_result_stable(2)
        loop.record_step(
            phase=RevisionPhase.SELF_CRITIQUE,
            action="Initial critique",
            evidence=["score=4.0"],
            justification="Baseline critique before any heal",
        )

        loop.record_iteration({"stage": "critique_heal"})
        self.assertFalse(loop.check_convergence(sql_hash="sql-v1", confidence=0.57))
        self.assertTrue(loop.should_continue())

        loop.record_iteration({"stage": "validation_harness"})
        self.assertTrue(loop.check_convergence(sql_hash="sql-v1", confidence=0.93))

        summary = loop.get_summary()
        self.assertTrue(summary["converged"])
        self.assertEqual(summary["total_iterations"], 2)
        self.assertGreaterEqual(summary["convergence_confidence"], 0.90)
        self.assertEqual(loop.get_formal_trace()[0]["phase"], RevisionPhase.SELF_CRITIQUE.value)

    def test_stops_after_max_iterations_without_convergence(self):
        loop = create_revision_loop("vendor exposure", max_iterations=3)

        for idx in range(3):
            loop.record_iteration({"stage": f"attempt_{idx + 1}"})
            loop.check_convergence(sql_hash=f"sql-v{idx + 1}", confidence=0.20)

        summary = loop.get_summary()
        self.assertFalse(summary["converged"])
        self.assertEqual(summary["total_iterations"], 3)
        self.assertFalse(loop.should_continue())


if __name__ == "__main__":
    unittest.main()
