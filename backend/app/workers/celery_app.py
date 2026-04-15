"""
celery_app.py — Celery Application Configuration
================================================
Shared Celery app instance used by both the worker and the API broker.

Broker/Backend Host Resolution (Windows vs Docker):
  Outside Docker (Windows/Mac): use localhost or host.docker.internal
  Inside Docker (k8s):         use Docker service names (rabbitmq, redis)

  Override via env vars:
    CELERY_BROKER_URL      — AMQP broker (default: amqp://sapmasters:<PASS>@localhost:5672//)
    CELERY_RESULT_BACKEND   — Redis result backend (default: redis://localhost:6379/0)
    RABBITMQ_PASS           – RabbitMQ password (default: sapmasters123)

Workers (from backend/ directory):
  celery -A app.workers.celery_app worker --loglevel=info --concurrency=4

Flower (monitoring):
  celery -A app.workers.celery_app flower --port=5555

Beat (periodic tasks):
  celery -A app.workers.celery_app beat --loglevel=info
"""

from __future__ import annotations

import os
from celery import Celery
from kombu import Exchange, Queue

# ── Broker Configuration ──────────────────────────────────────────────────────
_rabbitmq_pass = os.environ.get("RABBITMQ_PASS", "sapmasters123")

# Resolve broker host: use localhost/host.docker.internal on Windows,
# Docker service names inside containers.
# Override via CELERY_BROKER_URL env var for full control.
_celery_host = os.environ.get("CELERY_BROKER_HOST", "localhost")
_broker_url = os.environ.get(
    "CELERY_BROKER_URL",
    f"amqp://sapmasters:{_rabbitmq_pass}@{_celery_host}:5672//",
)

# Same for result backend
_redis_host = os.environ.get("REDIS_HOST", "localhost")
_result_backend = os.environ.get(
    "CELERY_RESULT_BACKEND",
    f"redis://{_redis_host}:6379/0",
)

# ── Celery App ────────────────────────────────────────────────────────────────
# IMPORTANT: the bare name "app" is reserved for the app/ package.
# All celery_app_instance.conf.* calls must come BEFORE any "import app.workers.*"
# statement. Python resolves bare dotted names via sys.modules, which would
# overwrite a variable named "app".
# We use celery_app_instance as the Celery object name throughout.
celery_app_instance = Celery(
    "sap_masters",
    broker=_broker_url,
    backend=_result_backend,
)

celery_app_instance.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Result backend
    result_expires=600,
    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    # Broker / visibility timeout
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    # Routing defaults
    task_default_queue="agent",
    task_default_exchange="sap_masters",
    task_default_routing_key="agent",
    # Performance
    worker_prefetch_multiplier=1,
    # NOTE: On Windows, prefork (billiard) pool crashes with
    # PermissionError on semaphore handles. Force solo pool on Windows.
    worker_pool = "solo" if os.name == "nt" else "prefork",
    worker_concurrency=4,          # Reduce from 8 for stability; tune per workload
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# ── Queue Definitions ─────────────────────────────────────────────────────────
# Domain queues — each maps to a specific SAP domain agent.
# Workers can be started per-queue for independent autoscaling:
#
#   celery -A app.workers.celery_app worker -Q pur_queue --concurrency=4
#   celery -A app.workers.celery_app worker -Q bp_queue,mm_queue --concurrency=2
#   celery -A app.workers.celery_app worker -Q cross_queue --concurrency=1
#
# KEDA example for Kubernetes autoscaling:
#   apiVersion: keda.k8s.io/v1alpha1
#   kind: ScaledObject
#   metadata:
#     name: sapmasters-pur-agent-scaler
#   spec:
#     scaleTargetRef:
#       name: sapmasters-swarm-pur
#     pollingInterval: 15
#     cooldownPeriod: 300
#     minReplicaCount: 1
#     maxReplicaCount: 10
#     triggers:
#       - type: rabbitmq
#         metadata:
#           queueName: pur_queue
#           host: amqp://sapmasters:sapmasters123@rabbitmq:5672/
#           queueLength: "10"

