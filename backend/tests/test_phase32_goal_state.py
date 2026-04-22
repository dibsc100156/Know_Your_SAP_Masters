import unittest

from app.core.goal_drift_detector import GoalDriftDetector
from app.core.goal_policy import GoalPolicy
from app.core.goal_tracker import GoalTracker
from app.core.query_goal import build_query_goal
from app.core.security import security_mesh


class PerQueryGoalStateArchitectureTests(unittest.TestCase):
    def test_goal_state_tracker_and_drift_policy_trigger_replan(self):
        auth_context = security_mesh.get_context("AP_CLERK")
        goal = build_query_goal("vendor trend by year", auth_context, session_context={"prior_turns": 2})
        tracker = GoalTracker(goal)
        detector = GoalDriftDetector()
        policy = GoalPolicy()

        tracker.update_goal_state("planning", "started", domain="vendor")
        tracker.update_goal_state("schema_retrieval", "partial", tables_found=0)
        drifts = detector.detect_drift(tracker.state, {"tables_found": 0, "retrieval_quality": 0.4, "confidence": 0.5})
        action = policy.evaluate_goal_policy(tracker.state, drifts)

        self.assertTrue(any(signal.name == "missing_grounding" for signal in drifts))
        self.assertEqual(action.action, "expand_retrieval")
        self.assertEqual(tracker.state.status, "in_progress")
        self.assertEqual(len(tracker.goal_trace()), 2)

    def test_goal_state_completes_on_final_answer(self):
        auth_context = security_mesh.get_context("AP_CLERK")
        goal = build_query_goal("show vendor payment terms", auth_context)
        tracker = GoalTracker(goal)

        tracker.update_goal_state("planning", "started")
        state = tracker.update_goal_state("final_answer", "completed", confidence=0.88, tables_found=2)

        self.assertEqual(state.status, "completed")
        self.assertEqual(state.progress["final_answer"]["tables_found"], 2)


if __name__ == "__main__":
    unittest.main()
