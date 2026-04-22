import unittest
from types import SimpleNamespace

from app.agents.swarm.agent_tool_mode import AgentToolMode, ToolModeConfig
from app.agents.swarm.synthesis_agent import SynthesisAgent
from app.core.security import security_mesh


class FakeAgent:
    name = "fake_agent"
    domain = "fake"

    def _resolve_tables(self, query):
        return ["LFA1"]

    def _resolve_sql(self, query, tables, auth_context):
        return "SELECT * FROM LFA1"

    def _inject_auth(self, sql, auth_context):
        return sql + " WHERE MANDT = '100'"

    def _execute(self, sql, auth_context):
        return [{"LIFNR": "V100", "NAME1": "Acme"}]

    def _mask_results(self, rows, auth_context):
        return rows, []

    def run(self, *args, **kwargs):
        return {"status": "normal_run"}


def _ctx(session_id: str = "sess-1"):
    return security_mesh.get_context("AP_CLERK").model_copy(
        update={"session_id": session_id, "user_id": "user:test"}
    )


def _verdict(action: str = "tighten", detected: bool = True):
    return SimpleNamespace(
        threat_detected=detected,
        recommended_action=action,
        evidence=["policy trigger"],
        session_flags=["FLAG"],
        confidence=0.9,
        threat_type=None,
        severity=SimpleNamespace(value="high"),
    )


class Phase19AgentToolModeTests(unittest.TestCase):
    def test_wrap_agent_execution_uses_tool_mode_when_session_active(self):
        mode = AgentToolMode(config=ToolModeConfig(tool_mode_ttl_seconds=60))
        ctx = _ctx()
        mode.activate(ctx.session_id, "sentinel_tighten", _verdict())

        result = mode.wrap_agent_execution(
            agent=FakeAgent(),
            query="show vendor",
            auth_context=ctx,
            session_id=ctx.session_id,
        )

        self.assertTrue(result["tool_mode"])
        self.assertEqual(result["tool_mode_reason"], "sentinel_tighten")
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["executed_sql"].startswith("SELECT * FROM LFA1"))

    def test_synthesis_agent_uses_dedup_only_when_tool_mode_is_active(self):
        mode = AgentToolMode(config=ToolModeConfig(tool_mode_ttl_seconds=60))
        ctx = _ctx("sess-2")
        mode.activate(ctx.session_id, "sentinel_block", _verdict(action="block"))

        agent_results = {
            "bp_agent": {"agent": "bp_agent", "tool_mode": True, "data": [{"LIFNR": "V100", "NAME1": "Acme"}]},
            "pur_agent": {"agent": "pur_agent", "tool_mode": True, "data": [{"LIFNR": "V100", "NAME1": "Acme"}]},
        }

        result = SynthesisAgent().synthesize(
            query="show vendor",
            agent_results=agent_results,
            auth_context=ctx,
            routing=SimpleNamespace(value="parallel"),
            agent_tool_mode=mode,
            session_id=ctx.session_id,
        )

        self.assertTrue(result["tool_mode"])
        self.assertEqual(result["tool_mode_reason"], "sentinel_block")
        self.assertEqual(result["synthesis_method"], "dedup_only")
        self.assertEqual(result["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
