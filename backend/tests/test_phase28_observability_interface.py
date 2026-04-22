import unittest
from types import SimpleNamespace

from app.core.monitoring_dashboard import QueryRecord
from app.core.observability_interface import ObservabilityQueryInterface


class FakeWindow:
    def __init__(self, records):
        self._records = records

    def get_all(self):
        return list(self._records)


class FakeMonitor:
    def __init__(self, records):
        self._window = FakeWindow(records)

    def get_all_metrics(self):
        return {
            "success_rates": {"success_rate": 0.9, "error_rate": 0.1},
            "throughput": {"qpm": 1.5, "qph": 90.0},
            "latency": {"p95_ms": 120, "p99_ms": 220},
            "self_heal": {"heal_rate": 0.2},
        }


class FakeHarnessRuns:
    def get_run(self, run_id):
        if run_id != "run-1":
            return None
        return SimpleNamespace(
            run_id="run-1",
            query="vendor payment terms",
            status="completed",
            routing_tier="SIMPLE",
            trajectory_event_count=2,
            trajectory_log=[{"step": "phase_1"}],
            phase_states=[],
        )


class ObservabilityInterfaceTests(unittest.TestCase):
    def test_query_logs_filters_records(self):
        records = [
            QueryRecord(1.0, 100, "vendor", "AP_CLERK", "success", ["LFA1"], 0.5, 0.7, [], False, "none", False, "", "high", 0.9, None, False, "", 0),
            QueryRecord(2.0, 200, "finance", "CFO_GLOBAL", "error", ["BSEG"], 0.5, 0.5, [], False, "none", False, "", "low", 0.2, None, True, "high", 0, error_type="sql"),
        ]
        interface = ObservabilityQueryInterface(monitor=FakeMonitor(records), harness_runs=FakeHarnessRuns())
        result = interface.query_logs("status=error domain=finance")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["records"][0]["domain"], "finance")

    def test_query_metrics_and_trace(self):
        interface = ObservabilityQueryInterface(monitor=FakeMonitor([]), harness_runs=FakeHarnessRuns())
        self.assertEqual(interface.query_metrics("latency_p95_ms")["value"], 120)
        trace = interface.get_trace("run-1")
        self.assertEqual(trace["run_id"], "run-1")


if __name__ == "__main__":
    unittest.main()
