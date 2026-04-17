# KYSM Level-5 Roadmap — Consolidated Implementation Status
**Last Updated:** April 17, 2026 | Project: Know Your SAP Masters (SAP Masters)

---

## Executive Summary

The KYSM architecture is a 5-Pillar RAG system augmented by 13 execution phases,
2 infrastructure migrations (Memgraph M1–M6, Qdrant cluster), and a suite of
Harness Engineering principles that collectively move the chatbot from a static
Q&A tool to an autonomous, self-healing, threat-aware, multi-agent enterprise
assistant.

**Infrastructure Status (April 16, 2026):**
- Qdrant ✅ ACTIVE — 4 collections (sap_schema, sql_patterns, graph_node_embeddings, graph_table_context)
- Memgraph ✅ ACTIVE — 114 nodes / **137 edges** (all NetworkX edges synced via `sync_nx_to_memgraph.py`; 151 total including bidirectional duplicates)
- ChromaDB: Retired — all collections migrated to Qdrant (Schema RAG, Pattern RAG, QM, Graph Embeddings)
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

## 13-Phase Execution Roadmap

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
| **5.5** | **Validation Harness** | `SELECT COUNT(*)` dry-run → syntax validation → autonomous fix | ✅ **IMPLEMENTED — Apr 12** |
| 6 | Self-Healing | Rule-based SQL correction (10 error codes → 6 heal strategies) | ✅ Working |
| **6b** | **Memory Compounding** | Auto-vectorize healed SQL back into Qdrant pattern store | ✅ **IMPLEMENTED — Apr 12** |
| **6c** | **Proactive Threat Sentinel** | 6 threat engines + dynamic AuthContext tightening | ✅ **IMPLEMENTED — Apr 12** |
| 7 | Execution | SAP HANA mock executor — swap `hdbcli` for real connection to close P0 | ✅ Working (mock) |
| 8 | Result Masking | Role-based column redaction (Pillar 1) | ✅ Working |
| 9 | Frontend Modernization | 8-phase + confidence gauge + signal table + dark card | ✅ **COMPLETE — Apr 5** |
| **10** | **Multi-Agent Domain Swarm** | Planner + Domain Agents + Synthesis Agent — ThreadPoolExecutor on Windows | ✅ **LIVE — Apr 12** |
| **10a** | **Agent-as-a-Graph 1.5:1 Routing** | AGENT_TOOL_GRAPH with context(1.5x) vs tool(1.0x) scoring | ✅ **IMPLEMENTED — Apr 15** |
| **10b** | **Context Isolation (File-Backed Handoffs)** | Plan state files per agent — no orchestrator history leakage | ✅ **IMPLEMENTED — Apr 15** |
| **11** | **Automated Meta-Harness** | `meta_harness_loop.py` (45KB) exists — ADVISORY MODE: collect→analyze→YAML→approve→patch | ✅ **Implemented** — Manual trigger only; NOT auto-wired into orchestrator |
| **12** | **Quality Metrics Eval** | `QualityEvaluator` (2.8KB) in `app/core/` — computes correctness_score + trajectory_adherence from Redis traces | ✅ **Implemented** — NOT wired into orchestrator; never auto-runs after queries |
| **12b** | **Trajectory Log** | `HarnessRun.trajectory_log[]` field — 12KB recorded per run in orchestrator.py | ✅ **Recording** — data captured but never analyzed; `QualityEvaluator` never called on it |
| Phase 13 | Inter-Agent Message Bus | ✅ IMPLEMENTED — `message_bus.py` (16.5KB) exists | Confirmed — Redis pub/sub + streams, 6 message types |
| Phase 13b | Negotiation Protocol | ✅ IMPLEMENTED — `negotiation_protocol.py` (24KB) exists | Confirmed — 4-phase engine, 6 strategies, SOURCE_AUTHORITY |

---

