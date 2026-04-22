import unittest
from types import SimpleNamespace

from app.api.endpoints import chat_async
from app.core.long_running_jobs import LongRunningJobStore


class LongRunningJobStoreTests(unittest.TestCase):
    def test_create_update_and_list_job(self):
        store = LongRunningJobStore(redis_url="redis://invalid:6379/0")
        store.create_job(
            task_id="task-1",
            query="vendor payment terms",
            user_role="AP_CLERK",
            user_id="user-1",
            session_id="sess-1",
            long_running=True,
            payload={"query": "vendor payment terms", "user_role": "AP_CLERK", "long_running": True},
        )
        store.mark_started("task-1", worker="worker@host")
        store.mark_completed("task-1", {"answer": "ok", "status": "success", "execution_time_ms": 10})

        job = store.get_job("task-1")
        self.assertEqual(job["status"], "success")
        self.assertEqual(store.list_jobs(user_id="user-1")[0]["task_id"], "task-1")


class ResumeTaskEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_task_resubmits_from_durable_payload(self):
        store = LongRunningJobStore(redis_url="redis://invalid:6379/0")
        store.create_job(
            task_id="old-task",
            query="vendor payment terms",
            user_role="AP_CLERK",
            user_id="user-1",
            session_id="sess-1",
            long_running=True,
            queue_target="longrun",
            payload={
                "query": "vendor payment terms",
                "user_role": "AP_CLERK",
                "domain": "auto",
                "urgency": "normal",
                "user_id": "user-1",
                "session_id": "sess-1",
                "long_running": True,
            },
        )
        store.mark_failed("old-task", "boom")

        original_jobs = chat_async.get_long_running_job_store
        original_notifications = chat_async.get_notification_store
        original_long_apply = chat_async.run_orchestrator_long_task.apply_async

        class FakeNotifications:
            def create_notification(self, **kwargs):
                return kwargs

        try:
            chat_async.get_long_running_job_store = lambda: store
            chat_async.get_notification_store = lambda: FakeNotifications()
            chat_async.run_orchestrator_long_task.apply_async = lambda *, kwargs, **celery_kwargs: SimpleNamespace(id="new-task")

            result = await chat_async.resume_task("old-task")

            self.assertEqual(result["task_id"], "new-task")
            resumed = store.get_job("new-task")
            self.assertEqual(resumed["resubmitted_from"], "old-task")
            self.assertTrue(resumed["long_running"])
        finally:
            chat_async.get_long_running_job_store = original_jobs
            chat_async.get_notification_store = original_notifications
            chat_async.run_orchestrator_long_task.apply_async = original_long_apply


if __name__ == "__main__":
    unittest.main()
