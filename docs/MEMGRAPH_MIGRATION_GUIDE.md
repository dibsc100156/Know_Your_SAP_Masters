# Memgraph Migration Guide — Know Your SAP Masters
**From:** in-memory NetworkX graph  
**To:** Memgraph-backed graph runtime with a local NetworkX mirror  
**Last Updated:** April 22, 2026

---

## Executive Summary

**Status labels used in this guide:** ✅ Complete | 🟡 Partial | 🚧 Planned

The Memgraph migration is largely complete.

- **Graph storage/runtime:** Memgraph is wired and can replace the global `graph_store` at startup.
- **Traversal model:** the system still keeps a **local NetworkX mirror** for compatibility and low-latency graph algorithms.
- **Native Memgraph path-finding:** available for ranked multi-path exploration via `find_all_ranked_paths_native()`.
- **Vector search:** **Qdrant**, not Memgraph, is the active vector backend for schema/pattern search, graph embeddings, and QM semantic search.
- **Remaining gap:** real SAP HANA production cutover is still not the default runtime; pool-backed HANA execution exists in code but is not the default deployment mode.

---

## Implementation Status

| Phase | Area | Status | Notes |
|---|---|---|---|
| M1 | Memgraph Docker stack + adapter scaffold | ✅ Complete | `docker-compose.memgraph.yml`, Memgraph Lab, `memgraph_adapter.py` |
| M2 | Native Memgraph graph querying | ✅ Complete | `AllPathsExplorer` uses `find_all_ranked_paths_native()` when available |
| M3 | FastAPI startup wiring | ✅ Complete | `main.py` activates Memgraph when `MEMGRAPH_URI` is set |
| M4 | Celery worker fleet | ✅ Complete | `celery_app_instance`, `@shared_task`, RabbitMQ-backed async execution |
| M5 | Redis dialog state | ✅ Complete | Redis-backed dialog/session state with enforcement controls |
| M6 | Qdrant migration | ✅ Complete | Schema RAG, SQL patterns, graph embeddings, and QM semantic search support Qdrant |
| M7 | SAP HANA connection pooling | 🟡 Partial | `hana_pool.py` and `HANA_MODE=pool` exist, but real HANA is still not the default live path |
| M8 | Kubernetes autoscaling | ✅ Complete | KEDA `ScaledObject` manifests for Celery workers are present |
| M9 | Multi-tenant isolation | ✅ Complete | Tenant-aware labels via `TENANT_ID` in Memgraph adapter |

**Overall status:** ✅ Complete for M1-M6 and M8-M9; 🟡 Partial for M7.

---

## Current Architecture

```text
FastAPI / Orchestrator
        |
        | use_memgraph() when MEMGRAPH_URI is set
        v
MemgraphGraphRAGManager
        |
        | builds / syncs
        v
Memgraph (persistent graph store)
        |
        | local mirror for compatibility + algorithms
        v
NetworkX mirror (in-process)
```

### Key design choice
The system is **not** “Memgraph only.” It is a **hybrid runtime**:

- **Memgraph** provides persistence and native graph querying.
- **NetworkX mirror** preserves existing graph APIs and supports algorithms still running in-process.

This is intentional and matches the current codebase.

---

## What Changed

### Before
- Graph existed only in-process via `graph_store.py`
- No persistent graph database
- Vector search relied on ChromaDB

### Now
- Memgraph can back the global graph runtime
- Startup can swap `graph_store` to the Memgraph-backed shim
- Ranked path exploration can execute natively in Memgraph
- Qdrant is the active scalable vector backend
- Tenant labels are supported in Memgraph
- Celery + Redis + RabbitMQ infrastructure is in place for horizontal scale

---

## What Did **Not** Change

These APIs remain stable for the orchestrator layer:

- `traverse_graph()`
- `find_path()`
- `get_neighbors()`
- `get_subgraph_context()`
- `stats()`

The migration preserved compatibility by keeping the NetworkX mirror and shim layer.

---

## Phase Details

## M1 — Memgraph Stack and Adapter

### Delivered
- `docker/docker-compose.memgraph.yml`
- `backend/app/core/memgraph_adapter.py`
- Memgraph Lab on port `3000`
- Memgraph Bolt on port `7687`

### Notes
The adapter is no longer just a scaffold in practice. It connects, loads schema, builds the NetworkX mirror, and exposes the graph API expected by the rest of the system.

---

## M2 — Native Memgraph Querying

