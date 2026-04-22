import unittest

from app.core.recovery_orchestrator import RecoveryOrchestrator
from app.core.recovery_types import RecoveryCase, RecoverySeverity


class RecoveryEscalationArchitectureTests(unittest.TestCase):
    def test_recovery_orchestrator_escalates_to_partial_when_data_exists(self):
        orchestrator = RecoveryOrchestrator()
        case = RecoveryCase(
            error_class="sql_execution_error",
            error_message="mock error",
            context={},
            severity=RecoverySeverity.HIGH,
        )

        result = orchestrator.resolve_recovery(case, context={"has_partial_data": True})

        self.assertEqual(result.decision.lane.value, "partial")
        self.assertEqual(len(result.trace), 1)
        self.assertEqual(result.trace[0]["chosen_lane"], "partial")

    def test_recovery_orchestrator_escalates_to_fallback_when_no_data(self):
        orchestrator = RecoveryOrchestrator()
        case = RecoveryCase(
            error_class="sql_execution_error",
            error_message="mock error",
            context={},
            severity=RecoverySeverity.HIGH,
        )

        result = orchestrator.resolve_recovery(case, context={"has_partial_data": False})

        self.assertEqual(result.decision.lane.value, "fallback")

    def test_recovery_orchestrator_escalates_validation_to_halt(self):
        orchestrator = RecoveryOrchestrator()
        case = RecoveryCase(
            error_class="validation_error",
            error_message="mock error",
            context={},
        )

        result = orchestrator.resolve_recovery(case, context={})

        self.assertEqual(result.decision.lane.value, "halt")


if __name__ == "__main__":
    unittest.main()