## Memgraph Migration (M1–M6)

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| M1 | Memgraph 2.12.0 + Lab — Docker Compose | ✅ Complete | |
| M1a | Memgraph schema init (`init_schema.cql`) | ✅ Complete | 47 edges |
| M1b | Edge sync from NetworkX (`sync_nx_to_memgraph.py`) | ✅ Complete | 104 missing edges added; 151 total |
| M2 | Native Cypher paths (`find_all_ranked_paths_native`, variable-length `[*..5]`) | ✅ Complete | Memgraph 2.x compatible |
| M3 | `use_memgraph` flag + `_sync_nx_edges_to_memgraph()` auto-sync at startup | ✅ Complete | Syncs all 137 NX edges on each start |
| M4 | Celery async worker pool (RabbitMQ + Redis + 4-thread solo worker) | ✅ Complete | 9 queues; `solo` pool on Windows |
| M5 | Redis Dialog State (hardened: retries, backoff, `REDIS_ENFORCE` fail-loud) | ✅ Complete | |
| M6 | Qdrant cluster migration (Schema RAG + SQL Pattern RAG + QM + Graph Embeddings) | ✅ Complete | 4 collections active |
| M7 | Load testing + production tuning (`pool_size >= 20`, p95 <= 300ms @ conc=10) | 🚧 Pending | 0% error @ conc=5; p95 773ms — needs conc=10 sign-off |
| M8 | Real SAP HANA connection (`hdbcli`, `hana_pool.py`, `HANA_MODE=pool`) | 🚧 Pending | Env: HANA_HOST, HANA_PORT, HANA_USER, HANA_PASSWORD |
| M9 | Kubernetes HPA — autoscale Celery workers (KEDA ScaledObjects) | ✅ Complete | Max 20 replicas; 300s cooldown |
| M10 | LeanIX agent governance integration (DPO reporting, middleware in main.py) | ✅ Complete | |
| M11 | Multi-tenant isolation — separate Memgraph subgraphs per BU/company code | ✅ Complete | `TENANT_ID` env wired |

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

## Priority Build Order (Post-Harness Engineering Review)

| # | Priority | Item | Phase | Notes |
|---|----------|------|-------|-------|
| 1 | 🔴 P0 | `agent_inbox.py` — agent message inbox + async inbox listener | Phase 13 | ✅ IMPLEMENTED — Apr 17; AgentInbox class + InboxManager |
| 2 | 🔴 P0 | `message_bus.py` + `negotiation_protocol.py` — verify against `message_dispatcher.py` coverage | Phase 13/13b | Check if dispatcher already covers bus + negotiation |
| 3 | 🔴 P0 | Ephemeral Task Environments — git worktree clone per task, unique port, log capture, teardown | **NEW** | Needed for 6hr agent runs |
| 4 | 🔴 P0 | DOM/Screenshot Validation — Chrome DevTools Protocol skills | **NEW** | Needed for full autonomy threshold |
| 5 | 🔴 P0 | Full Autonomous Pipeline — single prompt: validate→reproduce→fix→PR→merge | **NEW** | The "Ralph Wiggum Loop" end-to-end |
| 6 | ✅ DONE | Wire Phase 11 (`MetaHarnessLoop`) failure trigger | ✅ **WIRED — Apr 17** | `failure_trigger.py` fires background thread on ≥3 failures/hr (1hr cooldown) |
| 7 | ✅ DONE | Wire Phase 12 (`QualityEvaluator`) into orchestrator | ✅ **WIRED — Apr 17** | `QualityEvaluator.evaluate_run()` called after `complete_run()`, stores quality_score + trajectory_adherence in Redis via `hset_run_field()` |
| 8 | 🟡 P1 | `agent_inbox.py` — agent message inbox + async inbox listener | Phase 13 | Pending since Apr 12; unblocks swarm async message handling |
| 9 | 🟡 P1 | Doc-Gardening Agent — recurring stale doc scanner + fix PR | **NEW** | OpenAI's "doc-gardening" pattern; not yet built |
| 10 | 🟡 P1 | Ralph Wiggum PR Review Loop — agent self-review → cross-agent → auto-merge | **NEW** | Agent-to-agent PR review chain; not yet built |
| 11 | 🟡 P1 | Observability Query Interface — LogQL/PromQL agent-accessible | **NEW** | "Ensure startup completes in under 800ms"; not yet built |
| 12 | 🟡 P1 | Golden Principles Linters — mechanical taste enforcement | **NEW** | Shared utilities, no YOLO data, file size limits; not yet built |
| 13 | 🟡 P1 | Progressive Disclosure Linter — AGENTS.md ≤150 lines, cross-links valid | **NEW** | "Map, not manual" enforcement; not yet built |
| 14 | 🟡 P1 | Long-Running Agent Infrastructure — `soft_time_limit` increase, heartbeat | **NEW** | Support 6hr overnight agent runs; not yet built |
| 15 | 🟢 P2 | BAPI Workflow Harness (Read-to-Write) — `BAPI_PO_CHANGE`, `BAPI_VENDOR_CREATE` | P1 | Requires BEGIN/COMMIT/ROLLBACK + write-gate sentinel |
| 15 | 🟢 P2 | M6 Load Testing sign-off — p95 ≤ 300ms @ conc=10 | P1 | Current p95 773ms; needs conc=10 sign-off |
| 16 | 🟢 P2 | Real SAP HANA connection (`hdbcli`) | P0 | Final production barrier |