### Delivered
- `find_all_ranked_paths_native()` in `memgraph_adapter.py`
- `AllPathsExplorer.find_all_ranked_paths()` prefers the native Memgraph path when available
- `init_schema.cql` loading + regex parsing fixes
- sync path to push missing NetworkX edges into Memgraph

### Important accuracy note
Only part of traversal is native today:

- **Native in Memgraph:** ranked multi-path exploration via variable-length Cypher matching
- **Still on NetworkX mirror:** shortest-path traversal, neighborhood traversal, centrality-heavy logic, and compatibility paths

So the correct description is **hybrid graph execution**, not “everything moved to Memgraph.”

---

## M3 — FastAPI Startup Wiring

### Delivered
`backend/app/main.py` now activates Memgraph on startup when `MEMGRAPH_URI` is present.

### Actual startup behavior
```python
memgraph_uri = os.environ.get("MEMGRAPH_URI", "")
if memgraph_uri:
    from app.core import use_memgraph
    tenant = os.environ.get("TENANT_ID", "default")
    use_memgraph(uri=memgraph_uri, tenant_id=tenant)
else:
    # stay on pure NetworkX
```

### Relevant environment variables
| Variable | Default | Purpose |
|---|---|---|
| `MEMGRAPH_URI` | empty | Enables Memgraph mode when set |
| `TENANT_ID` | `default` | Tenant-scoped Memgraph labels |
| `REDIS_HOST` | `localhost` | Redis host |
| `VECTOR_STORE_BACKEND` | `chroma` | Set to `qdrant` to enable Qdrant |

### Example
```bash
# Windows
set MEMGRAPH_URI=bolt://localhost:7687
set TENANT_ID=SP_GLOBAL_ENERGY
set VECTOR_STORE_BACKEND=qdrant
```

---

## M4 — Celery Worker Fleet

### Delivered
- `backend/app/workers/celery_app.py`
- `celery_app_instance` naming fix to avoid circular import ambiguity
- `@shared_task` task registration pattern
- RabbitMQ-backed task routing
- queue definitions for agent and domain-specific work

### Accuracy note
This phase is complete from a code and deployment-manifest standpoint. It is not just a plan anymore.

---

## M5 — Redis Dialog State

### Delivered
- Redis-backed session/dialog state
- fail-loud enforcement support
- retry/backoff behavior

### Behavior
- Redis is used when configured and reachable
- on Windows, `REDIS_HOST=localhost` is typically required outside Docker

---

## M6 — Qdrant Migration

### Delivered
Qdrant support is fully present across the migration stack:

- `backend/app/core/vector_store.py` — dual backend manager
- `backend/app/core/qdrant_vector_store.py` — Qdrant-backed schema/pattern store
- `backend/app/core/graph_embedding_store.py` — graph embeddings on Qdrant
- `backend/app/core/qdrant_qm_wrapper.py` — Qdrant wrapper for QM semantic search
- `backend/app/core/qm_semantic_search.py` — supports `VECTOR_STORE_BACKEND=qdrant`

### Important correction
The active scalable vector path is **Qdrant**, not Memgraph native vector search.

`memgraph_adapter.py` still marks Memgraph-native vector search as **pending / not implemented**.

### Current collections in play
| Collection | Purpose |
|---|---|
| `sap_schema` | DDIC/schema metadata |
| `sql_patterns` | SQL pattern retrieval |
| `graph_node_embeddings` | Node2Vec structural embeddings |
| `graph_table_context` | graph-aware semantic table context |
| `qm_semantic_notifications` | QM long-text semantic search |

---

## M7 — SAP HANA Connection Pooling

### Current state
This phase is implemented in code, but it is not yet the default production runtime.

### What exists
- `backend/app/tools/hana_pool.py`
- `backend/app/tools/sql_executor.py`
- `HANA_MODE=pool` execution path
- pool sizing, timeouts, circuit breaker, MANDT enforcement hooks

### What is still pending
- real SAP HANA cutover as the normal runtime path
- production validation against a live system
- full replacement of the current default mock execution mode

### Recommended status wording
**🟡 Partial** — implemented in code, not yet the default production runtime

---

## M8 — Kubernetes Autoscaling

### Delivered
KEDA-backed scaling manifests exist in `k8s/base/`, including `ScaledObject` definitions for Celery workers.

### Evidence in repo
- `k8s/base/celery-primary.yaml`
- `k8s/base/celery-replica.yaml`

---

## M9 — Multi-Tenant Isolation

### Delivered
The Memgraph adapter supports tenant-specific labels:

```python
self.tenant_label = f"Tenant_{tenant_id}"
```

