# KYSM Level-5 Roadmap — Consolidated Implementation Status
**Last Updated:** April 15, 2026 | Project: Know Your SAP Masters (SAP Masters)

---

## Executive Summary

The KYSM architecture is a 5-Pillar RAG system augmented by 12 execution phases,
2 infrastructure migrations (Memgraph M1–M6, Qdrant cluster), and a suite of
Harness Engineering principles that collectively move the chatbot from a static
Q&A tool to an autonomous, self-healing, threat-aware, multi-agent enterprise
assistant.

**Infrastructure Status (April 15, 2026):**
- Qdrant ✅ ACTIVE — 4 collections (sap_schema, sql_patterns, graph_node_embeddings, graph_table_context)
- Memgraph ✅ ACTIVE — 114 nodes / 47 edges loaded
- ChromaDB: Retained for local dev fallback only
- RabbitMQ ✅ ACTIVE — amqp://sapmasters:sapmasters123@localhost:5672//
- Redis ✅ ACTIVE — localhost:6379/0
- Celery Worker ✅ ACTIVE — 4 threads, queues: agent + priority

---

## 5-Pillar RAG Architecture

| Pillar | Name | Component | Status |
|--------|------|-----------|--------|
| 1 | Role-Aware Security | `security.py` — SAPAuthContext, AuthContext masking, denied_tables | ✅ Working |
| 2 | Agentic Orchestrator | `orchestrator.py` — `run_agent_loop()`, 10-step execution flow | ✅ Working |
| 3 | Schema RAG | Qdrant + ChromaDB dual-backend, `schema_lookup()` | ✅ Working |
| 4 | SQL Pattern RAG | `sql_pattern_lookup()`, 68+ patterns across 18 domains | ✅ Working |
| 5 | Graph RAG | NetworkX FK graph, `AllPathsExplorer`, `TemporalGraphRAG`, Meta-Path Library | ✅ Working |
| 5½ | Graph Embedding Search | Node2Vec + text hybrid, ChromaDB collections | ✅ Working |

---

## 12-Phase Execution Roadmap

| Phase | Name | Description | Status |
|-------|------|-------------|--------|
| 0 | Meta-Path Match | Fast-path template matching (14 pre-computed JOIN paths) | ✅ Working |
| 1 | Schema RAG | Qdrant semantic search over DDIC metadata | ✅ Working |
| 1.5 | Graph Embedding | Node2Vec structural + text hybrid table discovery | ✅ Working |
| 1.75 | QM Semantic Search | 20yr QM notification long-text semantic search | ✅ Working |
| 2 | SQL Pattern RAG | Qdrant proven SQL patterns (18 domains) | ✅ Working |
| 2b | Temporal Detection | Date/fiscal anchor detection → temporal filters | ✅ Working |
| 2c | Phase 7 Temporal Engine | FY analysis, CLV, Supplier SPI, Economic Cycle | ✅ Working |
| 2d | Phase 8 Negotiation Briefing | CLV, PSI, churn risk, BATNA synthesis | ✅ Working |
| 3 | Graph RAG | All-ranked-paths → best JOIN via NetworkX + AllPathsExplorer | ✅ Working |
| 4 | SQL Assembly | MANDT injection + AuthContext + Temporal filters | ✅ Working |
| 5 | Critique Gate | 7-point SQL validation (SELECT-only, MANDT, JOIN sanity, LIMIT) | ✅ Working |
| **5.5** | **Validation Harness** | `SELECT COUNT(*)` dry-run → syntax validation → autonomous fix | ✅ **NEW — IMPLEMENTED** |
| 6 | Self-Healing | Rule-based SQL correction (10 error codes → 6 heal strategies) | ✅ Working |
| **6b** | **Memory Compounding** | Auto-vectorize healed SQL back into Qdrant pattern store | ✅ **NEW — IMPLEMENTED** |
| **6c** | **Proactive Threat Sentinel** | 6 threat engines + dynamic AuthContext tightening | ✅ **NEW — IMPLEMENTED** |
| 7 | Execution | SAP HANA mock executor (swap `hdbcli` for real connection) | ✅ Working (mock) |
| 8 | Result Masking | Role-based column redaction (Pillar 1) | ✅ Working |
| 9 | Frontend Modernization | 8-phase + confidence gauge + signal table + dark card | ✅ Working |
| **10** | **Multi-Agent Domain Swarm** | Planner + Domain Agents + Synthesis Agent — LIVE port 8001 | ✅ **NEW — LIVE** |
| **11** | **Automated Meta-Harness** | Agentic proposer loop: trace analysis → YAML recs → auto-patch | ✅ **NEW — LIVE** |
| **12** | **Quality Metrics Eval** | `QualityEvaluator` computes trajectory adherence and correctness score from Redis traces | ✅ **NEW — LIVE** |
| **12b** | **Trajectory Log** | Structured reasoning-span log per run: step, decision, reasoning, metadata stored in `HarnessRun.trajectory_log[]` and returned in API | ✅ **NEW — LIVE** |