## Integration Gaps (Wired but Never Called)

The following components exist and are imported but **never automatically invoked** in the orchestrator:

| Component | File | Status | Integration Gap |
|-----------|------|--------|----------------|
| MetaHarnessLoop | `meta_harness_loop.py` + `failure_trigger.py` | ✅ WIRED | Background thread fires on ≥3 failures/hr (1hr cooldown); `apply_recommendations()` auto-applies P3/P4 low-risk patches |
| QualityEvaluator | `quality_evaluator.py` | ✅ WIRED | Called in orchestrator `complete_run()` path; stores correctness_score + trajectory_adherence in Redis; `trajectory_log` analyzed via `_compute_trajectory_adherence()` |
| Trajectory Log | `HarnessRun.trajectory_log[]` | ✅ ANALYZED | Consumed by `QualityEvaluator._compute_trajectory_adherence()` on every orchestrator run; scored and stored in Redis |
| Message Bus | `message_bus.py` | ✅ Wired | ✅ Properly integrated via `message_dispatcher.py` |
| Negotiation Protocol | `negotiation_protocol.py` | ✅ Wired | ✅ Properly integrated via `message_dispatcher.py` |

### Actions Required:
- **Phase 11 Integration:** ✅ COMPLETE — `failure_trigger.py` (12.6KB) non-blocking background thread on cascade; cooldown prevents re-trigger within 1hr
- **Phase 12 Integration:** ✅ COMPLETE — `QualityEvaluator.evaluate_run()` called after `complete_run()`; stores score + adherence via `hset_run_field()` in Redis
- **Phase 12b:** ✅ COMPLETE — `trajectory_log` passed to `_compute_trajectory_adherence()` on every run; sequence penalties for backtracking applied

### Full Harness Engineering Gap Analysis
See: `docs/HARNESS_ENGINEERING_GAP_ANALYSIS.md` — Full comparison of OpenAI's 14-point capability checklist against KYSM implementation.

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
| `backend/app/core/eval_dashboard.py` | Eval Dashboard — structured eval reports from query history (Phase 5) |
| `backend/app/core/eval_alerting.py` | Eval Alerting — threshold alerts (success_rate, latency, score drop) wired to Redis |
| `backend/app/core/self_improver.py` | Autonomous Self-Improvement — pattern promotion/demotion + ghost injection (Phase 6) |
| `backend/app/core/harness_runs.py` | Harness Runs Table — Redis flight recorder for every query (Phase 7+) |

