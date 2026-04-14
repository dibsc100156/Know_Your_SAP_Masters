"""
chat_async.py — Celery-backed Async Chat Endpoints
================================================
Two modes for the orchestrator:

1. SYNC (original): run_agent_loop() called directly in request thread.
   Simple, but blocks the FastAPI worker — limits concurrency.

2. ASYNC (new): run_orchestrator_task submitted to Celery.
   FastAPI is always free to accept new requests.
   Client polls GET /tasks/{task_id} or uses SSE.

We keep BOTH endpoints:
   POST /chat/master-data          → sync (unchanged, for backward compat)
   POST /chat/master-data-async    → async (Celery, for production scale)
   GET  /tasks/{task_id}          → poll task result
   GET  /tasks/{task_id}/status   → lightweight status check
   DELETE /tasks/{task_id}        → revoke / cancel
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Query,
)
from pydantic import BaseModel, Field

from app.agents.orchestrator import run_agent_loop
from app.core.security import security_mesh
from app.workers.celery_app import celery_app_instance as celery_app
from app.workers.orchestrator_tasks import (
    run_orchestrator_task,
    get_task_result,
    AsyncResultNotReadyError,
)
from app.core.eval_alerting import EvalAlertMonitor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# ── Shared Models ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., description="Natural language question about SAP master data")
    domain: str = Field(default="auto", description="Routing domain")
    user_role: str = Field(default="AP_CLERK", description="SAP role key")


class TaskSubmitResponse(BaseModel):
    task_id: str = Field(..., description="Celery task UUID — poll GET /tasks/{task_id}")
    status: str = Field(default="PENDING", description="Initial task status")
    message: str = Field(default="Query submitted. Poll GET /tasks/{task_id} for result.")
    estimated_wait_s: Optional[float] = Field(
        default=None,
        description="Estimated wait time in seconds (based on query complexity hint)"
    )
    poll_after_s: float = Field(default=1.0, description="Recommended poll interval")


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str          # PENDING | STARTED | SUCCESS | FAILURE | RETRY
    ready: bool
    result: Optional[dict] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


# ── Async Submit Endpoint ──────────────────────────────────────────────────────

@router.post(
    "/master-data-async",
    response_model=TaskSubmitResponse,
    status_code=202,
    summary="Submit query to Celery worker queue (async)",
    description=(
        "Submits the query to the Celery agent worker fleet and returns immediately "
        "with a task_id. Poll GET /tasks/{task_id} for the result. "
        "Estimated latency: 2-30s depending on query complexity."
    ),
)
async def submit_orchestrator_task(request: ChatRequest):
    """
    ASYNC submission endpoint.

    Flow:
        1. Validate role
        2. Submit run_orchestrator_task to RabbitMQ
        3. Return task_id immediately (HTTP 202)
        4. Client polls GET /tasks/{task_id}
    """
    # Validate role
    try:
        security_mesh.get_context(request.user_role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Estimate queue wait (rough heuristic based on query signals)
    # Complex indicators: cross_module, temporal, QM semantic, negotiation
    complexity_indicators = sum([
        any(k in request.query.lower() for k in ["fy", "fiscal", "trend", "last year", "quarterly"]),
        any(k in request.query.lower() for k in ["vendor", "customer", "material", "cross"]),
        any(k in request.query.lower() for k in ["negotiation", "brief", "clv", "churn"]),
        any(k in request.query.lower() for k in ["quality", "inspection", "qm", "defect"]),
    ])
    estimated_wait = 2.0 + (complexity_indicators * 3.0)  # 2-14s rough estimate

    try:
        # .delay() returns AsyncResult — task is already queued in RabbitMQ
        async_result = run_orchestrator_task.delay(
            query=request.query,
            user_role=request.user_role,
            domain=request.domain,
        )
        task_id = async_result.id

        logger.info(
            f"[AsyncChat] task_id={task_id} submitted "
            f"query='{request.query[:50]}...' role={request.user_role}"
        )

        return TaskSubmitResponse(
            task_id=task_id,
            status="PENDING",
            message=(
                f"Query queued. Poll GET /tasks/{task_id} for result. "
                f"Or subscribe to ws://.../tasks/{task_id}/stream for SSE."
            ),
            estimated_wait_s=estimated_wait,
            poll_after_s=1.0,
        )

    except Exception as e:
        logger.exception(f"[AsyncChat] Failed to submit task: {e}")
        raise HTTPException(
            status_code=503,
            detail=(
                f"Broker unreachable. Try the sync endpoint "
                f"POST /chat/master-data as fallback. Error: {str(e)}"
            ),
        )


# ── Task Result Polling Endpoint ─────────────────────────────────────────────────

@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Poll Celery task result",
    description="Poll for a previously submitted task result. Use exponential backoff.",
)
async def get_task_result_endpoint(
    task_id: str,
    timeout: float = Query(
        default=0.0,
        ge=0.0,
        le=120.0,
        description="Wait up to N seconds for result (0 = non-blocking)"
    ),
):
    """
    Poll for task completion.

    timeout > 0: blocks up to N seconds (long-polling)
    timeout = 0: non-blocking — raises 202 if task not ready
    """
    try:
        result = get_task_result(task_id, timeout=timeout)
        return TaskStatusResponse(
            task_id=task_id,
            status="SUCCESS",
            ready=True,
            result=result,
            execution_time_ms=result.get("execution_time_ms"),
        )

    except AsyncResultNotReadyError:
        # Task is running but not done — return 202 Accepted
        from celery.result import AsyncResult
        ar = AsyncResult(task_id, app=celery_app)
        return TaskStatusResponse(
            task_id=task_id,
            status=ar.status,   # PENDING | STARTED | RETRY
            ready=False,
        )

    except Exception as e:
        logger.error(f"[TaskPoll] task_id={task_id} error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Task Status (lightweight) ─────────────────────────────────────────────────

@router.get(
    "/tasks/{task_id}/status",
    summary="Lightweight task status (no result fetch)",
    tags=["tasks"],
)
async def get_task_status(task_id: str):
    """
    Lightweight status check — does NOT fetch the result from Redis.
    Fastest option for the frontend polling loop.
    """
    from celery.result import AsyncResult
    try:
        ar = AsyncResult(task_id, app=celery_app)
        return {
            "task_id": task_id,
            "status": ar.status,
            "ready": ar.ready(),
            "successful": ar.successful() if ar.ready() else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Task Cancellation ───────────────────────────────────────────────────────────

@router.delete(
    "/tasks/{task_id}",
    summary="Revoke and cancel a running task",
    tags=["tasks"],
)
async def revoke_task(task_id: str, terminate: bool = Query(default=False)):
    """
    Revoke a running or queued task.

    terminate=True: SIGKILL the worker process (hard kill)
    terminate=False: send SIGTERM to graceful shutdown (soft kill)

    Note: Celery revoke is best-effort — the task may already be running.
    """
    from celery.result import AsyncResult
    try:
        ar = AsyncResult(task_id, app=celery_app)
        ar.revoke(terminate=terminate)
        logger.info(f"[TaskRevoke] task_id={task_id} terminate={terminate}")
        return {
            "task_id": task_id,
            "status": "REVOKED",
            "message": (
                "Task revocation requested. "
                "It may still complete if already in final execution stages."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── SSE Streaming Endpoint (WebSocket upgrade alternative) ───────────────────────

@router.websocket("/tasks/{task_id}/stream")
async def task_result_stream(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint — streams the result when ready.
    Eliminates polling overhead for the client.

    Client:
        ws = WebSocket()
        await ws.connect(f"/ws/tasks/{task_id}/stream")
        # Receive status updates every 0.5s until ready
        while True:
            msg = await ws.receive_json()
            if msg.get("ready"):
                break
    """
    await websocket.accept()

    try:
        from celery.result import AsyncResult
        ar = AsyncResult(task_id, app=celery_app)

        # Poll with small sleep intervals until ready
        poll_interval = 0.5   # seconds between status pings
        max_wait = 300.0       # 5 min hard cap
        elapsed = 0.0

        while not ar.ready() and elapsed < max_wait:
            await websocket.send_json({
                "task_id": task_id,
                "status": ar.status,
                "ready": False,
                "elapsed_s": round(elapsed, 1),
            })
            # Sleep before next poll — don't busy-wait
            import asyncio
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # Task is now ready
        if ar.successful():
            result = ar.result
            await websocket.send_json({
                "task_id": task_id,
                "status": "SUCCESS",
                "ready": True,
                "result": result,
            })
        elif ar.failed():
            await websocket.send_json({
                "task_id": task_id,
                "status": "FAILURE",
                "ready": True,
                "error": str(ar.result),
            })
        else:
            await websocket.send_json({
                "task_id": task_id,
                "status": ar.status,
                "ready": ar.ready(),
            })

    except WebSocketDisconnect:
        logger.info(f"[WSTaskStream] task_id={task_id} client disconnected")
    except Exception as e:
        logger.error(f"[WSTaskStream] task_id={task_id} error: {e}")
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Health Check (broker + Redis reachability) ─────────────────────────────────

