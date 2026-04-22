import unittest
from types import SimpleNamespace

from fastapi import Request

from app.api.endpoints import chat_async
from app.core.agent_notifications import AgentNotificationStore


class AgentNotificationStoreTests(unittest.TestCase):
    def test_create_list_and_mark_read(self):
        store = AgentNotificationStore(redis_url="redis://invalid:6379/0")
        created = store.create_notification(
            title="Task queued",
            message="Queued on agent",
            user_id="user-1",
            session_id="sess-1",
            task_id="task-1",
        )

        notifications = store.list_notifications(user_id="user-1")
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["notification_id"], created["notification_id"])
        self.assertEqual(store.get_summary(user_id="user-1")["unread"], 1)

        self.assertTrue(store.mark_read(created["notification_id"]))
        self.assertEqual(store.get_summary(user_id="user-1")["unread"], 0)


class Phase17AsyncSubmitNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_submit_creates_queued_notification(self):
        notification_store = AgentNotificationStore(redis_url="redis://invalid:6379/0")
        original_get_store = chat_async.get_notification_store
        original_route = chat_async.route_with_cost
        original_apply_async = chat_async.run_orchestrator_task.apply_async
        original_compute = __import__("app.core.query_priority_scorer", fromlist=["compute_priority"]).compute_priority
        original_job_store = chat_async.get_long_running_job_store

        class FakeJobStore:
            def create_job(self, **kwargs):
                return kwargs

        def fake_compute_priority(**kwargs):
            return SimpleNamespace(
                score=4.2,
                queue="agent",
                breakdown=SimpleNamespace(to_dict=lambda: {"final_score": 4.2}),
                to_celery_kwargs=lambda: {"queue": "agent", "priority": 4, "routing_key": "agent"},
            )

        try:
            chat_async.get_notification_store = lambda: notification_store
            chat_async.get_long_running_job_store = lambda: FakeJobStore()
            chat_async.route_with_cost = lambda query, domain_hint: SimpleNamespace(tier=SimpleNamespace(value="simple"))
            chat_async.run_orchestrator_task.apply_async = lambda *, kwargs, **celery_kwargs: SimpleNamespace(id="task-queued-1")
            __import__("app.core.query_priority_scorer", fromlist=["compute_priority"]).compute_priority = fake_compute_priority

            http_request = Request({
                "type": "http",
                "method": "POST",
                "path": "/api/v1/chat/master-data-async",
                "headers": [(b"x-user-id", b"user-1")],
            })
            http_request.state.session_id = "sess-1"

            response = await chat_async.submit_orchestrator_task(
                chat_async.ChatRequest(query="vendor payment terms", user_role="AP_CLERK"),
                http_request,
            )

            self.assertEqual(response.task_id, "task-queued-1")
            summary = notification_store.get_summary(user_id="user-1")
            self.assertEqual(summary["unread"], 1)
            self.assertEqual(notification_store.list_notifications(user_id="user-1")[0]["title"], "Agent task queued")
        finally:
            chat_async.get_notification_store = original_get_store
            chat_async.get_long_running_job_store = original_job_store
            chat_async.route_with_cost = original_route
            chat_async.run_orchestrator_task.apply_async = original_apply_async
            __import__("app.core.query_priority_scorer", fromlist=["compute_priority"]).compute_priority = original_compute


if __name__ == "__main__":
    unittest.main()
