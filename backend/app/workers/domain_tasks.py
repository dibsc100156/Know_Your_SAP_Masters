"""
domain_tasks.py — Per-Domain Celery Tasks for Swarm Autoscaling
===============================================================
Each domain agent gets its own Celery task, routed to a dedicated queue.
This enables horizontal autoscaling per domain (e.g., more pur_queue workers
during procurement peak hours).

Queue layout:
    pur_queue   → PURAgent      (EKKO, EKPO, EINA, EINE, EORD)
    bp_queue    → BPAgent       (LFA1, KNA1, BUT000, ADRC)
    mm_queue    → MMAgent       (MARA, MARC, MARD, MBEW, MSKA)
    sd_queue    → SDAgent       (VBAK, VBAP, LIKP, KNVL, KONV)
    qm_queue    → QMAgent       (QALS, QMEL, MAPL, QAMV)
    wm_queue    → WMAgent       (LAGP, LQUA, VEKP, MLGT)
    cross_queue → CROSSAgent    (multi-domain JOINs)

Start domain-specific workers:
    # Scale pur_agent pool to 4 processes
    celery -A app.workers.celery_app worker -Q pur_queue --concurrency=4 --hostname=pur@%h

    # Scale all domain queues with separate concurrency
    celery -A app.workers.celery_app worker -Q pur_queue,bp_queue,mm_queue --concurrency=2 --hostname=domain@%h

    # KEDA autoscaling example (kubernetes):
    kedascale func aspnetcore --deployment sapmasters-swarm --name pur-agent \
        --query http://rabbitmq:15672/api/queues/%2F/pur_queue | jq .messages

Usage:
    from app.workers.domain_tasks import run_domain_task

    # Direct call (within a Celery worker — reducer pattern)
    result = run_domain_task.delay(
        agent_name="pur_agent",
        query="vendor open POs over 50000",
        user_role="AP_CLERK",
        tables_hint=["EKKO", "EKPO"],
        run_id="abc-123",
        plan_path="/tmp/plan_abc-123.json",
    )
    # AsyncResult.get() → result dict
"""

from __future__ import annotations

import logging
import time
from typing import Optional, List

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

logger = logging.getLogger(__name__)

# ── Queue mapping ────────────────────────────────────────────────────────────
AGENT_TO_QUEUE = {
    "pur_agent":   "pur_queue",
    "bp_agent":    "bp_queue",
    "mm_agent":    "mm_queue",
    "sd_agent":    "sd_queue",
    "qm_agent":    "qm_queue",
    "wm_agent":    "wm_queue",
    "cross_agent": "cross_queue",
}

QUEUE_ROUTING_KEY = {v: v for v in AGENT_TO_QUEUE.values()}

# ── Per-domain task definitions ──────────────────────────────────────────────

# Each domain task is a thin Celery-shared_task wrapper around DomainAgent.run()
# We use a SINGLE shared task with queue routing to avoid code duplication.
# The agent_name param tells us which DomainAgent to instantiate.