---

## Memgraph Migration (M1–M6)

| Phase | Description | Status |
|-------|-------------|--------|
| M1 | Memgraph 2.12.0 + Lab — Docker Compose | ✅ Complete |
| M2 | Cypher port — replace NetworkX with Memgraph queries | 🚧 Pending |
| M1 | Memgraph schema init + load (init_schema.cql) | ✅ COMPLETE |
| M2 | Native Cypher path queries (find_all_ranked_paths_native) | ✅ COMPLETE |
| M3 | `use_memgraph` flag in main.py | 🚧 Pending |
| M4 | Qdrant cluster migration (Schema RAG + SQL Pattern RAG + QM + Graph Embeddings) | ✅ COMPLETE |
| M5 | Celery async worker pool (RabbitMQ + Redis + 4-thread worker) | ✅ COMPLETE |
| M6 | Load testing + production tuning | 🚧 Pending |
| M7 | Real SAP HANA connection (hana_pool.py, HANA_MODE=pool) | 🚧 Pending |

> **Note:** Memgraph 2.x Cypher limitations — `LENGTH(path)`, `relationships(path)`, `shortestPath()`, path-list comprehensions are NOT implemented. Native pattern matching used.

---

## Harness Engineering — Implemented Principles

### ✅ Phase 5.5: Deep Harnessing via Sandboxed Validation
- **File:** `backend/app/tools/sql_executor.py`, `backend/app/agents/orchestrator.py`
- **Flow:** `SELECT COUNT(*)` dry-run → error code capture → SelfHealer → re-test → execute
- **Error codes handled:** `37000`, `ORA-01476`, `ORA-00942`, `ORA-01799`, `SAP_AUTH`

### ✅ Phase 6b: Automated Memory Compounding (Qdrant Vectorization)
- **File:** `backend/app/agents/orchestrator.py` — Step 8b
- **Flow:** Self-heal success → build intent string → `store_manager.load_domain()` → Qdrant upsert
- **Effect:** AI expands its own pattern library autonomously with every healed query

### ✅ Phase 6c: Proactive Threat Sentinel
- **File:** `backend/app/core/security_sentinel.py` (32KB)
- **Modes:** DISABLED | AUDIT | ENFORCING
- **Threat Engines:** CROSS_MODULE_ESCALATION, SCHEMA_ENUMERATION, DENIED_TABLE_PROBE, DATA_EXFILTRATION, TEMPORAL_INFERENCE, ROLE_IMPERSONATION
- **Actions:** Dynamic AuthContext tightening + SIEM/webhook alerts
- **Integration:** Pre-execution gate in orchestrator; verdict in API `"sentinel"` key

---

## Pending Work

### P0 — Real SAP HANA Connection
Wire `hdbcli` to replace mock executor. This is the final production barrier.

### P1 — BAPI Workflow Harness (Read-to-Write)
Build transaction tool harness for autonomous SAP writes:
- `BAPI_PO_CHANGE` — Update PO delivery dates
- `BAPI_VENDOR_CREATE` — Create vendor master
- `BAPI_MATERIAL_SAVEDATA` — Create/update materials
- `BAPI_SALESORDER_CHANGE` — Modify sales orders

### P2 — Multi-Agent Domain Swarms — Inter-Agent Message Bus
Break domain agents out of star-topology via a shared message bus for direct agent-to-agent negotiation.

