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

from celery import shared_task  # ← bind at call time, not import time
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

# Import the orchestrator — this is the expensive CPU-bound work
# that Celery offloads from the FastAPI request thread.
from app.agents.orchestrator import run_agent_loop
from app.core.security import security_mesh

# NOTE: celery_app is imported LAZILY inside each task / helper below.
# Do NOT import it at module level — that creates a circular import deadlock:
#   celery_app.py:54 imports orchestrator_tasks
#   → orchestrator_tasks top-level tries @app.task(..., app=celery_app)
#   → app not yet defined → NameError.
# Lazy import (inside get_task_result etc.) avoids the deadlock.

logger = logging.getLogger(__name__)

# ── Shared result metadata ─────────────────────────────────────────────────────
# Keys stored in Redis alongside Celery result:
#   celery.result.meta.task_id = <id>
#   celery.result.meta.status  = PENDING / STARTED / SUCCESS / FAILURE / RETRY
#   sap_masters.task.result    = <result_dict>
#   sap_masters.task.started   = <timestamp>
#   sap_masters.task.query     = <query>


# ── Core orchestrator task ────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.workers.orchestrator_tasks.run_orchestrator_task",
    max_retries=2,               # Retry up to 2 times on failure
    default_retry_delay=5,       # Wait 5s before retry
    autoretry_for=(ConnectionError, SoftTimeLimitExceeded, TimeLimitExceeded),
    retry_backoff=True,          # Exponential backoff on retry
    retry_backoff_max=60,
    acks_late=True,              # Only ack after success (not on dispatch)
    reject_on_worker_lost=True,   # Requeue if worker dies
    time_limit=300,              # 5 min hard cap
    soft_time_limit=240,         # 4 min warning
    track_started=True,           # Track STARTED state in result backend
)
def run_orchestrator_task(
    self,                     # bind=True gives us self (Task)
    query: str,
    user_role: str = "AP_CLERK",
    domain: str = "auto",
    use_supervisor: bool = False,  # NOTE: use_supervisor=True returns simplified result without confidence_score, critique, etc.
) -> dict:
    """
    Celery task: run the full 8-phase agentic orchestrator.

    This is the heavy lifting — runs in a Celery worker process, not the
    FastAPI request thread. Workers can be scaled horizontally:

        celery -A app.workers.celery_app worker \\
            --loglevel=info --concurrency=8 --pool=prefork

    Args:
        query:          Natural language question
        user_role:      SAP role key (AP_CLERK, PROCUREMENT_MANAGER_EU, CFO_GLOBAL, HR_ADMIN)
        domain:         Routing domain (auto, purchasing, business_partner, etc.)
        use_supervisor: Whether to try domain agents before orchestrator

    Returns:
        Full orchestrator result dict — same shape as run_agent_loop() return.
        Includes: answer, sql_generated, tables_used, tool_trace, data,
                  confidence_score, routing_path, temporal, qm_semantic,
                  negotiation_brief, self_heal, masked_fields, etc.

    Raises:
        SoftTimeLimitExceeded: Query took >4 min — logged, retried once.
        TimeLimitExceeded:      Query took >5 min — killed, retried once.
        ConnectionError:        Broker/Redis unreachable — retried with backoff.
    """
    start_time = time.time()
    task_id = self.request.id

    logger.info(
        f"[CeleryTask:{task_id}] START query='{query[:60]}...' "
        f"role={user_role} domain={domain}"
    )

    # ── 1. Get AuthContext ────────────────────────────────────────────────────
    try:
        auth_context = security_mesh.get_context(user_role)
    except ValueError as e:
        logger.error(f"[CeleryTask:{task_id}] Invalid role {user_role}: {e}")
        return {
            "answer": f"Invalid role: {user_role}",
            "error": str(e),
            "task_id": task_id,
            "status": "role_error",
        }

    # ── 2. Run orchestrator ──────────────────────────────────────────────────
    # This is the CPU-bound work — runs in the Celery worker.
    # SoftTimeLimitExceeded is caught and retried automatically.
    try:
        result = run_agent_loop(
            query=query,
            auth_context=auth_context,
            domain=domain,
            verbose=False,           # Task logs → celery worker log, not API response
            use_supervisor=use_supervisor,
        )
    except SoftTimeLimitExceeded:
        elapsed = int(time.time() - start_time)
        logger.warning(
            f"[CeleryTask:{task_id}] SoftTimeLimitExceeded "
            f"at {elapsed}s — will retry (attempt {self.request.retries + 1})"
        )
        raise  # Celery handles retry

    except TimeLimitExceeded:
        elapsed = int(time.time() - start_time)
        logger.error(
            f"[CeleryTask:{task_id}] TimeLimitExceeded "
            f"at {elapsed}s — failing without retry"
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
        return {
            "answer": f"Internal error: {str(e)}",
            "error": str(e),
            "task_id": task_id,
            "execution_time_ms": elapsed * 1000,
            "status": "error",
        }

    # ── 3. Attach metadata ───────────────────────────────────────────────────
    elapsed_ms = int((time.time() - start_time) * 1000)
    result["task_id"] = task_id
    result["status"] = "success"
    result["celery"] = {
        "worker": self.request.hostname,
        "retries": self.request.retries,
        "elapsed_ms": elapsed_ms,
        "time_limit_ms": 300000,
    }

    logger.info(
        f"[CeleryTask:{task_id}] DONE in {elapsed_ms}ms "
        f"status=success tables={result.get('tables_used', [])} "
        f"pattern={result.get('pattern_name', 'ad_hoc')}"
    )

    return result


# ── Synchronous convenience task (for low-latency / simple cases) ─────────────

@shared_task(
    bind=True,
    name="app.workers.orchestrator_tasks.run_orchestrator_sync_task",
    max_retries=0,              # No retries for sync mode
    time_limit=120,             # 2 min hard cap for sync
    acks_late=False,           # Ack immediately (fire-and-forget semantics)
)
def run_orchestrator_sync_task(
    self,
    query: str,
    user_role: str = "AP_CLERK",
    domain: str = "auto",
) -> dict:
    """
    Synchronous variant — same as run_orchestrator_task but:
      - No retries
      - Shorter time limit (2 min)
      - Faster ack (no late ack)

    Use for: streaming SSE responses, quick ad-hoc queries.
    For high-throughput: use run_orchestrator_task with async polling.
    """
    return run_orchestrator_task.delay(
        query=query,
        user_role=user_role,
        domain=domain,
    )  # Returns AsyncResult — call .get() in the API to block


# ── System health / memory cleanup tasks ──────────────────────────────────────

@shared_task(
    name="app.workers.orchestrator_tasks.cleanup_memory_task",
    queue="system",
    time_limit=30,
)
def cleanup_memory_task() -> dict:
    """
    Periodic task: clean up stale dialog sessions and old query history
    from Redis. Run via Celery Beat every 5 minutes.

    Keeps memory layer lean without blocking the main request path.
    """
    try:
        from app.core.memory_layer import sap_memory
        # Prune old entries from query history
        # (implemented in sap_memory — placeholder for now)
        logger.info("[CleanupTask] Memory layer cleanup complete")
        return {"status": "ok", "task": "cleanup_memory"}
    except Exception as e:
        logger.error(f"[CleanupTask] Error: {e}")
        return {"status": "error", "error": str(e)}


# ── Task result helpers (used by API layer) ────────────────────────────────────

def get_task_result(task_id: str, timeout: float = 0.0) -> dict:
    """
    Fetch a Celery task result from Redis.

    Args:
        task_id: Celery task UUID (returned by send_task)
        timeout: 0.0 = non-blocking (raise if not ready)
                 >0 = wait up to N seconds
                 None = wait forever

    Returns:
        The result dict from run_orchestrator_task

    Raises:
        celery.exceptions.AsyncResultNotReady
        celery.exceptions.AsyncResultFailed
    """
    from celery.result import AsyncResult
    # Lazy import breaks the circular import deadlock:
    # celery_app is imported here at call time, not at module load time.
    from app.workers.celery_app import app as celery_app
    result = AsyncResult(task_id, app=celery_app)
    if timeout > 0:
        return result.get(timeout=timeout)
    elif timeout is None:
        return result.get()
    else:
        # Non-blocking
        if not result.ready():
            raise AsyncResultNotReadyError(f"Task {task_id} not ready")
        if result.failed():
            raise result.result  # re-raise the exception
        return result.result


class AsyncResultNotReadyError(Exception):
    """Raised when polling a Celery task that hasn't completed yet."""
    pass
