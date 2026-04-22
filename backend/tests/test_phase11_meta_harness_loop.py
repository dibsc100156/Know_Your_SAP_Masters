import tempfile
import unittest
from pathlib import Path

from app.core.meta_harness_loop import BACKEND_ROOT, MetaHarnessLoop, Recommendation


class Phase11MetaHarnessLoopTests(unittest.TestCase):
    def test_summarize_recommendations_groups_by_priority_category_and_status(self):
        loop = MetaHarnessLoop()
        recs = [
            Recommendation(
                rec_id="rec-1",
                category="healing_rules",
                title="Add heal rule",
                evidence="e1",
                pattern_description="p1",
                recommended_fix="f1",
                target_file="backend/app/core/self_healer.py",
                patch_lines=["RULE_X"],
                priority="P0",
                status="pending",
            ),
            Recommendation(
                rec_id="rec-2",
                category="meta_paths",
                title="Add meta path",
                evidence="e2",
                pattern_description="p2",
                recommended_fix="f2",
                target_file="backend/app/core/meta_path_library.py",
                patch_lines=["PATH_Y"],
                priority="P1",
                status="approved",
            ),
        ]

        summary = loop.summarize_recommendations(recs)

        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["by_priority"]["P0"], 1)
        self.assertEqual(summary["by_priority"]["P1"], 1)
        self.assertEqual(summary["by_category"]["healing_rules"], 1)
        self.assertEqual(summary["by_status"]["pending"], 1)
        self.assertEqual(summary["by_status"]["approved"], 1)

    def test_approve_and_apply_patches_target_file(self):
        loop = MetaHarnessLoop()

        with tempfile.TemporaryDirectory(dir=BACKEND_ROOT) as tmpdir:
            tmp_path = Path(tmpdir)
            target = tmp_path / "sample_target.py"
            target.write_text("print('hello')\n", encoding="utf-8")
            rel_target = str(target.relative_to(BACKEND_ROOT)).replace("\\", "/")

            rec = Recommendation(
                rec_id="rec-apply-1",
                category="schema_rag",
                title="Append harmless marker",
                evidence="repeated schema miss",
                pattern_description="same file needs extra context",
                recommended_fix="append marker",
                target_file=rel_target,
                patch_lines=["# meta harness patch marker"],
                priority="P1",
                risk="low",
            )
            yaml_path = tmp_path / "analysis_test.yaml"
            yaml_path.write_text(rec.to_yaml() + "\n---\n", encoding="utf-8")

            result = loop.approve_and_apply(yaml_path, rec_ids=["rec-apply-1"])
            patched = target.read_text(encoding="utf-8")

            self.assertTrue(result["rec-apply-1"][0])
            self.assertIn("# meta harness patch marker", patched)


if __name__ == "__main__":
    unittest.main()
