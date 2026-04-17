from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file from backend/ directory (sets MEMGRAPH_URI, QDRANT_URL, etc.)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.api.api import api_router
from app.api.middleware.session_middleware import SessionMiddleware, check_redis_health
from app.governance.leanix_middleware import LeanIXGovernanceMiddleware

app = FastAPI(
    title="SAP S/4 HANA Enterprise Master Data Chatbot API",
    description=(
        "5-Pillar RAG Architecture for secure, role-aware natural language querying "
        "of SAP Master Data. Horizontally scalable via Celery + Redis."
    ),
    version="0.3.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Session & Rate Limiting Middleware ─────────────────────────────────────────
# Reads X-Session-ID / sets sap_session_id cookie
# Attaches dialog state + rate info to request.state
# Auto-creates Redis session on first request
app.add_middleware(SessionMiddleware)

# ── LeanIX Governance Middleware (M9) ────────────────────────────────────────
# Pre-flight:  pre-authorization + compliance classification + context enrichment
# Post-flight: audit trail + LeanIX response headers
# Bypasses: health checks, task polling, static paths
# Set LEANIX_ENABLED=false to disable (or omit LEANIX_BASE_URL / LEANIX_API_TOKEN)
app.add_middleware(LeanIXGovernanceMiddleware)

# ── API Routes ─────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")

# ── Health & System Endpoints ──────────────────────────────────────────────────
@app.get("/")
def read_root():
    return {
        "message": "Welcome to the SAP Master Data Chatbot API.",
        "docs": "/docs",
        "async": "/api/v1/chat/master-data-async",
        "health": "/health",
    }


@app.get("/health")
def health():
    """Combined health check: API + Redis + Memgraph (if configured)."""
    import requests as _requests

    health_status = {
        "api": "ok",
        "redis": "unknown",
        "memgraph": "unknown",
    }

    # Redis check
    try:
        from app.core.redis_dialog_manager import get_dialog_manager
        dm = get_dialog_manager()
        stats = dm.stats()
        health_status["redis"] = "ok" if stats.get("connected") else "error"
    except Exception as e:
        health_status["redis"] = f"error: {e}"

    # Memgraph check (if MEMGRAPH_URI set)
    memgraph_uri = os.environ.get("MEMGRAPH_URI", "")
    if memgraph_uri:
        try:
            import socket as _socket
            host = memgraph_uri.split("://")[1].split(":")[0]
            port = int(memgraph_uri.split(":")[-1])
            sock = _socket.create_connection((host, port), timeout=2)
            sock.close()
            health_status["memgraph"] = "ok"
        except Exception:
            health_status["memgraph"] = "unreachable"

    return health_status


@app.get("/health/redis")
def redis_health():
    """Dedicated Redis health endpoint for load balancer probes."""
    return check_redis_health()


@app.get("/debug/graph-backend")
def graph_backend_debug():
    """
    Diagnostic endpoint for Graph RAG backend.
    Reports which backend is active, connection status, and schema stats.
    """
    from app.core.graph_store import graph_store
    import time as _time

    result = {"backend": "unknown", "timestamp": _time.time()}

    # Detect backend type
    backend_type = type(graph_store).__name__
    result["backend_type"] = backend_type
    result["is_memgraph"] = backend_type == "MemgraphShim"
    result["is_networkx"] = backend_type in ("GraphRAGManager", "GraphStore")

    # NetworkX stats (always available as mirror)
    try:
        nx_meta = getattr(graph_store, "_node_meta", None) or []
        edge_meta = getattr(graph_store, "_edge_meta", None) or []
        result["networkx"] = {
            "nodes": len(nx_meta),
            "edges": len(edge_meta),
        }
    except Exception as e:
        result["networkx"] = {"error": str(e)}

    # Memgraph stats (if active)
    if result["is_memgraph"]:
        try:
            mg = graph_store._mg
            node_result = list(mg.execute_and_fetch("MATCH (n:SAPTable) RETURN count(n) AS cnt"))
            edge_result = list(mg.execute_and_fetch("MATCH ()-[r:FOREIGN_KEY]->() RETURN count(r) AS cnt"))

            result["memgraph"] = {
                "connected": True,
                "nodes": node_result[0]["cnt"] if node_result else 0,
                "edges": edge_result[0]["cnt"] if edge_result else 0,
            }

            # Sample traversal with timing
            start = _time.time()
            sample = list(mg.execute_and_fetch(
                "MATCH path = (a:SAPTable {table_name: 'LFA1'})-[r:FOREIGN_KEY*1..2]-(b:SAPTable) "
                "RETURN a.table_name AS src, b.table_name AS dst LIMIT 5"
            ))
            elapsed = round((_time.time() - start) * 1000, 1)
            result["memgraph"]["traversal_ms"] = elapsed
            result["memgraph"]["sample_paths"] = [
                {"src": str(r["src"]), "dst": str(r["dst"])} for r in sample
            ]

            # Sync status
            if hasattr(graph_store, "_edge_meta"):
                result["sync"] = {
                    "nx_edges": len(graph_store._edge_meta),
                    "mg_edges": result["memgraph"]["edges"],
                    "in_sync": len(graph_store._edge_meta) == result["memgraph"]["edges"],
                }

        except Exception as e:
            result["memgraph"] = {"connected": False, "error": str(e)}

    return result


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    import os
    from app.core.vector_store import VectorStoreManager

    # Initialize vector store (ChromaDB or Qdrant)
    # Set VECTOR_STORE_BACKEND=qdrant to use Qdrant cluster (default: ChromaDB)
    from app.core.vector_store import init_vector_store
    _backend = os.environ.get("VECTOR_STORE_BACKEND", "chroma")
    try:
        store_manager = init_vector_store(backend=_backend)
        count = store_manager.count()
        logger.info(f"[STARTUP] Vector store ({_backend}): {count} schema records.")
    except Exception as e:
        logger.warning(f"[STARTUP] Vector store ({_backend}) failed: {e}")
        logger.info("[STARTUP] Falling back to ChromaDB...")
        store_manager = init_vector_store(backend="chroma")
        count = store_manager.count()
        logger.info(f"[STARTUP] ChromaDB fallback: {count} schema records.")

    # Initialize Redis dialog manager (lazy — connects on first use)
    from app.core.redis_dialog_manager import get_dialog_manager
    try:
        dm = get_dialog_manager()
        stats = dm.stats()
        logger.info(f"[STARTUP] Redis Dialog Manager: {stats}")
    except Exception as e:
        logger.warning(f"[STARTUP] Redis Dialog Manager: {e}")

    # ── Memgraph Phase M3: Wire use_memgraph() into global graph_store ──────────
    # If MEMGRAPH_URI is set, replace the NetworkX graph_store singleton with
    # the Memgraph-backed adapter. All subsequent code uses graph_store as normal.
    #
    # To disable Memgraph and use pure NetworkX: omit MEMGRAPH_URI env var.
    memgraph_uri = os.environ.get("MEMGRAPH_URI", "")
    if memgraph_uri:
        try:
            from app.core import use_memgraph, graph_store
            tenant = os.environ.get("TENANT_ID", "default")
            logger.info(f"[STARTUP] Memgraph: swapping graph_store → Memgraph ({memgraph_uri}) for tenant {tenant}")
            mg_class = use_memgraph(uri=memgraph_uri, tenant_id=tenant)
            import app.core.graph_store as gs
            logger.info(f"[STARTUP] Memgraph Graph RAG: {gs.stats()}")
        except Exception as e:
            logger.warning(f"[STARTUP] Memgraph: {e} — using NetworkX fallback")
    else:
        logger.info("[STARTUP] Memgraph: not configured (MEMGRAPH_URI not set) — using NetworkX")
