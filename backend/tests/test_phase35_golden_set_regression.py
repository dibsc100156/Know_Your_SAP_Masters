import unittest

from app.evals.change_impact import ChangeImpactDetector
from app.evals.eval_runner import EvalRunner
from app.evals.golden_set import load_golden_set
from app.evals.regression_gate import RegressionGate


class AutomatedGoldenSetRegressionArchitectureTests(unittest.TestCase):
    def test_change_impact_detector_selects_graph_and_safety_scope(self):
        scope = ChangeImpactDetector().detect_eval_scope(changed_components=["graph_discovery", "security_guardrails"])
        self.assertIn("graph", scope.tags)
        self.assertIn("safety", scope.tags)

    def test_eval_runner_and_gate_warn_on_partial_pass(self):
        golden_set = load_golden_set("runtime_guardrails")
        eval_run = EvalRunner().run_golden_set(
            golden_set=golden_set,
            scope=["routing", "answer"],
            observed={
                "domain": "vendor",
                "confidence": 0.20,
                "tables_used": ["LFA1"],
                "masked_fields": [],
                "routing_path": "standard",
            },
        )
        verdict = RegressionGate().evaluate_regression_gate(eval_run)
        self.assertEqual(len(eval_run.results), 1)
        self.assertEqual(verdict.status, "block")

    def test_eval_runner_passes_when_runtime_expectations_hold(self):
        golden_set = load_golden_set("runtime_guardrails")
        eval_run = EvalRunner().run_golden_set(
            golden_set=golden_set,
            scope=["routing", "answer"],
            observed={
                "domain": "vendor",
                "confidence": 0.50,
                "tables_used": ["LFA1"],
                "masked_fields": [],
                "routing_path": "standard",
            },
        )
        verdict = RegressionGate().evaluate_regression_gate(eval_run)
        self.assertEqual(verdict.status, "pass")


if __name__ == "__main__":
    unittest.main()