### P3 — 50-Query Benchmark Suite
Golden dataset to feed Eval Alerting with real failure signals.

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `backend/app/agents/orchestrator.py` | Main agentic loop (Pillar 2) |
| `backend/app/core/security.py` | AuthContext + SecurityMesh (Pillar 1) |
| `backend/app/core/security_sentinel.py` | **NEW** — Proactive Threat Sentinel (32KB) |
| `backend/app/core/self_healer.py` | SQL self-healing engine (Phase 6) |
| `backend/app/core/vector_store.py` | Dual-backend Qdrant + ChromaDB manager |
| `backend/app/core/graph_embedding_store.py` | Node2Vec + text hybrid (Pillar 5½) |
| `backend/app/core/meta_path_library.py` | 14 meta-paths, 22+ JOIN variants |
| `backend/app/core/graph_store.py` | NetworkX FK graph + AllPathsExplorer + TemporalGraphRAG |
| `backend/app/core/memory_layer.py` | Persistent memory (Phase 4) |
| `backend/app/tools/sql_executor.py` | SAP HANA executor (mock + real hdbcli) |
| `backend/app/agents/orchestrator_tools.py` | Tool registry + 12 tool implementations |
| `backend/app/agents/swarm/planner_agent.py` | **NEW** — Planner Agent + Complexity Analyzer (19KB) |
| `backend/app/agents/swarm/synthesis_agent.py` | **NEW** — Synthesis Agent (16KB) |
| `backend/bolt_load.py` | Neo4j Bolt loader for Memgraph schema |
| `docs/KYSM_HARNESS_ENGINEERING.md` | Harness Engineering principles + implementation |
| `docs/MULTI_AGENT_SWARM_ARCHITECTURE.md` | Full swarm architecture documentation |
| `docs/MEMGRAPH_MIGRATION_GUIDE.md` | Memgraph Phase M1–M6 migration guide |

---

## Multi-Agent Domain Swarm Architecture — ✅ LIVE (April 12, 2026, Port 8001)

| Component | File | Status |
|---|---|---|
| Domain Agents (7 specialists) | `domain_agents.py` | ✅ Working |
| Planner Agent + Complexity Analyzer | `swarm/planner_agent.py` (19KB) | ✅ **LIVE** |
| Synthesis Agent (merge + rank + conflicts) | `swarm/synthesis_agent.py` (16KB) | ✅ **LIVE** |
| Swarm entry point | `swarm/__init__.py` (2KB) | ✅ **LIVE** |
| Orchestrator `use_swarm` flag + API wiring | `orchestrator.py`, `api/endpoints/chat.py` | ✅ **LIVE** |
| Frontend default `use_swarm=True` + swarm UI | `frontend/app.py` | ✅ **LIVE** |
| Bug: `tables_involved` early init | `orchestrator.py` | ✅ Fixed |
| Bug: `cross_agent` empty guard | `domain_agents.py` | ✅ Fixed |
| Bug: `abs(min(vals), 0.01)` syntax | `synthesis_agent.py` | ✅ Fixed |
| Inter-Agent Message Bus | — | 🚧 Planned |
| Agent-to-Agent Negotiation Protocol | — | 🚧 Planned |
| Swarm Autoscaling (Celery workers) | — | 🚧 Planned |

### Bugs Fixed During Swarm Activation
1. `tables_involved` referenced before initialization → early init added before sentinel evaluation
2. `cross_agent` `list index out of range` → `_mask_results` guard for empty `primary_tables` → guard: `table = self.primary_tables[0] if self.primary_tables else ""`
3. `abs(min(vals), 0.01)` Python syntax error in `synthesis_agent` → `max(abs(min(vals)), 0.01)`

### Live Test Results (localhost:8001)
| Query | Swarm Routing | Agents | Result |
|---|---|---|---|
| vendor open POs > 50k + material | `cross_module` | pur + cross | ✅ 2 records |
| vendor payment terms vs customer credit | `cross_module` | bp + cross | ✅ 2 records |
| quality inspection results + material | `cross_module` | mm + qm + cross | ✅ 2 records |

### API Usage
```python
# Swarm mode (multi-agent parallel)
result = run_agent_loop(query, auth, use_swarm=True)

# Monolith mode (single orchestrator)
result = run_agent_loop(query, auth, use_swarm=False)
```

### Swarm Response Fields (new in API)
`swarm_routing`, `planner_reasoning`, `agent_summary`, `domain_coverage`, `conflicts`, `complexity_score`, `agent_count`