@shared_task(
    bind=True,
    name="app.workers.domain_tasks.run_domain_task",
    max_retries=2,
    default_retry_delay=8,
    autoretry_for=(ConnectionError, SoftTimeLimitExceeded, TimeLimitExceeded),
    retry_backoff=True,
    retry_backoff_max=60,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=240,       # 4 min hard cap per domain agent
    soft_time_limit=200,  # 3.3 min soft cap
    track_started=True,
)
def run_domain_task(
    self,
    agent_name: str,
    query: str,
    user_role: str,
    tables_hint: Optional[List[str]] = None,
    run_id: Optional[str] = None,
    plan_path: Optional[str] = None,
    verbose: bool = False,
) -> dict:
    """
    Celery task that runs a single domain agent's pipeline in an isolated worker.

    Args:
        agent_name:  Which domain agent (e.g. "pur_agent", "bp_agent")
        query:       The user query (passed to the domain agent)
        user_role:   SAP role key for AuthContext
        tables_hint: Optional table hints from planner
        run_id:      Harness run ID (for phase tracking)
        plan_path:   Temp plan state file path (planner writes this)
        verbose:     Print agent reasoning steps

    Returns:
        Domain agent result dict with keys: answer, sql_generated, tables_used,
        tool_trace, data, masked_fields, record_count, validation_passed, etc.
    """
    start_time = time.time()
    task_id = self.request.id
    queue = self.request.delivery_info.get("routing_key", AGENT_TO_QUEUE.get(agent_name, "agent"))

    logger.info(
        f"[DomainTask:{task_id}] START agent={agent_name} queue={queue} "
        f"query='{query[:50]}...' role={user_role}"
    )

    # ── 1. Validate agent name ─────────────────────────────────────────────
    from app.agents.domain_agents import get_domain_agent
    agent = get_domain_agent(agent_name)
    if agent is None:
        logger.error(f"[DomainTask:{task_id}] Unknown agent: {agent_name}")
        return {
            "error": f"Unknown agent: {agent_name}",
            "agent_name": agent_name,
            "status": "agent_not_found",
            "task_id": task_id,
        }

    # ── 2. Build AuthContext ────────────────────────────────────────────────
    try:
        from app.core.security import security_mesh
        auth_context = security_mesh.get_context(user_role)
    except ValueError as e:
        logger.error(f"[DomainTask:{task_id}] Invalid role {user_role}: {e}")
        return {
            "error": f"Invalid role: {user_role}",
            "agent_name": agent_name,
            "status": "role_error",
            "task_id": task_id,
        }

    # ── 3. Run domain agent ─────────────────────────────────────────────────
    result = {}
    try:
        result = agent.run(
            query=query,
            auth_context=auth_context,
            tables_hint=tables_hint or [],
            verbose=verbose,
            run_id=run_id,
            plan_path=plan_path,
        )
    except SoftTimeLimitExceeded:
        elapsed = int(time.time() - start_time)
        logger.warning(
            f"[DomainTask:{task_id}] SoftTimeLimitExceeded "
            f"agent={agent_name} at {elapsed}s — retrying "
            f"(attempt {self.request.retries + 1})"
        )
        raise  # Celery handles retry with backoff

    except TimeLimitExceeded:
        elapsed = int(time.time() - start_time)
        logger.error(
            f"[DomainTask:{task_id}] TimeLimitExceeded "
            f"agent={agent_name} at {elapsed}s — failing without retry"
        )
        return {
            "answer": f"Domain agent '{agent_name}' timed out after {elapsed}s.",
            "error": "TimeLimitExceeded",
            "agent_name": agent_name,
            "task_id": task_id,
            "execution_time_ms": elapsed * 1000,
            "status": "timeout",
        }

    except Exception as e:
        elapsed = int(time.time() - start_time)
        logger.exception(
            f"[DomainTask:{task_id}] Unexpected error agent={agent_name} "
            f"at {elapsed}s: {e}"
        )
        return {
            "answer": f"Error in {agent_name}: {str(e)}",
            "error": str(e),
            "agent_name": agent_name,
            "task_id": task_id,
            "execution_time_ms": elapsed * 1000,
            "status": "error",
        }

    # ── 4. Attach metadata ─────────────────────────────────────────────────
    elapsed_ms = int((time.time() - start_time) * 1000)
    result["task_id"] = task_id
    result["agent_name"] = agent_name
    result["status"] = result.get("status", "success")
    result["celery"] = {
        "worker": self.request.hostname,
        "queue": queue,
        "retries": self.request.retries,
        "elapsed_ms": elapsed_ms,
        "time_limit_ms": 240000,
    }

    # ── 5. Harness phase tracking ─────────────────────────────────────────
    if run_id:
        try:
            from app.core.harness_runs import get_harness_runs
            hr = get_harness_runs()
            hr.update_phase(
                run_id=run_id,
                phase=f"domain_{agent_name}",
                status="completed" if result.get("status") == "success" else "failed",
                artifacts={
                    "agent": agent_name,
                    "tables_used": result.get("tables_used", []),
                    "record_count": result.get("record_count", 0),
                    "validation_passed": result.get("validation_passed"),
                    "celery_task_id": task_id,
                    "celery_queue": queue,
                    "celery_worker": self.request.hostname,
                },
                error=result.get("error"),
                duration_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning(f"[DomainTask:{task_id}] Harness tracking failed: {e}")

    logger.info(
        f"[DomainTask:{task_id}] DONE agent={agent_name} "
        f"status={result.get('status')} elapsed={elapsed_ms}ms "
        f"tables={result.get('tables_used', [])}"
    )

    return result


# ── Convenience: dispatch a group of domain tasks in parallel ────────────────

def dispatch_domain_group(
    assignments: list,
    query: str,
    user_role: str,
    run_id: Optional[str] = None,
    plan_path: Optional[str] = None,
) -> list:
    """
    Dispatch a list of agent assignments as parallel Celery tasks, each routed
    to its domain-specific queue.

    Args:
        assignments:      List of AgentAssignment dataclass instances from PlannerAgent
        query:            User query string
        user_role:        SAP role key
        run_id:           Harness run ID (propagated to each domain task)
        plan_path:        Plan state file path written by planner

    Returns:
        List of celery.result.AsyncResult objects, one per assignment.
        Use [ar.get(timeout=300) for ar in results] to collect.

    Usage:
        async_results = dispatch_domain_group(assignments, query, user_role, run_id)
        results = [ar.get(timeout=300) for ar in async_results]

    Note on queue routing:
        Each task is dispatched via .apply_async(queue=...) so it lands
        directly in the agent's dedicated queue. Workers on that queue pick it up.
        This is the core of swarm autoscaling — each domain queue can have
        N workers scaled independently via Kubernetes HPA, KEDA, or systemd.
    """
    from celery.result import AsyncResult
    from app.workers.celery_app import celery_app_instance as celery_app

    async_results = []
    for assignment in assignments:
        queue = AGENT_TO_QUEUE.get(assignment.agent_name, "agent")
        task_sig = run_domain_task.s(
            agent_name=assignment.agent_name,
            query=query,
            user_role=user_role,
            tables_hint=assignment.tables_hint,
            run_id=run_id,
            plan_path=plan_path,
            verbose=False,
        )
        # Route directly to domain queue — workers listening on that queue will pick it up
        async_result = task_sig.apply_async(
            queue=queue,
            routing_key=queue,
        )
        async_results.append(async_result)

    logger.info(
        f"[DispatchGroup] Dispatched {len(async_results)} domain tasks — "
        f"agents={[a.agent_name for a in assignments]} "
        f"queues={[AGENT_TO_QUEUE.get(a.agent_name, 'agent') for a in assignments]} "
        f"run_id={run_id} "
        f"task_ids={[ar.id for ar in async_results]}"
    )

    return async_results


# ── Result collection helper ──────────────────────────────────────────────────

def collect_group_results(async_results: list, assignments: list, run_id: str = None, timeout: float = 300.0) -> list:
    """
    Collect and verify results from a dispatched Celery Group.

    Args:
        group_result:  AsyncResult from Group.apply_async()
        assignments:   Original AgentAssignment list (for ordering)
        timeout:       Max seconds to wait per result

    Returns:
        List of result dicts (same order as assignments).
        Partial failure: returns successful results, logs failures.
        Total failure: returns empty list.
    """
    results = []
    failed = []

    for i, async_res in enumerate(async_results):
        agent_name = assignments[i].agent_name if i < len(assignments) else "unknown"
        try:
            result = async_res.get(timeout=timeout)
            if result.get("status") in ("error", "timeout", "role_error", "agent_not_found"):
                logger.warning(
                    f"[CollectGroup] agent={agent_name} "
                    f"task_id={async_res.id} returned status={result.get('status')}"
                )
                failed.append(result)
            results.append(result)
        except Exception as e:
            logger.error(
                f"[CollectGroup] agent={agent_name} "
                f"task_id={async_res.id} raised: {e}"
            )
            failed.append({
                "error": str(e),
                "agent_name": agent_name,
                "status": "celery_error",
                "task_id": async_res.id,
            })
            results.append(failed[-1])

    success_count = len([r for r in results if r.get("status") != "celery_error"])
    logger.info(
        f"[CollectGroup] {success_count}/{len(results)} agents succeeded, "
        f"{len(failed)} failed — run_id={run_id or 'N/A'}"
    )

    return results


# ── Queue configuration helper ───────────────────────────────────────────────

def get_domain_queues():
    """
    Returns all domain queues as a list of kombu.Queue objects.
    Import this in celery_app.py to register queues.
    """
    from kombu import Exchange
    queues = []
    for queue_name in AGENT_TO_QUEUE.values():
        queues.append(
            Queue(
                queue_name,
                exchange=Exchange("sap_masters", type="direct"),
                routing_key=queue_name,
                max_priority=5,
            )
        )
    return queues
