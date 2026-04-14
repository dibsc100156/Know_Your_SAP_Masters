# Memgraph Migration Guide — Know Your SAP Masters
**From:** In-memory NetworkX Graph  
**To:** Distributed Memgraph Graph Database  
**Date:** April 6, 2026 | Author: Vishnu ॐ  
**Last Updated:** April 9, 2026

---

## Implementation Status — Updated April 9, 2026

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
| M1 | `docker-compose.memgraph.yml` + Memgraph Lab | ✅ DONE | Lab at `http://localhost:3000` |
| M1 | `memgraph_adapter.py` scaffold | ✅ DONE | Dual-mode (Memgraph + NetworkX mirror) |
| M1 | `init_schema.cql` — 114 tables + 137 edges | ✅ DONE | Full SAP enterprise schema loaded |
| M1 | `use_memgraph()` factory in `__init__.py` | ✅ DONE | Accepts `uri`, `user`, `password` |
| M2 | `build_enterprise_schema_graph()` direct Cypher port | ✅ DONE | Parses `init_schema.cql` via regex, builds both Memgraph + NX mirror |
| M2 | Regex fix — `m.group(6)` bridge flag (was `m.group(7)`) | ✅ DONE | `IndexError: no such group` bug fixed |
| M2 | Edge regex fixed — `)-[` pattern for `FOREIGN_KEY` edges | ✅ DONE | All 47 edges now parse correctly |
| M2 | Duplicate kwargs fix in `MemgraphShim.__init__` | ✅ DONE | Fixed `TypeError` on hot-reload |
| M2 | Orchestrator Native Cypher Querying (`AllPathsExplorer`) | ✅ DONE | `find_all_ranked_paths_native` implemented natively in `memgraph_adapter.py`. Variable-length queries (`-[*..5]-`) offloaded from Python to DB engine. |
| M3 | Wire `use_memgraph()` into `main.py` startup | ✅ DONE | Sets `MEMGRAPH_URI` env var; falls back to NX on failure |
| M3 | `smoke_test_memgraph.py` + `load_init_schema.py` scripts | ✅ DONE | |
| M4 | Celery async workers + circular import fix | ✅ DONE | `celery_app_instance` name change + `@shared_task` migration |
| M5 | Redis dialog state | ✅ COMPLETE | Hardened: retries, backoff, `REDIS_ENFORCE` fail-loud |
| M6 | Qdrant cluster migration | ✅ DONE | `vector_store.py` unified manager, `qdrant_vector_store.py` operational, configured via `VECTOR_STORE_BACKEND=qdrant` |
| M7 | Connection pooling for SAP HANA | ⬜ PENDING | |
| M8 | Kubernetes HPA — autoscale Celery workers | ✅ COMPLETE | KEDA ScaledObjects configured for RabbitMQ depth |
| M9 | LeanIX agent governance integration | ✅ WIRED | Middleware registered in main.py; DPO reporting enabled |
| M10 | Multi-tenant isolation — separate Memgraph subgraphs | ✅ COMPLETE | Cypher nodes labeled per-tenant, `TENANT_ID` env wired |

**Overall:** Phases M1–M6, M8 & M10 ✅ COMPLETE | M7 ⬜ PENDING

---

## Overview

This guide migrates **Pillar 5 (Graph RAG)** from a single-node in-memory NetworkX graph (`graph_store.py`) to a distributed Memgraph cluster — enabling horizontal scale, concurrent multi-worker traversal, and native vector search.

### Architecture: Dual-Mode (Memgraph + NetworkX Mirror)

```
┌─────────────────────────────────────────────────────────┐
│  Memgraph (bolt://localhost:7687)                       │
│  · Persistent graph — 114 tables, 137 FK edges          │
│  · Loaded once at startup from init_schema.cql          │
│  · Queried via Cypher for graph mutations               │
└────────────────────┬────────────────────────────────────┘
                    │ _build_nx_from_local_metadata()
                    │ (called once after schema load)
                    ↓
┌─────────────────────────────────────────────────────────┐
│  NetworkX Mirror (in-process, in-memory)                │
│  · Built from local _node_meta + _edge_meta            │
│  · Always stays in sync with Memgraph                  │
│  · Used for ALL traversal algorithms (BFS, betweenness) │
│  · Falls back to NX if Memgraph is unavailable         │
└─────────────────────────────────────────────────────────┘
```

> **Key insight:** The NetworkX mirror is built **locally** from parsed metadata — NOT lazily synced from Memgraph queries. This avoids round-trip latency on every traversal and makes the system work even if Memgraph goes down mid-session.