Nodes and relationships are written and queried with tenant-aware labels when Memgraph mode is enabled.

### Correction
Older drafts of this guide labeled this section as **M10**. That was inconsistent with the status table. The correct phase label here is **M9**.

---

## Activation Guide

### Local stack
```bash
docker compose -f docker/docker-compose.memgraph.yml up -d
```

### Backend env
```bash
set MEMGRAPH_URI=bolt://localhost:7687
set VECTOR_STORE_BACKEND=qdrant
set REDIS_HOST=localhost
set TENANT_ID=default
```

### Expected behavior
- backend starts with Memgraph enabled
- vector store initializes with Qdrant when configured
- Redis dialog manager connects
- graph APIs continue to work through the shim

---

## Verification Checklist

### Memgraph
- `http://localhost:3000` opens Memgraph Lab
- Bolt endpoint reachable on `localhost:7687`
- backend startup logs show Memgraph activation

### Graph backend
Use:
- `GET /debug/graph-backend`
- `GET /health`

Expected:
- Memgraph reachable when configured
- NetworkX metadata counts present
- backend remains functional even if Memgraph is unavailable

### Qdrant
- `VECTOR_STORE_BACKEND=qdrant`
- Qdrant reachable on `localhost:6333`
- schema/pattern/graph/QM vector paths initialize successfully

---

## Troubleshooting

### Memgraph not activating
**Symptom:** backend stays on NetworkX only  
**Check:** `MEMGRAPH_URI` must be set; the current startup path does not force a default URI.

### Partial edge set in Memgraph
**Symptom:** Memgraph has fewer edges than NetworkX metadata  
**Cause:** `init_schema.cql` does not carry the full edge set used by the in-memory graph model  
**Current mitigation:** `_sync_nx_edges_to_memgraph()` adds missing edges from the NetworkX metadata

### Regex parse failures during schema load
Known fixes already applied:
- node regex bridge flag uses the correct capture group
- edge regex correctly matches `)-[` style edge patterns

### Redis hostname failure on Windows
Use:
```bash
set REDIS_HOST=localhost
```
not Docker service names like `redis` when running from the host OS.

### Celery circular import / `app` naming issue
Use `celery_app_instance` and import worker modules only after configuration is applied.

### Memgraph vector search confusion
Do **not** describe Memgraph vector search as active. In the current code, Memgraph-native vector search remains unimplemented; Qdrant is the real vector backend.

---

## Performance Positioning

| Capability | Current state |
|---|---|
| Graph persistence | Memgraph-backed |
| Compatibility graph APIs | NetworkX mirror |
| Ranked path exploration | Native Memgraph available |
| General shortest path / neighbor traversal | NetworkX mirror |
| Vector search | Qdrant |
| Async orchestration | Celery + RabbitMQ |
| Session/dialog state | Redis |
| Real SAP HANA runtime | 🟡 Partial |

---

## Files Most Relevant to This Migration

```text
backend/app/core/
  __init__.py
  memgraph_adapter.py
  graph_store.py
  vector_store.py
  qdrant_vector_store.py
  graph_embedding_store.py
  qm_semantic_search.py
  qdrant_qm_wrapper.py

backend/app/workers/
  celery_app.py
  orchestrator_tasks.py

backend/app/tools/
  hana_pool.py
  sql_executor.py

docker/
  docker-compose.memgraph.yml
  memgraph/init_schema.cql

k8s/base/
  celery-primary.yaml
  celery-replica.yaml

backend/app/main.py
```

---

## Recommended Next Steps

1. **Close M7 properly**
   - validate `HANA_MODE=pool` against a live SAP HANA system
   - make the real HANA path operational, not just available in code

2. **Benchmark the hybrid graph runtime**
   - compare native Memgraph path exploration vs NetworkX mirror paths under concurrency

3. **Document operational defaults clearly**
   - recommended local/dev env
   - recommended Docker env
   - recommended production env

4. **Keep the guide aligned with code**
   - avoid mixing old ChromaDB-era language with current Qdrant reality
   - avoid calling M9 “M10”
   - avoid implying Memgraph-native vector search is already live

---

## Bottom Line

The migration succeeded as a **hybrid architecture**:

- **Memgraph** is the persistent graph layer
- **NetworkX** remains the compatibility and algorithm mirror
- **Qdrant** is the production vector backend
- **Redis + RabbitMQ + Celery** provide distributed execution support

The biggest remaining gap is **real SAP HANA production activation**, not the Memgraph migration itself.