agent_queue = Queue(
    "agent",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="agent",
    max_priority=5,
)
system_queue = Queue(
    "system",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="system",
    max_priority=10,
)
priority_queue = Queue(
    "priority",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="priority",
    max_priority=10,
)
# Domain agent queues (for swarm autoscaling)
pur_queue = Queue(
    "pur_queue",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="pur_queue",
    max_priority=5,
)
bp_queue = Queue(
    "bp_queue",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="bp_queue",
    max_priority=5,
)
mm_queue = Queue(
    "mm_queue",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="mm_queue",
    max_priority=5,
)
sd_queue = Queue(
    "sd_queue",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="sd_queue",
    max_priority=5,
)
qm_queue = Queue(
    "qm_queue",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="qm_queue",
    max_priority=5,
)
wm_queue = Queue(
    "wm_queue",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="wm_queue",
    max_priority=5,
)
cross_queue = Queue(
    "cross_queue",
    exchange=Exchange("sap_masters", type="direct"),
    routing_key="cross_queue",
    max_priority=5,
)

all_queues = (
    agent_queue, system_queue, priority_queue,
    pur_queue, bp_queue, mm_queue, sd_queue, qm_queue, wm_queue, cross_queue,
)
celery_app_instance.conf.task_queues = all_queues

# ── Task Routes ───────────────────────────────────────────────────────────────
celery_app_instance.conf.task_routes = {
    "app.workers.orchestrator_tasks.run_orchestrator_task": {
        "queue": "agent",
        "routing_key": "agent",
        "priority": 5,
    },
    "app.workers.orchestrator_tasks.health_check_task": {
        "queue": "system",
        "routing_key": "system",
        "priority": 10,
    },
    "app.workers.orchestrator_tasks.run_orchestrator_sync_task": {
        "queue": "priority",
        "routing_key": "priority",
        "priority": 8,
    },
    # ── Domain agent tasks (swarm autoscaling) ────────────────────────────
    # Queue is determined by agent_name → queue mapping inside domain_tasks.py
    # We route the generic run_domain_task to queues based on task args.
    "app.workers.domain_tasks.run_domain_task": {
        "queue": "agent",        # Default; overridden by queue param in .delay()
        "routing_key": "agent",
        "priority": 4,
    },
}

# ── Domain task queue routing via task_apply ────────────────────────────────────
# Celery doesn't support dynamic routing_key from task args at route config time.
# We use .apply_async(queue=...) at call site instead. The Kombu queue binding
# is already declared above. See dispatch_domain_group() in domain_tasks.py.

# ── Beat Schedule (periodic tasks) ───────────────────────────────────────────────
# Start with: celery -A app.workers.celery_app beat --loglevel=info
#
# NOTE: On Windows, Celery Beat + solo pool has issues with periodic tasks.
# For production on Windows, use Celery Beat inside a Linux container or k8s.
# The beat_schedule below works correctly on Linux/Mac or inside Docker.
celery_app_instance.conf.beat_schedule = {
    "cleanup-memory-every-5-min": {
        "task": "app.workers.orchestrator_tasks.cleanup_memory_task",
        "schedule": 300.0,   # seconds (5 min)
        "options": {"queue": "system", "routing_key": "system"},
    },
    "health-check-every-1-min": {
        "task": "app.workers.orchestrator_tasks.health_check_task",
        "schedule": 60.0,
        "options": {"queue": "system", "routing_key": "system"},
    },
}

# ── NOW import task modules ───────────────────────────────────────────────────
# IMPORTANT: All celery_app_instance.conf.* calls MUST come BEFORE this import.
# See docstring at top of file for explanation of the naming convention.
import app.workers.orchestrator_tasks  # noqa: F401
import app.workers.domain_tasks             # noqa: F401 — registers run_domain_task with the Celery app

# ── Health check for startup / k8s readiness probe ───────────────────────────
@celery_app_instance.task(name="health_check_task", queue="system")
def health_check_task() -> dict:
    """Lightweight task for load balancer / k8s readiness probes."""
    return {
        "status": "ok",
        "service": "sap_masters_celery",
        "broker": _broker_url.split("@")[-1] if "@" in _broker_url else "configured",
    }


if __name__ == "__main__":
    celery_app_instance.start()
