import unittest
from types import SimpleNamespace

from fastapi import Request

from app.api.endpoints import chat_async
from app.core.query_priority_scorer import QueryPriorityScorer


class FakeRedis:
    def __init__(self):
        self.data = {}

    def zremrangebyscore(self, key, min_score, max_score):
        items = self.data.get(key, {})
        self.data[key] = {member: score for member, score in items.items() if score > max_score}

    def zcard(self, key):
        return len(self.data.get(key, {}))

    def zadd(self, key, mapping):
        self.data.setdefault(key, {}).update(mapping)

    def expire(self, key, ttl):
        return True


class Phase22QueryPrioritizationTests(unittest.TestCase):
    def test_recency_boost_tracks_user_id_not_role(self):
        redis_client = FakeRedis()
        scorer = QueryPriorityScorer(redis_client=redis_client)

        first = scorer.compute_priority(
            query="vendor payment terms",
            user_role="AP_CLERK",
            routing_tier="simple",
            domain="vendor",
            urgency="normal",
            contract_type="standard",
            user_id="alice",
        )
        second = scorer.compute_priority(
            query="vendor payment terms",
            user_role="AP_CLERK",
            routing_tier="simple",
            domain="vendor",
            urgency="normal",
            contract_type="standard",
            user_id="alice",
        )
        third = scorer.compute_priority(
            query="vendor payment terms",
            user_role="AP_CLERK",
            routing_tier="simple",
            domain="vendor",
            urgency="normal",
            contract_type="standard",
            user_id="bob",
        )

        self.assertEqual(first.breakdown.recency_boost, 1.0)
        self.assertGreater(second.breakdown.recency_boost, 1.0)
        self.assertEqual(third.breakdown.recency_boost, 1.0)

    def test_critical_request_routes_to_priority_queue(self):
        scorer = QueryPriorityScorer(redis_client=None)

        result = scorer.compute_priority(
            query="urgent executive vendor exposure report",
            user_role="CFO_GLOBAL",
            routing_tier="simple",
            domain="finance",
            urgency="critical",
            contract_type="enterprise",
            is_critical_report=True,
            user_id="cfo-user",
        )

        self.assertEqual(result.queue, "priority")
        self.assertGreaterEqual(result.score, 8.0)
        self.assertEqual(result.to_celery_kwargs()["queue"], "priority")

    def test_heavy_recent_volume_gets_penalized_not_infinitely_boosted(self):
        redis_client = FakeRedis()
        scorer = QueryPriorityScorer(redis_client=redis_client, max_recency_queries=20)
        user_key = "phase22:user:alice:recent_queries"
        redis_client.data[user_key] = {f"q{i}": 10_000 + i for i in range(15)}

        result = scorer.compute_priority(
            query="vendor payment terms",
            user_role="AP_CLERK",
            routing_tier="simple",
            domain="vendor",
            urgency="normal",
            contract_type="standard",
            user_id="alice",
        )

        self.assertLess(result.breakdown.recency_boost, 1.15)
        self.assertGreaterEqual(result.breakdown.recency_boost, 0.8)
        self.assertEqual(result.queue, "agent")

    def test_expert_low_urgency_query_does_not_jump_to_priority_queue(self):
        scorer = QueryPriorityScorer(redis_client=None)

        result = scorer.compute_priority(
            query="cross module vendor material quality logistics analysis",
            user_role="AP_CLERK",
            routing_tier="expert",
            domain="auto",
            urgency="low",
            contract_type="standard",
            user_id="ap-user",
        )

        self.assertEqual(result.queue, "agent")
        self.assertLess(result.score, 5.0)


class Phase22AsyncSubmitTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_submit_routes_to_priority_queue_with_metadata(self):
        captured = {}

        def fake_compute_priority(**kwargs):
            return SimpleNamespace(
                score=8.4,
                queue="priority",
                breakdown=SimpleNamespace(to_dict=lambda: {"final_score": 8.4, "queue_target": "priority"}),
                to_celery_kwargs=lambda: {
                    "queue": "priority",
                    "priority": 9,
                    "expires": 300,
                    "routing_key": "priority",
                },
            )

        def fake_apply_async(*, kwargs, **celery_kwargs):
            captured["task_kwargs"] = kwargs
            captured["celery_kwargs"] = celery_kwargs
            return SimpleNamespace(id="task-123")

        original_compute = __import__("app.core.query_priority_scorer", fromlist=["compute_priority"]).compute_priority
        original_route = chat_async.route_with_cost
        original_apply_async = chat_async.run_orchestrator_task.apply_async

        try:
            __import__("app.core.query_priority_scorer", fromlist=["compute_priority"]).compute_priority = fake_compute_priority
            chat_async.route_with_cost = lambda query, domain_hint: SimpleNamespace(tier=SimpleNamespace(value="expert"), score=0.91)
            chat_async.run_orchestrator_task.apply_async = fake_apply_async

            http_request = Request({
                "type": "http",
                "method": "POST",
                "path": "/api/v1/chat/master-data-async",
                "headers": [(b"x-user-id", b"user-42")],
            })
            http_request.state.session_id = "sess-42"

            response = await chat_async.submit_orchestrator_task(
                chat_async.ChatRequest(
                    query="urgent executive vendor exposure report",
                    domain="finance",
                    user_role="CFO_GLOBAL",
                    urgency="critical",
                    contract_type="enterprise",
                ),
                http_request,
            )

            self.assertEqual(response.task_id, "task-123")
            self.assertEqual(response.queue_target, "priority")
            self.assertEqual(response.priority_breakdown["queue_target"], "priority")
            self.assertEqual(captured["celery_kwargs"]["queue"], "priority")
            self.assertEqual(captured["task_kwargs"]["priority_score"], 8.4)
            self.assertEqual(captured["task_kwargs"]["queue_target"], "priority")
            self.assertEqual(captured["task_kwargs"]["routing_tier"], "expert")
            self.assertEqual(captured["task_kwargs"]["user_id"], "user-42")
            self.assertEqual(captured["task_kwargs"]["session_id"], "sess-42")
        finally:
            __import__("app.core.query_priority_scorer", fromlist=["compute_priority"]).compute_priority = original_compute
            chat_async.route_with_cost = original_route
            chat_async.run_orchestrator_task.apply_async = original_apply_async


if __name__ == "__main__":
    unittest.main()