| `backend/app/core/agent_inbox.py` | AgentInbox per-agent inbox listener + InboxManager (19.7KB) — Phase 13 async messaging |
| `backend/app/core/failure_trigger.py` | Phase 11 failure trigger — non-blocking MetaHarnessLoop on ≥3 failures/hr (12.6KB) |
| `backend/app/core/quality_evaluator.py` | QualityEvaluator — computes correctness_score + trajectory_adherence from HarnessRun traces (2.8KB) |
| `backend/app/agents/swarm/contracts.py` | Typed Sub-Agent Output Contracts — 9 contracts (7 domain + base + SWARM), `validate_contract()` before merge |
| `backend/app/core/message_bus.py` | Redis pub/sub + streams MessageBus — 6 message types (Phase 13) |
| `backend/app/core/negotiation_protocol.py` | 4-phase Negotiation Engine — ASSERTING→CHALLENGING→NEGOTIATING→COMMITTED (Phase 13b) |
| `backend/app/tools/sql_executor.py` | SAP HANA executor (mock + real hdbcli) |
| `backend/app/agents/orchestrator_tools.py` | Tool registry + 12 tool implementations |
| `backend/app/agents/swarm/planner_agent.py` | **NEW** — Planner Agent + Complexity Analyzer (19KB) |
| `backend/app/agents/swarm/synthesis_agent.py` | **NEW** — Synthesis Agent (16KB) |
| `backend/app/workers/domain_tasks.py` | **NEW —** Per-domain Celery tasks with queue routing (pur/bp/mm/sd/qm/wm/cross queues) |
| `docs/KYSM_HARNESS_ENGINEERING.md` | Harness Engineering principles + implementation |
| `docs/HARNESS_ENGINEERING_TRENDS.md` | Top 10 Harness Engineering trends + production use cases (Karpathy, Solo Swift Crafter, Cyril Imhof) |
| `docs/MULTI_AGENT_SWARM_ARCHITECTURE.md` | Full swarm architecture documentation |
| `docs/MEMGRAPH_MIGRATION_GUIDE.md` | Memgraph Phase M1–M11 migration guide |
| `docs/SANDBOX_ARCHITECTURE.md` | 7-layer sandbox stack: Proxy Pattern → Dry-Run Harness → SQL Guard → AuthContext → Result Masking → Sentinel → Network Isolation |
| `docs/GRAPH_RAG_SAP_HANA_TECHNIQUES.md` | Graph RAG techniques guide: AllPathsExplorer, TemporalGraphRAG, Meta-Path Library, Graph Embeddings, CDS View Equivalents, BOM Explosion, Community Detection |

---

## Multi-Agent Domain Swarm Architecture — ✅ LIVE (April 12, 2026, Port 8000)

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
| Inter-Agent Message Bus | `app/core/message_bus.py` | ✅ IMPLEMENTED (Phase 13) |
| Negotiation Protocol | `app/core/negotiation_protocol.py` | ✅ IMPLEMENTED (Phase 13) |
| Message Dispatcher + Agent Registry | `app/agents/swarm/message_dispatcher.py` | ✅ IMPLEMENTED (Phase 13) |
| Agent Inbox (`agent_inbox.py`) | `app/core/agent_inbox.py` | ✅ **IMPLEMENTED — Apr 17** | 19.7KB — AgentInbox per-agent inbox + InboxManager swarm lifecycle
| Swarm Autoscaling (Celery workers) | `app/workers/domain_tasks.py` | ✅ **IMPLEMENTED — SWARM AUTOSCALING** |

### Bugs Fixed During Swarm Activation
1. `tables_involved` referenced before initialization → early init added before sentinel evaluation
2. `cross_agent` `list index out of range` → `_mask_results` guard for empty `primary_tables` → guard: `table = self.primary_tables[0] if self.primary_tables else ""`
3. `abs(min(vals), 0.01)` Python syntax error in `synthesis_agent` → `max(abs(min(vals)), 0.01)`

### Live Test Results (localhost:8000)
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
