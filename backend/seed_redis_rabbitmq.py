"""
seed_redis_rabbitmq.py — Seed Redis with session state and verify RabbitMQ
=========================================================================
Redis: Creates demo sessions for AP_CLERK, MM_CLERK, SD_CLERK roles
         Pre-loads conversation history so the chatbot starts with context
RabbitMQ: Verifies broker connectivity (no tasks defined yet — Celery app scaffold)

Usage:
    python seed_redis_rabbitmq.py
"""
import json
import time
import uuid
import os
import sys

BACKEND_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_PATH)

REDIS_URL = "redis://localhost:6379/0"
RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"

# ─────────────────────────────────────────────────────────────────────────────
# Redis — Dialog & Session State
# ─────────────────────────────────────────────────────────────────────────────
import redis

def seed_redis():
    print("=" * 60)
    print("  Redis Session State Seeder")
    print("=" * 60)

    r = redis.from_url(REDIS_URL, decode_responses=True)

    # Check connection
    try:
        r.ping()
        info = r.info()
        print(f"\nConnected to Redis: {REDIS_URL}")
        print(f"  Redis version: {info.get('redis_version', 'unknown')}")
        print(f"  Memory used: {info.get('used_memory_human', 'unknown')}")
    except Exception as e:
        print(f"  ❌ Redis connection failed: {e}")
        return False

    # ── Demo sessions per role ───────────────────────────────────────────
    DEMO_SESSIONS = [
        {
            "role": "AP_CLERK",
            "session_id": "demo-ap-clerk-001",
            "user_id": "user:ap_clerk",
            "context": {
                "company_code": "1000",
                "currency": "USD",
                "language": "EN",
            },
            "turns": [
                {
                    "turn_id": "t1",
                    "timestamp": "2026-04-11T09:00:00Z",
                    "user_query": "Show me all open invoices for vendor ACME Corp",
                    "generated_sql": "SELECT LIFNR, BELNR, BLDAT, WRBTR FROM BSEG WHERE LIFNR = 'ACME001' AND BSCHL = '31'",
                    "tables_used": ["BSEG", "LFA1"],
                    "row_count": 12,
                    "confidence": 0.91,
                },
                {
                    "turn_id": "t2",
                    "timestamp": "2026-04-11T09:01:30Z",
                    "user_query": "What about invoices over $10,000?",
                    "generated_sql": "SELECT LIFNR, BELNR, BLDAT, WRBTR FROM BSEG WHERE LIFNR = 'ACME001' AND WRBTR > 10000",
                    "tables_used": ["BSEG"],
                    "row_count": 3,
                    "confidence": 0.88,
                },
            ],
        },
        {
            "role": "MM_CLERK",
            "session_id": "demo-mm-clerk-001",
            "user_id": "user:mm_clerk",
            "context": {
                "plant": "1000",
                "language": "EN",
            },
            "turns": [
                {
                    "turn_id": "t1",
                    "timestamp": "2026-04-11T10:00:00Z",
                    "user_query": "What is the current stock level for material FG-100?",
                    "generated_sql": "SELECT MATNR, WERKS, LABST FROM MARD WHERE MATNR = 'FG-100'",
                    "tables_used": ["MARD", "MARA"],
                    "row_count": 4,
                    "confidence": 0.95,
                },
            ],
        },
        {
            "role": "SD_CLERK",
            "session_id": "demo-sd-clerk-001",
            "user_id": "user:sd_clerk",
            "context": {
                "sales_org": "1000",
                "language": "EN",
            },
            "turns": [
                {
                    "turn_id": "t1",
                    "timestamp": "2026-04-11T11:00:00Z",
                    "user_query": "Show me all sales orders for customer WESTERN CORP this month",
                    "generated_sql": "SELECT VBAK.VBELN, VBAK.KUNNR, VBAK.BSTDK, VBAP.MATNR, VBAP.KWMENG FROM VBAK JOIN VBAP ON VBAK.VBELN = VBAP.VBELN WHERE VBAK.KUNNR = 'WESTERN001' AND VBAK.BSTDK >= '20260401'",
                    "tables_used": ["VBAK", "VBAP", "KNA1"],
                    "row_count": 8,
                    "confidence": 0.87,
                },
            ],
        },
        {
            "role": "BASIC_USER",
            "session_id": "demo-basic-user-001",
            "user_id": "user:basic",
            "context": {"language": "EN"},
            "turns": [],
        },
    ]

    print(f"\n[1] Seeding {len(DEMO_SESSIONS)} demo sessions...")
    for session in DEMO_SESSIONS:
        sid = session["session_id"]
        role = session["role"]
        user_id = session["user_id"]
        turns = session["turns"]
        ctx = session["context"]

        # Set session hash
        r.hset(f"dialog:{sid}", mapping={
            "session_id": sid,
            "user_id": user_id,
            "role": role,
            "context": json.dumps(ctx),
            "last_domain": "",
            "last_tables": json.dumps([]),
            "last_entities": json.dumps([]),
            "pending_clarification_type": "",
            "created_at": "2026-04-11T00:00:00Z",
            "last_updated": "2026-04-11T12:00:00Z",
        })

        # Set TTL of 7 days for session
        r.expire(f"dialog:{sid}", 7 * 24 * 3600)

        # Push conversation turns
        for turn in turns:
            turn_json = json.dumps(turn)
            r.rpush(f"dialog:{sid}:turns", turn_json)
        r.expire(f"dialog:{sid}:turns", 7 * 24 * 3600)

        print(f"  ✅ {role} session '{sid}': {len(turns)} turns, context={ctx}")

    # ── Role preferences ───────────────────────────────────────────────────
    print("\n[2] Setting role preferences...")
    role_prefs = {
        "AP_CLERK": {"output_format": "table", "max_rows": "50", "include_sql": "True"},
        "MM_CLERK": {"output_format": "table", "max_rows": "100", "include_sql": "True"},
        "SD_CLERK": {"output_format": "table", "max_rows": "50", "include_sql": "False"},
        "BASIC_USER": {"output_format": "simple", "max_rows": "20", "include_sql": "False"},
    }
    for role, prefs in role_prefs.items():
        r.hset(f"preferences:{role}", mapping=prefs)
        r.expire(f"preferences:{role}", 30 * 24 * 3600)
        print(f"  ✅ {role}: {prefs}")

    # ── Rate limit counters ────────────────────────────────────────────────
    print("\n[3] Initializing rate limit counters...")
    for user_id in ["user:ap_clerk", "user:mm_clerk", "user:sd_clerk", "user:basic"]:
        r.setex(f"rate_limit:{user_id}", 3600, "100")  # 100 requests/hour
    print(f"  ✅ Rate limits set for 4 users")

    # ── Stats ──────────────────────────────────────────────────────────────
    session_keys = r.keys("dialog:*")
    turn_keys = r.keys("dialog:*:turns")
    pref_keys = r.keys("preferences:*")
    print(f"\n[4] Redis state summary:")
    print(f"    Session hashes: {len([k for k in session_keys if ':turns' not in k])}")
    print(f"    Turn lists: {len(turn_keys)}")
    print(f"    Role preferences: {len(pref_keys)}")
    print(f"    Rate limit keys: {len(r.keys('rate_limit:*'))}")

    # Verify
    all_keys = r.keys("*")
    print(f"\n    Total keys in Redis: {len(all_keys)}")

    r.close()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# RabbitMQ — Verify broker connectivity
