import tempfile
import unittest
from pathlib import Path

from app.core.doc_gardening_agent import DocGardeningAgent


class DocGardeningAgentTests(unittest.TestCase):
    def test_scan_detects_broken_references(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            docs = repo / "docs"
            docs.mkdir(parents=True, exist_ok=True)
            (docs / "A.md").write_text("See `backend/app/missing.py`\n", encoding="utf-8")
            (docs / "LEVEL5_ROADMAP.md").write_text("ok", encoding="utf-8")
            (docs / "LEVEL5_PUNCHLIST.md").write_text("ok", encoding="utf-8")

            result = DocGardeningAgent(repo).scan()

            self.assertEqual(result["status"], "needs_attention")
            self.assertTrue(any(issue["issue_type"] == "broken_reference" for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