@router.get(
    "/health/queue",
    summary="Queue health check",
    tags=["system"],
)
async def queue_health():
    """
    Fast liveness/readiness probe for load balancers and k8s.
    Checks: RabbitMQ reachable + Redis reachable.
    Does NOT check if a task is running.
    """
    from app.workers.celery_app import health_check_task

    try:
        # Send a health_check_task and wait 3s for result
        result = health_check_task.apply_async()
        health = result.get(timeout=3.0)
        return {
            "status": "ok",
            **health,
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(e),
                "broker_url": celery_app.conf.broker_url.split("@")[-1] if "@" in celery_app.conf.broker_url else "configured",
            },
        )


# ── Eval Alerting Endpoints ───────────────────────────────────────────────────

@router.get(
    "/alerts",
    summary="Active eval alerts",
    tags=["system"],
)
async def get_eval_alerts():
    """
    Returns all unresolved eval alerts (benchmark regressions).
    Frontend polls this every ~30s to show notification badges.
    """
    monitor = EvalAlertMonitor()
    alerts = monitor.get_active_alerts()
    summary = monitor.get_alert_summary()
    last_run = monitor.get_last_run()
    return {
        "alerts": alerts,
        "summary": summary,
        "last_run": last_run,
    }


@router.delete(
    "/alerts/{alert_id}",
    summary="Resolve an alert",
    tags=["system"],
)
async def resolve_alert(alert_id: str):
    """
    Acknowledge and resolve a specific alert.
    Called when the frontend user has seen and dismissed the alert.
    """
    monitor = EvalAlertMonitor()
    success = monitor.resolve_alert(alert_id)
    if success:
        return {"status": "resolved", "alert_id": alert_id}
    raise HTTPException(status_code=404, detail="Alert not found")


@router.delete(
    "/alerts",
    summary="Clear all resolved alerts",
    tags=["system"],
)
async def clear_resolved_alerts():
    """Delete all resolved alerts from Redis."""
    monitor = EvalAlertMonitor()
    monitor.clear_resolved()
    return {"status": "cleared"}