### What Stays the Same
- All **14 meta-paths** (vendor_master, procure_to_pay, order_to_cash, etc.)
- All **114 nodes** and **137 edges** (updated schema in `init_schema.cql`)
- All **orchestrator calls** — `traverse_graph()`, `find_path()`, `get_subgraph_context()`, `get_neighbors()`, `.G.nodes` all work unchanged
- `AllPathsExplorer` and `TemporalGraphRAG` — work unchanged via NetworkX mirror
- Drop-in replacement — no orchestrator changes needed

### What Has Changed
- Graph storage: RAM (NetworkX only) → Memgraph (persistent) + NetworkX (mirror)
- `graph_store.py` is now the **fallback** (NetworkX-only mode when Memgraph unavailable)
- `memgraph_adapter.py` is the **primary** — handles connection, parsing, dual sync
- `use_memgraph()` must be called at startup to activate Memgraph mode
- ChromaDB → Qdrant migration still pending (M6)

---

## Phase M1: Scaffold & Start Services

**Goal:** Get all Docker services running locally.

```bash
# Start the full stack
docker compose -f docker/docker-compose.memgraph.yml up memgraph lab -d

# Verify all containers are running
docker ps --format "{{.Names}} {{.Status}}"

# Expected output:
# sapmasters_memgraph       Up 2 minutes
# sapmasters_memgraph_lab   Up 2 minutes (port 3000)
# sapmasters_qdrant         Up <time>
# sapmasters_rabbitmq       Up <time> (ports 5672, 15672)
# sapmakers_redis           Up <time> (port 6379)
```

**Services and their endpoints:**

| Service | Host Port | Purpose |
|---------|-----------|---------|
| Memgraph | `localhost:7687` | Graph database (Bolt) |
| Memgraph Lab | `localhost:3000` | Web UI for graph visualization |
| Qdrant | `localhost:6333` | Vector store (not yet wired — M6) |
| Redis | `localhost:6379` | Dialog session store |
| RabbitMQ | `localhost:5672`, `15672` | Celery message broker |

**Install Python client:**
```bash
cd backend
.\.venv\Scripts\pip install gqlalchemy>=3.0.0
```

**Verify Memgraph connection:**
```python
from gqlalchemy import Memgraph
mg = Memgraph(host='localhost', port=7687)
print(list(mg.execute_and_fetch('RETURN 1 AS x')))
# → [{'x': 1}]
```

---

## Phase M2: Load the SAP Enterprise Schema

**Goal:** Populate Memgraph with 114 tables and 137 FK relationships from `init_schema.cql`.

### How it works

`MemgraphGraphRAGManager.build_enterprise_schema_graph()` does NOT use GraphRAGManager as a delegate anymore. Instead, it:

1. **Reads** `docker/memgraph/init_schema.cql` as a plain text file
2. **Parses** each statement with `_parse_node_statement()` and `_parse_edge_statement()` (regex-based)
3. **Executes** Cypher via `self._mg.execute()` to load nodes and edges into Memgraph
4. **Builds** the NetworkX mirror locally from parsed `_node_meta` / `_edge_meta` (no Memgraph round-trip)
5. **Computes** degree + betweenness centrality and stores back as Memgraph node properties

### Regex parsing (critical bugs to avoid)

**`_parse_node_statement()`** — parses CQL like:
```cypher
MERGE (m:SAPTable {table_name:"MARA"}) SET m.module="MM" ...
```
- Regex has **6 capture groups** — bridge flag is `m.group(6)` (NOT 7)
- The old code called `m.group(7)` → `IndexError: no such group` (bug fixed ✅)

**`_parse_edge_statement()`** — parses CQL like:
```cypher
MATCH (a:SAPTable {table_name:"MARA"}), (b:SAPTable {table_name:"MARC"})
MERGE (a)-[:FOREIGN_KEY {condition:"...", cardinality:"...", bridge_type:"..."}]->(b)
```
- Property block is captured as `edge_match.group(3)` — the full MATCH line
- Then `props_match = re.search(..., props_str)` extracts individual properties
- Previous bug: tried to parse from `edge_match.group(0)` using `[^}]*` which swallowed internal quotes → 0/47 edges matched (fixed ✅)

### Verify schema loaded

```python
from app.core import use_memgraph
mg = use_memgraph(uri='bolt://localhost:7687')
print(mg.stats())
# Expected:
# {'total_tables': 114, 'total_relationships': 137, 'cross_module_bridges': 97,
#  'modules': ['BP', 'CO', 'CS', 'FI', ...], 'memgraph_connected': True}
```

