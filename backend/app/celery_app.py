"""
celery_app.py — Celery application for Know Your SAP Masters
==========================================================
Async task queue: long-running SQL queries, report generation,
cross-module graph traversals, scheduled jobs.

Broker: RabbitMQ (amqp://guest:guest@rabbitmq:5672/)
Result backend: Redis (redis://redis:6379/0)

Start workers:
    cd backend
    celery -A app.celery_app worker --loglevel=info

Trigger from Python:
    from app.celery_app import async_generate_report
    task = async_generate_report.delay(role_id="AP_CLERK", query="...")
    print(task.id)   # poll with task.ready(), task.get()
"""
from celery import Celery
import os

broker_url = os.environ.get("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672/")
result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

app = Celery(
    "sapmasters",
    broker=broker_url,
    backend=result_backend,
    include=[
        # Add task modules here as they are created:
        # "app.tasks.reports",
        # "app.tasks.graph_jobs",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,      # 5 min hard limit
    task_soft_time_limit=240, # 4 min soft limit
    worker_prefetch_multiplier=1,
    task_acks_late=True,      # Only ack after completion (requeue on crash)
    task_reject_on_worker_lost=True,
    task_routes={
        "app.tasks.reports.*": {"queue": "reports"},
        "app.tasks.graph_jobs.*": {"queue": "graph"},
    },
)


@app.task(bind=True, name="sapmasters.health_check")
def health_check(self):
    """Smoke test — returns True if worker is alive."""
    return True


@app.task(bind=True, name="sapmasters.echo")
def echo(self, message: str):
    """Echo a message — used to verify broker connectivity."""
    return f"Worker received: {message}"
