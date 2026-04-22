import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

TEST_MODULES = [
    "tests.test_phase17_agent_notifications",
    "tests.test_phase25_long_running_jobs",
    "tests.test_phase26_pr_review_loop",
    "tests.test_phase27_doc_gardening",
    "tests.test_phase28_observability_interface",
    "tests.test_phase20_router_cost_tracker",
    "tests.test_phase22_query_prioritization",
    "tests.test_phase11_meta_harness_loop",
    "tests.test_phase12_quality_trajectory",
    "tests.test_f3_tool_sequencing",
    "tests.test_phase23_24_platform_extras",
]


def main() -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    cmd = [sys.executable, "-m", "unittest", *TEST_MODULES]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    report = {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": cmd,
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "modules": TEST_MODULES,
    }
    out = REPORTS_DIR / "end_to_end_validation_sweep.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out), "passed": report["passed"]}, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