### Inspect in Memgraph Lab

Open `http://localhost:3000` and run:
```cypher
MATCH (t:SAPTable) RETURN t LIMIT 25
MATCH (a)-[r:FOREIGN_KEY]->(b) RETURN a, r, b LIMIT 50
```

---

## Phase M3: Wire into FastAPI Startup

**Goal:** Activate Memgraph automatically when the FastAPI server starts.

### How it's wired (in `main.py`)

```python
# backend/app/main.py — on_startup()
from app.core import use_memgraph, MEMGRAPH_GRAPH_STORE
import os

# Memgraph — load on startup (falls back to NetworkX on failure)
memgraph_uri = os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")
try:
    graph_store = use_memgraph(uri=memgraph_uri)
    stats = graph_store.stats()
    print(f"[STARTUP] Memgraph Graph RAG: {stats}")
except Exception as e:
    print(f"[STARTUP] Memgraph unavailable: {e}")
    print("[STARTUP] Using NetworkX fallback.")
    # graph_store remains as the NetworkX GraphRAGManager
```

### Startup environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMGRAPH_URI` | `bolt://localhost:7687` | Memgraph Bolt endpoint |
| `REDIS_HOST` | `localhost` | Redis host (use `localhost` on Windows, `redis` inside Docker) |
| `REDIS_PORT` | `6379` | Redis port |

### Startup log verification

```
[STARTUP] ChromaDB: 11 schema records at ~/.openclaw/workspace/chroma_db
[STARTUP] Vector store ready.
[STARTUP] Redis Dialog Manager: {'backend': 'redis', 'connected': True, ...}
[STARTUP] Memgraph: swapping graph_store → Memgraph (bolt://localhost:7687)
[STARTUP] Memgraph Graph RAG: {'total_tables': 114, 'total_relationships': 137, ...}
```

### Manual activation (anywhere in code)

```python
from app.core import use_memgraph
mg = use_memgraph(uri='bolt://localhost:7687')
# graph_store global is now replaced with MemgraphGraphRAGManager
```

---

## Phase M4: Celery Worker Fleet (Horizontal Scale)

**Goal:** Decouple the orchestrator loop from the FastAPI request thread.

### Current status

✅ Tasks are defined with `@shared_task` decorator  
✅ `celery_app.py` uses `celery_app_instance` variable name to avoid circular import  
✅ Broker is RabbitMQ (`sapmasters-rabbitmq:5672`)  
✅ Lazy import pattern — `celery_app_instance` imported only inside `get_task_result()`

### The circular import deadlock (fixed)

If you see `NameError: name 'app' is not defined`:
- **Cause:** `celery_app.py` had `app = Celery(...)` then immediately `import app.workers.orchestrator_tasks`. Python's import system resolved bare `app` through `sys.modules` before the assignment.
- **Fix (Applied April 7):** Renamed Celery instance to `celery_app_instance`. Set ALL `.conf.*` settings BEFORE importing workers. Added `app = celery_app_instance` at module bottom. Changed all `@app.task` decorators to `@shared_task` in the workers.

---

## Phase M5: Redis Dialog State

**Goal:** Move session persistence out of in-process memory and harden for distributed environments.

### Current status

✅ **COMPLETE (April 8, 2026)**
✅ `RedisDialogManager` class fully hardened
✅ Exponential backoff and auto-reconnect logic added
✅ Strict enforcement to prevent split-brain (`REDIS_ENFORCE=true`)

### Dialog manager behavior

```
Request arrives
  → try Redis connection (with up to 3 retries & backoff)
  → Redis up? → use Redis backend
  → Redis down? 
      → If REDIS_ENFORCE=true (default) → Fail-loud (RuntimeError)
      → If REDIS_ENFORCE=false → Fall back to file-based (.dialog_sessions/ dir)
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Redis host (use `redis` inside Docker) |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_ENFORCE` | `true` | When true, prevents silent fallback to files to avoid split-brain state loss. |

### Verify Redis connection

```python
from app.core.redis_dialog_manager import get_dialog_stats
print(get_dialog_stats())
# → {'backend': 'redis', 'connected': True, 'dialog_sessions': 0, ...}
```

### Scaling to production (inside Docker)

When deployed inside Docker, change:
```bash
REDIS_HOST=redis   # Docker service name
REDIS_PORT=6379
```

---

## Phase M8: Kubernetes HPA (Auto-Scaling Celery Workers)

**Goal:** Automatically scale the backend Celery agents in a Kubernetes cluster based on workload (RabbitMQ queue depth).

### Current Status

