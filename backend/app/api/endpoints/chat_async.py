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
    Request,
    WebSocket,
    WebSocketDisconnect,
    Query,
)
from pydantic import BaseModel, Field

from app.agents.orchestrator import run_agent_loop
from app.core.agent_notifications import get_notification_store
from app.core.eval_alerting import EvalAlertMonitor
from app.core.long_running_jobs import get_long_running_job_store
from app.core.security import security_mesh
from app.core.router_cost_tracker import route_with_cost
from app.workers.celery_app import celery_app_instance as celery_app
from app.workers.orchestrator_tasks import (
    run_orchestrator_long_task,
    run_orchestrator_task,
    get_task_result,
    AsyncResultNotReadyError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# ── Shared Models ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., description="Natural language question about SAP master data")
    domain: str = Field(default="auto", description="Routing domain")
    user_role: str = Field(default="AP_CLERK", description="SAP role key")
    urgency: str = Field(default="normal", description="Query urgency: critical | high | normal | low")
    contract_type: str = Field(default="standard", description="SLA: enterprise | premium | standard")
    long_running: bool = Field(default=False, description="Route to long-running worker infrastructure (6h queue)")


class TaskSubmitResponse(BaseModel):
    task_id: str = Field(..., description="Celery task UUID — poll GET /tasks/{task_id}")
    status: str = Field(default="PENDING", description="Initial task status")
    message: str = Field(default="Query submitted. Poll GET /tasks/{task_id} for result.")
    estimated_wait_s: Optional[float] = Field(
        default=None,
        description="Estimated wait time in seconds (based on query complexity hint)"
    )
    poll_after_s: float = Field(default=1.0, description="Recommended poll interval")
    priority_score: float = Field(default=None, description="Phase 22: Urgency x Role-Authority score")
    queue_target: str = Field(default=None, description="Phase 22: Celery queue targeted")
    priority_breakdown: Optional[dict] = Field(default=None, description="Phase 22: Score breakdown")
    long_running: bool = Field(default=False, description="Whether the task was routed to long-running infrastructure")


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str          # PENDING | STARTED | SUCCESS | FAILURE | RETRY
    ready: bool
    result: Optional[dict] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


def _resolve_request_identity(http_request: Optional[Request], user_role: str) -> tuple[Optional[str], Optional[str]]:
    session_id = getattr(getattr(http_request, "state", None), "session_id", None) if http_request else None
    user_id = None
    if http_request is not None:
        user_id = http_request.headers.get("X-User-ID") or session_id or f"user:{user_role.lower()}"
    return user_id, session_id


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
async def submit_orchestrator_task(request: ChatRequest, http_request: Request):
    """Submit a query to normal or long-running Celery infrastructure."""
    try:
        security_mesh.get_context(request.user_role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    complexity_indicators = sum([
        any(k in request.query.lower() for k in ["fy", "fiscal", "trend", "last year", "quarterly"]),
        any(k in request.query.lower() for k in ["vendor", "customer", "material", "cross"]),
        any(k in request.query.lower() for k in ["negotiation", "brief", "clv", "churn"]),
        any(k in request.query.lower() for k in ["quality", "inspection", "qm", "defect"]),
    ])
    estimated_wait = 2.0 + (complexity_indicators * 3.0)
    user_id, session_id = _resolve_request_identity(http_request, request.user_role)

    try:
        routing = route_with_cost(query=request.query, domain_hint=request.domain)

        from app.core.query_priority_scorer import compute_priority
        priority_result = compute_priority(
            query=request.query,
            user_role=request.user_role,
            routing_tier=routing.tier.value,
            domain=request.domain,
            urgency=request.urgency,
            contract_type=request.contract_type,
            is_critical_report=request.urgency.lower() == "critical",
            user_id=user_id,
        )
        celery_kwargs = priority_result.to_celery_kwargs()
        task_runner = run_orchestrator_long_task if request.long_running else run_orchestrator_task
        if request.long_running:
            celery_kwargs["queue"] = "longrun"
            celery_kwargs["routing_key"] = "longrun"

        task_payload = {
            "query": request.query,
            "user_role": request.user_role,
            "domain": request.domain,
            "urgency": request.urgency,
            "priority_score": round(priority_result.score, 3),
            "queue_target": "longrun" if request.long_running else priority_result.queue,
            "priority_breakdown": priority_result.breakdown.to_dict(),
            "routing_tier": routing.tier.value,
            "user_id": user_id,
            "session_id": session_id,
            "long_running": request.long_running,
        }

        async_result = task_runner.apply_async(kwargs=task_payload, **celery_kwargs)
        task_id = async_result.id

        get_long_running_job_store().create_job(
            task_id=task_id,
            query=request.query,
            user_role=request.user_role,
            domain=request.domain,
            urgency=request.urgency,
            user_id=user_id,
            session_id=session_id,
            queue_target=task_payload["queue_target"],
            routing_tier=routing.tier.value,
            long_running=request.long_running,
            payload=task_payload,
        )
        get_notification_store().create_notification(
            title="Agent task queued",
            message=f"Task {task_id[:8]} queued on {task_payload['queue_target']}.",
            category="task",
            severity="info",
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            dedup_key=f"queued:{task_id}",
            metadata={"status": "queued", "long_running": request.long_running},
        )

        logger.info(
            f"[AsyncChat] task_id={task_id} submitted "
            f"query='{request.query[:50]}...' role={request.user_role} long_running={request.long_running}"
        )

        return TaskSubmitResponse(
            task_id=task_id,
            status="PENDING",
            message=(
                f"Query queued on {task_payload['queue_target']} queue. "
                f"Poll GET /tasks/{task_id} for result."
            ),
            estimated_wait_s=estimated_wait,
            poll_after_s=1.0,
            priority_score=round(priority_result.score, 3),
            queue_target=task_payload["queue_target"],
            priority_breakdown=priority_result.breakdown.to_dict(),
            long_running=request.long_running,
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
    """Lightweight status check plus durable job metadata when available."""
    from celery.result import AsyncResult
    try:
        ar = AsyncResult(task_id, app=celery_app)
        return {
            "task_id": task_id,
            "status": ar.status,
            "ready": ar.ready(),
            "successful": ar.successful() if ar.ready() else None,
            "job": get_long_running_job_store().get_job(task_id),
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
    """Revoke a running or queued task and mark durable state accordingly."""
    from celery.result import AsyncResult
    try:
        ar = AsyncResult(task_id, app=celery_app)
        ar.revoke(terminate=terminate)
        job = get_long_running_job_store().request_cancel(task_id)
        get_long_running_job_store().mark_cancelled(task_id)
        if job:
            get_notification_store().create_notification(
                title="Agent task cancelled",
                message=f"Task {task_id[:8]} cancellation was requested.",
                category="task",
                severity="warning",
                user_id=job.get("user_id"),
                session_id=job.get("session_id"),
                task_id=task_id,
                dedup_key=f"cancelled:{task_id}",
                metadata={"status": "cancelled"},
            )
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


@router.get("/notifications", tags=["tasks"])
async def list_notifications(
    http_request: Request,
    user_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
):
    req_user_id, req_session_id = _resolve_request_identity(http_request, "ap_clerk")
    return {
        "notifications": get_notification_store().list_notifications(
            user_id=user_id or req_user_id,
            session_id=session_id or req_session_id,
            unread_only=unread_only,
            limit=limit,
        )
    }


@router.get("/notifications/summary", tags=["tasks"])
async def notification_summary(
    http_request: Request,
    user_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
):
    req_user_id, req_session_id = _resolve_request_identity(http_request, "ap_clerk")
    return get_notification_store().get_summary(
        user_id=user_id or req_user_id,
        session_id=session_id or req_session_id,
    )


@router.post("/notifications/{notification_id}/read", tags=["tasks"])
async def mark_notification_read(notification_id: str):
    if get_notification_store().mark_read(notification_id):
        return {"status": "ok", "notification_id": notification_id}
    raise HTTPException(status_code=404, detail="Notification not found")


@router.post("/notifications/read-all", tags=["tasks"])
async def mark_all_notifications_read(
    http_request: Request,
    user_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
):
    req_user_id, req_session_id = _resolve_request_identity(http_request, "ap_clerk")
    count = get_notification_store().mark_all_read(
        user_id=user_id or req_user_id,
        session_id=session_id or req_session_id,
    )
    return {"status": "ok", "updated": count}


@router.get("/jobs", tags=["tasks"])
async def list_jobs(
    http_request: Request,
    user_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    req_user_id, req_session_id = _resolve_request_identity(http_request, "ap_clerk")
    return {
        "jobs": get_long_running_job_store().list_jobs(
            user_id=user_id or req_user_id,
            session_id=session_id or req_session_id,
            limit=limit,
        )
    }


@router.get("/jobs/{task_id}", tags=["tasks"])
async def get_job(task_id: str):
    job = get_long_running_job_store().get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/tasks/{task_id}/resume", tags=["tasks"])
async def resume_task(task_id: str):
    job = get_long_running_job_store().get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") in {"queued", "started", "retry"}:
        raise HTTPException(status_code=409, detail="Task is still active")

    payload = dict(job.get("payload") or {})
    if not payload:
        raise HTTPException(status_code=400, detail="Job does not have resumable payload")

    payload["long_running"] = bool(job.get("long_running"))
    runner = run_orchestrator_long_task if payload.get("long_running") else run_orchestrator_task
    celery_kwargs = {"queue": "longrun", "routing_key": "longrun"} if payload.get("long_running") else {}
    async_result = runner.apply_async(kwargs=payload, **celery_kwargs)
    new_task_id = async_result.id

    get_long_running_job_store().create_job(
        task_id=new_task_id,
        query=job.get("query", payload.get("query", "")),
        user_role=job.get("user_role", payload.get("user_role", "AP_CLERK")),
        domain=job.get("domain", payload.get("domain", "auto")),
        urgency=job.get("urgency", payload.get("urgency", "normal")),
        user_id=job.get("user_id"),
        session_id=job.get("session_id"),
        queue_target="longrun" if payload.get("long_running") else job.get("queue_target"),
        routing_tier=job.get("routing_tier"),
        long_running=bool(payload.get("long_running")),
        payload={**payload, "session_id": job.get("session_id"), "user_id": job.get("user_id")},
        resubmitted_from=task_id,
    )
    get_notification_store().create_notification(
        title="Agent task resumed",
        message=f"Task {task_id[:8]} was resumed as {new_task_id[:8]}.",
        category="task",
        severity="info",
        user_id=job.get("user_id"),
        session_id=job.get("session_id"),
        task_id=new_task_id,
        dedup_key=f"resumed:{task_id}:{new_task_id}",
        metadata={"status": "queued", "resubmitted_from": task_id},
    )
    return {"task_id": new_task_id, "resubmitted_from": task_id, "status": "PENDING"}


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
