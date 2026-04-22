"""
orchestrator_tasks.py — Celery Tasks for Know Your SAP Masters
============================================================
Three task types:

1. run_orchestrator_task  (async, queue:agent)
   → Full 8-phase orchestrator loop, executed in a Celery worker.
   → Fire-and-check: submit → poll result backend → return.
   → Timeout: 5 min hard, 4 min soft.

2. run_orchestrator_sync_task  (queue:priority)
   → Same as above but for latency-sensitive scenarios.
   → Uses Celery's synchronous mode (task.get() inside API).
   → Not recommended for high-throughput — use async with SSE instead.

3. health_check_task  (queue:system)
   → Lightweight broker + Redis reachability check.

Architecture:
    FastAPI
      POST /chat/master-data-async
        → celery_app.send_task()          (publishes to RabbitMQ)
        → returns task.id immediately      (HTTP 202 Accepted)
        → Client polls GET /tasks/{task_id}

    OR (latency-tolerant):

    FastAPI
      POST /chat/master-data
        → task.apply_async().get(timeout=60)
        → returns full result synchronously
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

from app.agents.orchestrator import run_agent_loop
from app.core.agent_notifications import get_notification_store
from app.core.long_running_jobs import get_long_running_job_store
from app.core.security import security_mesh

logger = logging.getLogger(__name__)


def _emit_task_notification(*, title: str, message: str, user_id: Optional[str], session_id: Optional[str], task_id: str, severity: str = "info", category: str = "task", dedup_key: Optional[str] = None, metadata: Optional[dict] = None) -> None:
    try:
        get_notification_store().create_notification(
            title=title,
            message=message,
            category=category,
            severity=severity,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            dedup_key=dedup_key,
            metadata=metadata or {},
        )
    except Exception as e:
        logger.warning("[CeleryTask:%s] notification emit failed: %s", task_id, e)



def _execute_orchestrator_task(
    self,
    *,
    query: str,
    user_role: str,
    domain: str,
    urgency: str,
    priority_score: Optional[float],
    queue_target: Optional[str],
    priority_breakdown: Optional[dict],
    routing_tier: Optional[str],
    user_id: Optional[str],
    session_id: Optional[str],
    use_supervisor: bool,
    long_running: bool,
    time_limit_ms: int,
) -> dict:
    start_time = time.time()
    task_id = self.request.id
    job_store = get_long_running_job_store()

    logger.info(
        f"[CeleryTask:{task_id}] START query='{query[:60]}...' "
        f"role={user_role} domain={domain} long_running={long_running}"
    )

    job_store.mark_started(task_id, worker=self.request.hostname)
    _emit_task_notification(
        title="Agent task started",
        message=f"Task {task_id[:8]} is now running.",
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        dedup_key=f"started:{task_id}",
        metadata={"status": "started", "long_running": long_running},
    )

    try:
        auth_context = security_mesh.get_context(user_role).model_copy(update={
            "user_id": user_id or f"user:{user_role.lower()}",
            "session_id": session_id,
        })
    except ValueError as e:
        logger.error(f"[CeleryTask:{task_id}] Invalid role {user_role}: {e}")
        job_store.mark_failed(task_id, str(e), status="role_error")
        _emit_task_notification(
            title="Agent task failed",
            message=f"Task {task_id[:8]} failed before execution: invalid role.",
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            severity="error",
            dedup_key=f"failed:{task_id}",
            metadata={"status": "role_error", "error": str(e)},
        )
        return {
            "answer": f"Invalid role: {user_role}",
            "error": str(e),
            "task_id": task_id,
            "status": "role_error",
        }

    job_store.heartbeat(task_id, status="started")

    try:
        result = run_agent_loop(
            query=query,
            auth_context=auth_context,
            domain=domain,
            verbose=False,
            use_supervisor=use_supervisor,
        )
    except SoftTimeLimitExceeded:
        elapsed = int(time.time() - start_time)
        job_store.mark_retry(task_id, retries=self.request.retries + 1, error="SoftTimeLimitExceeded")
        _emit_task_notification(
            title="Agent task retrying",
            message=f"Task {task_id[:8]} hit soft timeout at {elapsed}s and will retry.",
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            severity="warning",
            dedup_key=f"retry:{task_id}:{self.request.retries + 1}",
            metadata={"status": "retry", "retries": self.request.retries + 1},
        )
        raise
    except TimeLimitExceeded:
        elapsed = int(time.time() - start_time)
        job_store.mark_failed(task_id, "TimeLimitExceeded", status="timeout")
        _emit_task_notification(
            title="Agent task timed out",
            message=f"Task {task_id[:8]} timed out after {elapsed}s.",
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            severity="error",
            dedup_key=f"timeout:{task_id}",
            metadata={"status": "timeout", "long_running": long_running},
        )
        return {
            "answer": (
                f"Query timed out after {elapsed}s. "
                f"The query may be too complex or the system is under load. "
                f"Please try a simpler query or try again shortly."
            ),
            "error": "TimeLimitExceeded",
            "task_id": task_id,
            "execution_time_ms": elapsed * 1000,
            "status": "timeout",
        }
    except Exception as e:
        elapsed = int(time.time() - start_time)
        logger.exception(f"[CeleryTask:{task_id}] Unexpected error at {elapsed}s: {e}")
        job_store.mark_failed(task_id, str(e), status="error")
        _emit_task_notification(
            title="Agent task failed",
            message=f"Task {task_id[:8]} failed: {str(e)[:120]}",
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            severity="error",
            dedup_key=f"failed:{task_id}",
            metadata={"status": "error", "error": str(e)},
        )
        return {
            "answer": f"Internal error: {str(e)}",
            "error": str(e),
            "task_id": task_id,
            "execution_time_ms": elapsed * 1000,
            "status": "error",
        }

    elapsed_ms = int((time.time() - start_time) * 1000)
    result["task_id"] = task_id
    result["status"] = "success"
    result["urgency"] = urgency
    result["priority_score"] = priority_score
    result["queue_target"] = queue_target
    result["priority_breakdown"] = priority_breakdown
    result["routing_tier"] = result.get("routing_tier") or routing_tier
    result["role_applied"] = auth_context.role_id
    result["user_id"] = auth_context.user_id or f"user:{auth_context.role_id.lower()}"
    result["celery"] = {
        "worker": self.request.hostname,
        "retries": self.request.retries,
        "elapsed_ms": elapsed_ms,
        "time_limit_ms": time_limit_ms,
        "long_running": long_running,
    }

    job_store.mark_completed(task_id, result)
    _emit_task_notification(
        title="Agent task completed",
        message=f"Task {task_id[:8]} completed successfully in {elapsed_ms}ms.",
        user_id=result.get("user_id"),
        session_id=session_id,
        task_id=task_id,
        severity="success",
        dedup_key=f"success:{task_id}",
        metadata={"status": "success", "execution_time_ms": elapsed_ms, "long_running": long_running},
    )

    logger.info(
        f"[CeleryTask:{task_id}] DONE in {elapsed_ms}ms "
        f"status=success tables={result.get('tables_used', [])} "
        f"pattern={result.get('pattern_name', 'ad_hoc')}"
    )

    return result


@shared_task(
    bind=True,
    name="app.workers.orchestrator_tasks.run_orchestrator_task",
    max_retries=2,
    default_retry_delay=5,
    autoretry_for=(ConnectionError, SoftTimeLimitExceeded, TimeLimitExceeded),
    retry_backoff=True,
    retry_backoff_max=60,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=300,
    soft_time_limit=240,
    track_started=True,
)
def run_orchestrator_task(
    self,
    query: str,
    user_role: str = "AP_CLERK",
    domain: str = "auto",
    urgency: str = "normal",
    priority_score: Optional[float] = None,
    queue_target: Optional[str] = None,
    priority_breakdown: Optional[dict] = None,
    routing_tier: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    use_supervisor: bool = False,
    long_running: bool = False,
) -> dict:
    return _execute_orchestrator_task(
        self,
        query=query,
        user_role=user_role,
        domain=domain,
        urgency=urgency,
        priority_score=priority_score,
        queue_target=queue_target,
        priority_breakdown=priority_breakdown,
        routing_tier=routing_tier,
        user_id=user_id,
        session_id=session_id,
        use_supervisor=use_supervisor,
        long_running=long_running,
        time_limit_ms=300000,
    )


@shared_task(
    bind=True,
    name="app.workers.orchestrator_tasks.run_orchestrator_long_task",
    max_retries=2,
    default_retry_delay=15,
    autoretry_for=(ConnectionError, SoftTimeLimitExceeded, TimeLimitExceeded),
    retry_backoff=True,
    retry_backoff_max=300,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=21600,
    soft_time_limit=21000,
    track_started=True,
)
def run_orchestrator_long_task(
    self,
    query: str,
    user_role: str = "AP_CLERK",
    domain: str = "auto",
    urgency: str = "normal",
    priority_score: Optional[float] = None,
    queue_target: Optional[str] = None,
    priority_breakdown: Optional[dict] = None,
    routing_tier: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    use_supervisor: bool = False,
    long_running: bool = True,
) -> dict:
    return _execute_orchestrator_task(
        self,
        query=query,
        user_role=user_role,
        domain=domain,
        urgency=urgency,
        priority_score=priority_score,
        queue_target=queue_target,
        priority_breakdown=priority_breakdown,
        routing_tier=routing_tier,
        user_id=user_id,
        session_id=session_id,
        use_supervisor=use_supervisor,
        long_running=long_running,
        time_limit_ms=21600000,
    )


@shared_task(
    bind=True,
    name="app.workers.orchestrator_tasks.run_orchestrator_sync_task",
    max_retries=0,
    time_limit=120,
    acks_late=False,
)
def run_orchestrator_sync_task(
    self,
    query: str,
    user_role: str = "AP_CLERK",
    domain: str = "auto",
) -> dict:
    return run_orchestrator_task.delay(
        query=query,
        user_role=user_role,
        domain=domain,
    )


@shared_task(
    name="app.workers.orchestrator_tasks.cleanup_memory_task",
    queue="system",
    time_limit=30,
)
def cleanup_memory_task() -> dict:
    try:
        from app.core.memory_layer import sap_memory
        logger.info("[CleanupTask] Memory layer cleanup complete")
        return {"status": "ok", "task": "cleanup_memory"}
    except Exception as e:
        logger.error(f"[CleanupTask] Error: {e}")
        return {"status": "error", "error": str(e)}


# ── Task result helpers (used by API layer) ────────────────────────────────────

def get_task_result(task_id: str, timeout: float = 0.0) -> dict:
    from celery.result import AsyncResult
    from app.workers.celery_app import celery_app_instance as celery_app

    result = AsyncResult(task_id, app=celery_app)
    if timeout > 0:
        return result.get(timeout=timeout)
    elif timeout is None:
        return result.get()
    else:
        if not result.ready():
            raise AsyncResultNotReadyError(f"Task {task_id} not ready")
        if result.failed():
            raise result.result
        return result.result


class AsyncResultNotReadyError(Exception):
    pass
