import unittest

from app.core.reasoning_policy import ReasoningPolicy
from app.core.reasoning_runtime import ReasoningRuntime
from app.core.reasoning_types import ReasoningDepth


class ReasoningTraceArchitectureTests(unittest.TestCase):
    def test_reasoning_runtime_builds_trace_and_summary(self):
        runtime = ReasoningRuntime(depth=ReasoningDepth.LIGHT)
        runtime.record_reasoning_step("planning", "initialized", ["domain=vendor"], {"routing": "simple"})
        runtime.record_reasoning_step("schema_retrieval", "selected schema candidates", ["LFA1", "LFB1"], {"table_count": 2})

        trace = runtime.build_reasoning_trace().to_dict()

        self.assertEqual(len(trace["steps"]), 2)
        self.assertEqual(trace["summary"]["step_count"], 2)
        self.assertEqual(trace["summary"]["depth"], "light")

    def test_reasoning_policy_light_mode_redacts_detail(self):
        runtime = ReasoningRuntime(depth=ReasoningDepth.DETAILED)
        runtime.record_reasoning_step("execution", "executed candidate SQL", ["ok", "rows=10"], {"status": "success", "rows": 10})

        trace = runtime.build_reasoning_trace()
        filtered = ReasoningPolicy(depth=ReasoningDepth.LIGHT).filter_reasoning_trace(trace).to_dict()

        self.assertEqual(filtered["steps"][0]["evidence"], ["ok"])
        self.assertEqual(filtered["steps"][0]["detail"], {})


if __name__ == "__main__":
    unittest.main()
