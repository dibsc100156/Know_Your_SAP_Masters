# KYSM Level-5 Roadmap â Consolidated Implementation Status
**Last Updated:** April 12, 2026 | Project: Know Your SAP Masters (SAP Masters)

---

## Executive Summary

The KYSM architecture is a 5-Pillar RAG system augmented by 9 execution phases,
2 infrastructure migrations, and a suite of Harness Engineering principles that
collectively move the chatbot from a static Q&A tool to an autonomous,
self-healing, threat-aware enterprise agent.

---

## 5-Pillar RAG Architecture

| Pillar | Name | Component | Status |
|--------|------|-----------|--------|
| 1 | Role-Aware Security | `security.py` â SAPAuthContext, AuthContext masking, denied_tables | â Working |
| 2 | Agentic Orchestrator | `orchestrator.py` â `run_agent_loop()`, 8-step execution flow | â Working |
| 3 | Schema RAG | Qdrant + ChromaDB dual-backend, `schema_lookup()` | â Working |
| 4 | SQL Pattern RAG | `sql_pattern_lookup()`, 68+ patterns across 18 domains | â Working |
| 5 | Graph RAG | NetworkX FK graph, `AllPathsExplorer`, `TemporalGraphRAG`, Meta-Path Library | â Working |
| 5Â½ | Graph Embedding Search | Node2Vec + text hybrid, ChromaDB collections | â Working |

---

## 9-Phase Execution Roadmap

| Phase | Name | Description | Status |
|-------|------|-------------|--------|
| 0 | Meta-Path Match | Fast-path template matching (14 pre-computed JOIN paths) | â Working |
| 1 | Schema RAG | Qdrant semantic search over DDIC metadata | â Working |
| 1.5 | Graph Embedding | Node2Vec structural + text hybrid table discovery | â Working |
| 1.75 | QM Semantic Search | 20yr QM notification long-text semantic search | â Working |
| 2 | SQL Pattern RAG | ChromaDB proven SQL patterns (18 domains) | â Working |
| 2b | Temporal Detection | Date/fiscal anchor detection â temporal filters | â Working |
| 2c | Phase 7 Temporal Engine | FY analysis, CLV, Supplier SPI, Economic Cycle | â Working |
| 2d | Phase 8 Negotiation Briefing | CLV, PSI, churn risk, BATNA synthesis | â Working |
| 3 | Graph RAG | All-ranked-paths â best JOIN via NetworkX | â Working |
| 4 | SQL Assembly | MANDT injection + AuthContext + Temporal filters | â Working |
| 5 | Critique Gate | 7-point SQL validation (SELECT-only, MANDT, JOIN sanity, LIMIT) | â Working |
| 5.5 | **Validation Harness** | `SELECT COUNT(*)` dry-run â syntax validation â autonomous fix | â **NEW â IMPLEMENTED** |
| 6 | Self-Healing | Rule-based SQL correction (10 error codes â 6 heal strategies) | â Working |
| 6b | **Memory Compounding** | Auto-vectorize healed SQL back into Qdrant pattern store | â **NEW â IMPLEMENTED** |
| 6c | **Proactive Threat Sentinel** | 6 threat engines + dynamic AuthContext tightening | â **NEW â IMPLEMENTED** |
| 7 | Execution | SAP HANA mock executor (swap `hdbcli` for real connection) | â Working (mock) |
| 8 | Result Masking | Role-based column redaction (Pillar 1) | â Working |
| 9 | Frontend Modernization | 8-phase + confidence gauge + signal table + dark card | â Working |

---

## Memgraph Migration (M1âM6)

| Phase | Description | Status |
|-------|-------------|--------|
| M1 | Memgraph 2.12.0 + Lab â Docker Compose | â Complete |
| M2 | Cypher port â replace NetworkX with Memgraph queries | ð§ Pending |
| M3 | `use_memgraph` flag in main.py | ð§ Pending |
| M4 | Qdrant cluster migration (Schema + Pattern RAG) | ð§ Pending |
| M5 | Celery async worker pool | ð§ Pending |
| M6 | Load testing + production tuning | ð§ Pending |

---

## Harness Engineering â Implemented Principles

### â Phase 5.5: Deep Harnessing via Sandboxed Validation
- **File:** `backend/app/tools/sql_executor.py`, `backend/app/agents/orchestrator.py`
- **Flow:** `SELECT COUNT(*)` dry-run â error code capture â SelfHealer â re-test â execute
- **Error codes handled:** `37000`, `ORA-01476`, `ORA-00942`, `ORA-01799`, `SAP_AUTH`

### â Phase 6b: Automated Memory Compounding (Qdrant Vectorization)
- **File:** `backend/app/agents/orchestrator.py` â Step 8b
- **Flow:** Self-heal success â build intent string â `store_manager.load_domain()` â Qdrant upsert
- **Effect:** AI expands its own pattern library autonomously with every healed query

