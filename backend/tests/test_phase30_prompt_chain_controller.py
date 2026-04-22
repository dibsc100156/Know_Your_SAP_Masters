import unittest

from app.core.chain_controller import ChainController
from app.core.chain_types import ChainOutput, ChainStep, QualityGate, RetryBudget, StopCondition


class PromptChainControllerArchitectureTests(unittest.TestCase):
    def test_chain_controller_emits_retry_then_proceed_after_budget_exhausted(self):
        controller = ChainController([
            ChainStep(
                name="schema_lookup",
                label="Schema Lookup",
                quality_gate=QualityGate(min_items=1, allow_empty=False),
                retry_budget=RetryBudget(max_retries=1),
                stop_condition=StopCondition(halt_on_error=False, halt_on_retry_exhausted=False),
            )
        ])

        first = controller.evaluate_step("schema_lookup", ChainOutput(status="success", item_count=0, score=0.0))
        second = controller.evaluate_step("schema_lookup", ChainOutput(status="success", item_count=0, score=0.0))
        result = controller.result()

        self.assertEqual(first.action, "RETRY")
        self.assertEqual(second.action, "PROCEED")
        self.assertEqual(result.step_verdicts["schema_lookup"]["decision"], "PROCEED")
        self.assertEqual(len(result.trace), 2)

    def test_chain_controller_records_halt_when_required_step_errors(self):
        controller = ChainController([
            ChainStep(
                name="critique_gate",
                label="Critique Gate",
                quality_gate=QualityGate(min_items=1, min_score=0.7, allow_empty=False),
                retry_budget=RetryBudget(max_retries=0),
                stop_condition=StopCondition(halt_on_error=True, halt_on_retry_exhausted=True),
                required=True,
            )
        ])

        decision = controller.evaluate_step("critique_gate", ChainOutput(status="error", item_count=1, score=0.4))
        result = controller.result()

        self.assertEqual(decision.action, "HALT")
        self.assertTrue(result.halted)
        self.assertEqual(result.step_verdicts["critique_gate"]["gate_verdict"], "HALT")


if __name__ == "__main__":
    unittest.main()