✅ **COMPLETE (April 9, 2026)**  
✅ KEDA `ScaledObject` configured for both `celery-primary` and `celery-replica` deployments  
✅ RabbitMQ credentials injected securely via `TriggerAuthentication`  
✅ Scale behavior set to max 20 replicas, triggering at 10 messages per worker  

### How it works

The system uses [KEDA (Kubernetes Event-driven Autoscaling)](https://keda.sh) to monitor the length of the `agent` queue in RabbitMQ.
When the depth exceeds the `queueLengthTarget` (set to 10), KEDA automatically scales up the `celery-primary` Deployment. 
To prevent thrashing, the scaler employs a 300-second cooldown period before scaling down after a spike.

### Deployment instructions

```bash
# Ensure KEDA is installed in the cluster
kubectl apply --server-side -f https://github.com/kedacore/keda/releases/download/v2.14.2/keda-2.14.2.yaml

# Apply the worker deployments and KEDA ScaledObjects
kubectl apply -k k8s/overlays/prod
```

---

## Phase M10: Multi-Tenant Isolation

**Goal:** Segment the enterprise schema into isolated subgraphs so multiple Business Units (BUs), company codes, or external customers can share one Memgraph instance securely.

### Current Status

✅ **COMPLETE (April 9, 2026)**  
✅ Cypher queries updated to inject dynamic tenant labels  
✅ FastAPI startup uses `TENANT_ID` environment variable  
✅ NetworkX in-memory mirror scoped to tenant boundaries  

### How it works

In `memgraph_adapter.py`, the `MemgraphGraphRAGManager` accepts a `tenant_id` at initialization. It appends a label (e.g., `:Tenant_T100`) to every node inserted into Memgraph.

When the application fetches the graph to build the local NetworkX mirror, it filters strictly by that tenant label:
```cypher
MATCH (t:SAPTable:Tenant_T100) RETURN t...
MATCH (a:SAPTable:Tenant_T100)-[r:FOREIGN_KEY]->(b:SAPTable:Tenant_T100) RETURN ...
```

### Usage

Set the environment variable before starting the backend:
```bash
# Windows
set TENANT_ID=SP_GLOBAL_ENERGY

# Linux/Docker
export TENANT_ID=SP_GLOBAL_ENERGY
```

If not set, it defaults to `default`, keeping full backward compatibility with single-tenant deployments.

**Goal:** Replace file-based ChromaDB with clustered Qdrant vector store.

### Current status

✅ **COMPLETE (April 7, 2026)**
✅ Dual-backend `VectorStoreManager` built in `vector_store.py`
✅ `qdrant_vector_store.py` operational with gRPC connection
✅ Env var switch wired into FastAPI startup (`VECTOR_STORE_BACKEND=qdrant`)

### How to use Qdrant

In `main.py`, the backend checks the environment variable at startup:

```bash
# Windows
set VECTOR_STORE_BACKEND=qdrant
set QDRANT_HOST=localhost
set QDRANT_PORT=6333

# Docker/Linux
export VECTOR_STORE_BACKEND=qdrant
```

If the connection fails or `VECTOR_STORE_BACKEND` is missing/set to `chroma`, it falls back to ChromaDB instantly.

---

## NetworkX Mirror — How It Works

```
Memgraph (persistent graph, loaded at startup)
       │
       │  _build_nx_from_local_metadata()
       │  (called once, after schema loaded)
       ↓
NetworkX mirror (in-memory, in-process)
       │
       ├── traverse_graph()    ──► BFS shortest path
       ├── find_path()         ──► raw table list
       ├── get_neighbors()     ──► k-hop neighborhood
       ├── all_paths_explore() ──► all-simple-paths enumeration
       ├── get_subgraph_context() ──► rich path metadata
       └── temporal_graph_search() ──► date-filtered traversal
```

**The mirror is NOT lazily synced from Memgraph.** It's built in one pass from the local `_node_meta` and `_edge_meta` dictionaries, which are populated during the CQL parse. This design:

- Avoids round-trip latency on every traversal
- Works even if Memgraph is temporarily unavailable
- Makes the system trivially roll back to pure NetworkX by skipping `use_memgraph()`

---

## Rollback Plan

**Instant rollback — no code changes needed:**

```python
# Just don't call use_memgraph() — graph_store stays as NetworkX GraphRAGManager
from app.core.graph_store import graph_store  # pure NetworkX, no external deps
```

**Or, to explicitly use NetworkX:**
```python
from app.core.graph_store import graph_store as nx_graph_store
```

---

## Performance Targets

| Metric | Current (NetworkX only) | Current (Memgraph + NX) | Target (Full Fleet) |
|---|---|---|---|
| Graph load time | ~50ms (in-memory) | ~3-5s (Memgraph cold) | ~3-5s |
| Shortest path query | ~1ms | ~1ms (NX mirror) | ~1ms |
| Concurrent traversals | 1 (single process) | 1 (single process) | 50+ (fleet) |
| Graph persistence | RAM only | Memgraph disk + NX RAM | Memgraph + replicas |
| Vector search | ChromaDB (file) | ChromaDB (file) | Qdrant cluster |

---

## Files Created by This Migration

```
backend/app/core/
  ├── memgraph_adapter.py       # MemgraphGraphRAGManager — dual-mode graph
  │   ├── use_memgraph()        # factory: uri/user/password → instance
  │   ├── MemgraphShim          # shim for NetworkX compatibility
  │   ├── _parse_node_statement()  # CQL → dict (6 capture groups!)
  │   ├── _parse_edge_statement()  # CQL → dict (parse from group(3))
  │   ├── build_enterprise_schema_graph()  # load + build NX mirror
  │   ├── _build_nx_from_local_metadata()  # no Memgraph round-trip
  │   └── _compute_and_store_centrality()  # degree + betweenness → Memgraph
  │
  └── graph_store.py            # UNCHANGED — pure NetworkX fallback

backend/app/workers/
  ├── celery_app.py             # celery_app_instance + .conf before imports
  └── orchestrator_tasks.py     # @shared_task + lazy celery_app import

backend/app/main.py              # wires use_memgraph() on startup

docker/
  ├── docker-compose.memgraph.yml  # Memgraph + Lab
  └── memgraph/
      └── init_schema.cql          # 114 tables + 137 edges (full SAP schema)

scripts/
  ├── smoke_test_memgraph.py    # M1 smoke test
  └── load_init_schema.py       # M2 schema loader

docs/
  └── MEMGRAPH_MIGRATION_GUIDE.md  # THIS FILE
```

---

## Critical Debugging Notes

### `TypeError` in `super().__init__()` (Duplicate kwargs)
**Symptom:** Startup fails on `MemgraphShim` initialization due to unexpected keyword arguments.
**Cause:** The original parameters `uri`, `user`, and `password` were passed down via `**kwargs` causing duplicates.
**Fix:** Explicitly pop `uri`, `user`, and `password` out of `kwargs` before passing them up.

### "no such group" IndexError
**Symptom:** Startup fails during schema load, falls back to NetworkX silently.  
**Cause:** `_parse_node_statement()` called `m.group(7)` but regex only had 6 groups.  
**Fix:** Use `m.group(6)` for the bridge flag. Add `lastindex` guard: `m.group(6) if m.lastindex >= 6 else False`.

### "Failed to connect to Memgraph" at startup
**Symptom:** `[STARTUP] Memgraph Graph RAG: {...}` not in logs. NetworkX used instead.  
**Cause:** `use_memgraph()` failed silently (exception caught and swallowed).  
**Fix:** Set `MEMGRAPH_URI=bolt://localhost:7687` env var. Check Memgraph container is running: `docker ps sapmasters_memgraph`.

### Redis "getaddrinfo failed" on Windows
**Symptom:** `[RedisDialogManager] Redis unavailable (Error 11001 connecting to redis:6379)`  
**Cause:** `redis` hostname doesn't resolve on Windows — it's a Docker service name.  
**Fix:** Set `REDIS_HOST=localhost` env var (Windows host port 6379 is mapped).

### 0/47 edges parsed (edge regex failure)
**Symptom:** `mg.stats()` shows 114 nodes but 0 edges.  
**Cause:** Edge regex pattern `)\s*,\s*\(` matched `)` then `[` as separate characters instead of `)-[`.  
**Fix:** Pattern uses `)-[` (literal) to match the `)-[:FOREIGN_KEY` syntax correctly.

### Circular import with Celery
**Symptom:** `NameError: name 'app' is not defined`  
**Cause:** `app = Celery(...)` then `import app.workers.orchestrator_tasks` — deadlock.  
**Fix:** `celery_app_instance` variable name + `.conf.*` settings before any worker imports.

---

## Next Steps

1. **M6:** Wire Qdrant as vector store backend (replace ChromaDB)
2. **M7:** SAP HANA connection pooling (SQLAlchemy async)
3. **M8:** Kubernetes HPA — autoscale Celery workers based on RabbitMQ queue depth
4. **M9:** LeanIX agent governance integration
5. **M10:** Multi-tenant isolation — separate Memgraph subgraphs per BU/company code