### â Phase 6c: Proactive Threat Sentinel
- **File:** `backend/app/core/security_sentinel.py` (32KB)
- **Modes:** DISABLED | AUDIT | ENFORCING
- **Threat Engines:** CROSS_MODULE_ESCALATION, SCHEMA_ENUMERATION, DENIED_TABLE_PROBE, DATA_EXFILTRATION, TEMPORAL_INFERENCE, ROLE_IMPERSONATION
- **Actions:** Dynamic AuthContext tightening + SIEM/webhook alerts
- **Integration:** Pre-execution gate in orchestrator; verdict in API `"sentinel"` key

---

## Pending Work

### P0 â Real SAP HANA Connection
Wire `hdbcli` to replace mock executor. This is the final production barrier.

### P1 â BAPI Workflow Harness (Read-to-Write)
Build transaction tool harness for autonomous SAP writes:
- `BAPI_PO_CHANGE` â Update PO delivery dates
- `BAPI_VENDOR_CREATE` â Create vendor master
- `BAPI_MATERIAL_SAVEDATA` â Create/update materials
- `BAPI_SALESORDER_CHANGE` â Modify sales orders

### P2 â Multi-Agent Domain Swarms
Break `run_agent_loop` into Planner Agent + Domain Agents (MM, FI, SD, QM) for collaborative cross-module reasoning.

### P3 â 50-Query Benchmark Suite
Golden dataset to feed Eval Alerting with real failure signals.

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `backend/app/agents/orchestrator.py` | Main agentic loop (Pillar 2) |
| `backend/app/core/security.py` | AuthContext + SecurityMesh (Pillar 1) |
| `backend/app/core/security_sentinel.py` | **NEW** â Proactive Threat Sentinel |
| `backend/app/core/self_healer.py` | SQL self-healing engine (Phase 6) |
| `backend/app/core/vector_store.py` | Dual-backend Qdrant + ChromaDB manager |
| `backend/app/core/graph_embedding_store.py` | Node2Vec + text hybrid (Pillar 5Â½) |
| `backend/app/core/meta_path_library.py` | 14 meta-paths, 22+ JOIN variants |
| `backend/app/core/graph_store.py` | NetworkX FK graph + AllPathsExplorer + TemporalGraphRAG |
| `backend/app/core/memory_layer.py` | Persistent memory (Phase 4) |
| `backend/app/tools/sql_executor.py` | SAP HANA executor (mock + real hdbcli) |
| `backend/app/agents/orchestrator_tools.py` | Tool registry + 12 tool implementations |
| `docs/KYSM_HARNESS_ENGINEERING.md` | Harness Engineering principles + implementation |
| `docs/MEMGRAPH_MIGRATION_GUIDE.md` | Memgraph Phase M1âM6 migration guide |

---

## Multi-Agent Domain Swarm Architecture â â LIVE (April 12, 2026)

| Component | File | Status |
|---|---|---|
| Domain Agents (7 specialists) | `domain_agents.py` | â Working |
| Planner Agent + Complexity Analyzer | `swarm/planner_agent.py` (19KB) | â **LIVE** |
| Synthesis Agent (merge + rank + conflicts) | `swarm/synthesis_agent.py` (16KB) | â **LIVE** |
| Swarm entry point | `swarm/__init__.py` (2KB) | â **LIVE** |
| Orchestrator `use_swarm` flag + API wiring | `orchestrator.py`, `api/endpoints/chat.py` | â **LIVE** |
| Frontend default `use_swarm=True` + swarm UI | `frontend/app.py` | â **LIVE** |
| Inter-Agent Message Bus | â | ð§ Planned |
| Agent-to-Agent Negotiation Protocol | â | ð§ Planned |
| Swarm Autoscaling (Celery workers) | â | ð§ Planned |

### Bugs Fixed During Swarm Activation
1. `tables_involved` referenced before initialization in sentinel gate â early init added before sentinel evaluation
2. `cross_agent` `list index out of range` â `primary_tables = []` caused crash in `_mask_results` â guard added: `table = self.primary_tables[0] if self.primary_tables else ""`
3. `abs(min(vals), 0.01)` Python syntax error in `synthesis_agent` â fixed to `max(abs(min(vals)), 0.01)`

### Live Test Results (localhost:8001)
| Query | Swarm Routing | Agents | Result |
|---|---|---|---|
| vendor open POs > 50k + material | `cross_module` | pur + cross | â 2 records |
| vendor payment terms vs customer credit | `cross_module` | bp + cross | â 2 records |
| quality inspection results + material | `cross_module` | mm + qm + cross | â 2 records |

### API Usage
```python
# Swarm mode (multi-agent parallel)
result = run_agent_loop(query, auth, use_swarm=True)

# Monolith mode (single orchestrator)
result = run_agent_loop(query, auth, use_swarm=False)
```

### Swarm Response Fields (new in API)
`swarm_routing`, `planner_reasoning`, `agent_summary`, `domain_coverage`, `conflicts`, `complexity_score`, `agent_count`