# ─────────────────────────────────────────────────────────────────────────────
def verify_rabbitmq():
    print("\n" + "=" * 60)
    print("  RabbitMQ Broker Verification")
    print("=" * 60)

    try:
        import pika
    except ImportError:
        try:
            import urllib.parse
            url = urllib.parse.urlparse(RABBITMQ_URL)
            print(f"pika not installed — verifying via HTTP management API instead")
            # Try management API
            import urllib.request
            try:
                # HTTP Basic Auth for management API
                import base64
                auth = base64.b64encode(b"guest:guest").decode("ascii")
                req = urllib.request.Request(
                    "http://localhost:15672/api/overview",
                    headers={"Authorization": f"Basic {auth}"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                print(f"\n  ✅ RabbitMQ HTTP Management API: OK")
                print(f"     Cluster: {data.get('cluster_name', 'unknown')}")
                print(f"     RabbitMQ version: {data.get('rabbitmq_version', 'unknown')}")
                print(f"     Consumers: {data.get('queue_totals', {}).get('messages', 0)}")
                return True
            except Exception as e:
                print(f"  ❌ RabbitMQ HTTP API error: {e}")
                return False
        except Exception as e:
            print(f"  ❌ RabbitMQ verification failed: {e}")
            return False

    try:
        params = pika.URLParameters(RABBITMQ_URL)
        conn = pika.BlockingConnection(params)
        channel = conn.channel()
        print(f"\n  ✅ Connected to RabbitMQ: {RABBITMQ_URL}")
        print(f"     Channel: {channel}")

        # Declare a test queue
        channel.queue_declare(queue="sapmasters.test", durable=False)
        channel.basic_publish(
            body=json.dumps({"test": "hello from seed_redis_rabbitmq.py"}),
            exchange="",
            routing_key="sapmasters.test",
        )
        print(f"  ✅ Test message published to 'sapmasters.test'")

        # Check queues
        queues = channel.queue_declare(queue="", passive=True)
        print(f"\n  RabbitMQ ready — no queues active yet (Celery tasks not defined)")
        print(f"     To enable Celery workers: start with `celery -A app.celery_app worker`")

        conn.close()
        return True
    except Exception as e:
        print(f"  ❌ RabbitMQ connection failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Celery app scaffold — create if doesn't exist
# ─────────────────────────────────────────────────────────────────────────────
def create_celery_app():
    """Create a minimal Celery app scaffold pointing to RabbitMQ broker."""
    celery_app_path = os.path.join(BACKEND_PATH, "app", "celery_app.py")
    if os.path.exists(celery_app_path):
        print(f"\n[Celery] app/celery_app.py already exists — skipping scaffold")
        return

    print(f"\n[Celery] Creating app/celery_app.py scaffold...")
    celery_code = '''"""
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
'''
    with open(celery_app_path, "w") as f:
        f.write(celery_code)
    print(f"  ✅ Created: {celery_app_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    redis_ok = seed_redis()
    rabbitmq_ok = verify_rabbitmq()

    if redis_ok:
        create_celery_app()

    print("\n" + "=" * 60)
    if redis_ok and rabbitmq_ok:
        print("  ✅ Redis + RabbitMQ seeding complete")
    elif redis_ok:
        print("  ⚠️  Redis seeded, RabbitMQ verification failed")
    else:
        print("  ❌ Seeding failed — check output above")
    print("=" * 60)
