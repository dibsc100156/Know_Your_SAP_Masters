import unittest

from app.core.pr_review_loop import RalphWiggumPRReviewLoop


class PRReviewLoopTests(unittest.TestCase):
    def test_review_loop_requests_changes_without_tests(self):
        loop = RalphWiggumPRReviewLoop()
        result = loop.iterate_until_stable(
            pr_title="feat: add async control plane",
            changed_files=["backend/app/api/endpoints/chat_async.py"],
            diff_summary="API change with no benchmark mention",
            tests_added=False,
            docs_updated=False,
            max_rounds=1,
        )

        self.assertEqual(result["status"], "changes_requested")
        self.assertGreater(result["blocking_count"], 0)

    def test_review_loop_approves_small_well_formed_pr(self):
        loop = RalphWiggumPRReviewLoop()
        result = loop.iterate_until_stable(
            pr_title="feat: add endpoint tests",
            changed_files=["backend/app/api/endpoints/chat_async.py", "docs/README.md"],
            diff_summary="security docs benchmark auth updated",
            tests_added=True,
            docs_updated=True,
            max_rounds=2,
        )

        self.assertEqual(result["status"], "approved")
        self.assertTrue(result["auto_merge_eligible"])


if __name__ == "__main__":
    unittest.main()
