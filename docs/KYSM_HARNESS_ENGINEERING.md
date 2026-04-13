# Know Your SAP Masters (KYSM) - Harness Engineering & Agentic AI
## Session: April 12, 2026 | Status: LIVE (Updated April 13, 2026)

---

## Top Trends in Agentic AI & Harness Engineering (2026)

1. **Agentic AI Systems & Multi-Agent Frameworks:** Single-prompt AI is being replaced by autonomous, end-to-end agents that can break down tasks, reason, and act independently. Teams of specialized agents collaborate on complex tasks.
2. **The Rise of "Harness Engineering":** Shifting from "Context Engineering" (prompting) to "Harnessing Engineering" — pushing domain knowledge directly into code bases, tools, and sandboxes so agents can self-serve.
3. **Agentic Validation & Self-Healing Loops:** Separating "vibe coding" from reliable engineering requires validation. Agents are now equipped with self-validation loops (tests, screenshots, LogQL) to critique and fix their own outputs.
4. **Autonomous Workflow Orchestration:** AI is moving from a co-pilot to an orchestrator, capable of organizing and executing end-to-end enterprise functions.
5. **On-Device Generative AI:** Generative models are increasingly running directly on user devices or edge nodes for privacy and latency improvements.
6. **AI Production Scaling & Micro-Payments:** The ecosystem is adapting to support massive autonomous API consumption and agent-to-agent commerce.
7. **Hybrid Computing Architectures for Agents:** AI workloads are distributing across specialized hardware, routing tasks dynamically based on complexity and security.
8. **Context & Memory Compounding:** Agents are developing "second brains" for teams, logging mistakes and building rules to compound learning over time.
9. **Visual Agent Builders & No-Code Orchestration:** Platforms are introducing canvas interfaces that combine models, tools, and logic nodes.
10. **Advanced Security and Threat Response:** With autonomous agents, security shifts to hyper-autonomous threat response capable of detecting anomalies and deploying patches instantly.

---

## Application to SAP Masters Architecture — Implementation Status

### ✅ 1. Deep Harnessing via Sandboxed Validation (Phase 5.5 — VALIDATION HARNESS)
**Status:** IMPLEMENTED — April 12, 2026

**Files Modified:**
- `backend/app/tools/sql_executor.py` — `_mock_execution()` now acts as a true validation sandbox
- `backend/app/agents/orchestrator.py` — Step 5.5 injected into orchestrator

**How It Works:**
- The orchestrator wraps the generated SQL in a `SELECT COUNT(*) FROM (...)` dry-run subquery
- The executor strictly validates syntax: missing `FROM`, `JOIN` without `ON`, trailing commas, duplicate `WHERE`, division by zero
- If the dry-run fails, the exception code (`37000`, `ORA-01476`) is fed to `SelfHealer.heal()`
- Self-healer applies regex-driven corrections (add MANDT, strip JOIN, remove invalid column, simplify ORDER BY, etc.)
- Healed SQL is re-tested in the validation harness before proceeding to execution — zero human intervention

**Validation Harness Error Codes:**
```
37000      → Syntax error (missing FROM, JOIN without ON, trailing comma, duplicate WHERE)
ORA-01476  → Division by zero
ORA-00942  → Table not found
ORA-01799  → Column not in subquery
SAP_AUTH   → Authorization block (inject MANDT filter)
```

---

### ✅ 2. Automated Memory Compounding (Dynamic Qdrant Vectorization)
**Status:** IMPLEMENTED — April 12, 2026

**Files Modified:**
- `backend/app/agents/orchestrator.py` — Step 8b (Memory Compounding loop)

**How It Works:**
- Every time the Validation Harness triggers a self-heal and the corrected query succeeds, the orchestrator automatically:
  1. Builds a new intent string: `"{pattern_name} (Auto-Healed: {heal_reason})"`
  2. Calls `store_manager.load_domain(domain, {}, [{"intent": new_intent, "sql": healed_sql}])`
  3. The Qdrant adapter vectorizes the new healed SQL via `all-MiniLM-L6-v2` and upserts it into the `sql_patterns` collection
- The AI literally expands its own pattern library in real-time — no manual seeding required
- Next time a similar query is asked, the orchestrator pulls the pre-healed pattern from Qdrant instead of regenerating broken SQL

**Memory Compounding Flow:**
```
Query → Orchestrator → Self-Heal Fix → Qdrant Upsert → Pattern Boosted
  ↓
Next identical query → Qdrant hit → Pre-healed SQL returned (no regeneration)
```

---

### ✅ 3. Proactive Threat Sentinel (Phase 6c — Security Sentinel)
**Status:** IMPLEMENTED — April 12, 2026

**New File:** `backend/app/core/security_sentinel.py` (32KB)

**6 Threat Detection Engines:**

| Check | Method | Severity |
|---|---|---|
| `CROSS_MODULE_ESCALATION` | Detects role attempting to access tables outside `ROLE_SCOPE_MAP` via multi-hop graph traversal | MEDIUM → HIGH |
| `SCHEMA_ENUMERATION` | Flags bulk table discovery probes (>5 new tables per query burst) | LOW → HIGH |
| `DENIED_TABLE_PROBE` | Tracks repeated attempts to access explicitly denied tables | MEDIUM → HIGH |
| `DATA_EXFILTRATION` | Flags unusually large result sets (>5,000 rows) | MEDIUM |
| `TEMPORAL_INFERENCE` | Detects restricted historical period queries by HR_ADMIN / AP_CLERK | MEDIUM |
| `ROLE_IMPERSONATION` | Detects sudden cross-domain shift mid-session (3+ domain buckets hit by single role) | MEDIUM |

**Three Operating Modes:**
- `DISABLED` — Pass through, no monitoring (dev only)
- `AUDIT` — Monitor and log, never intervene
- `ENFORCING` — Monitor + dynamically tighten `SAPAuthContext` + fire alerts

**Dynamic Tightening Actions (ENFORCING mode):**
1. Adds out-of-scope tables to `auth_context.denied_tables`
2. Expands `auth_context.masked_fields` with sensitive columns from suspicious tables
3. Escalates session tightness level (0=normal → 3=lockdown)

**Alert System:**
- `sentinel.register_alert_callback(callback)` — Register webhooks, SIEM integrations, email
- Default alert: formatted audit log to console with threat type, confidence, evidence, session ID

**Orchestrator Integration:**
- Evaluates BEFORE query executes (pre-execution gate)
- Verdict surfaced in API response under `"sentinel"` key
- Sentinel stats included in response under `"sentinel_stats"` key

---

## Architecture Integration Map

```
Orchestrator (orchestrator.py)
  ├── Step 0: Meta-Path Match (fast path)
  ├── Step 1: Schema RAG (Qdrant) ● ACTIVE — 4 collections seeded
  ├── Step 1.5: Graph Embedding Search (Node2Vec)
  ├── Step 1.75: QM Semantic Search
  ├── Step 2: SQL Pattern RAG (Qdrant) ● ACTIVE — 4 collections seeded
  ├── Step 2b: Temporal Detection
  ├── Step 2c: Phase 7 Temporal Analysis
  ├── Step 2d: Phase 8 Negotiation Briefing
  ├── Step 3: Graph RAG (AllPathsExplorer)
  ├── Step 4: SQL Assembly + AuthContext
  ├── Step 5: Critique Agent (7-point gate)
  ├── Step 5.5: ✅ VALIDATION HARNESS (Dry-Run)     ← NEW
  │       └── ❌ FAIL → SelfHealer.heal() → Re-test
  ├── Step 6: Execute (SAP HANA Mock)
  ├── Step 7: Result Masking
  └── Step 8b: ✅ MEMORY COMPOUNDING (Qdrant Upsert) ← NEW

Security Mesh (security.py)
  ├── SAPAuthContext (role-based row/col masking)
  ├── denied_tables enforcement
  └── masked_fields redaction

Security Sentinel (security_sentinel.py)             ← NEW
  ├── CROSS_MODULE_ESCALATION
  ├── SCHEMA_ENUMERATION
  ├── DENIED_TABLE_PROBE
  ├── DATA_EXFILTRATION
  ├── TEMPORAL_INFERENCE
  ├── ROLE_IMPERSONATION
  └── Dynamic AuthContext Tightening + Alerts

Infrastructure
  ├── Qdrant (localhost:6333) ● 4 collections — ACTIVE (docker: sapmasters_qdrant — HEALTHY)
  │   ├── sap_schema            — Schema RAG
  │   ├── sql_patterns          — SQL Pattern RAG
  │   ├── graph_node_embeddings — Node2Vec structural
  │   └── graph_table_context   — Text context
  ├── Memgraph (localhost:7687) ● 114 nodes / 47 edges — ACTIVE (docker: sapmasters_memgraph — HEALTHY)
  │   └── Graph RAG via bolt_load.py (neo4j driver)
  ├── ChromaDB (./chroma_db/)   ← Legacy — Schema + Pattern RAG migrated to Qdrant
  ├── RabbitMQ (localhost:5672) ● ACTIVE (docker: sapmasters_rabbitmq — HEALTHY)
  └── Redis (localhost:6379)    ● ACTIVE (docker: sapmasters_redis — HEALTHY)
```

---

## Phase Roadmap — Updated Status

| Phase | Component | Status |
|---|---|---|
| 0 | Meta-Path Match (14 fast-path JOIN templates) | ✅ Working |
| 1 | Schema RAG (Qdrant + ChromaDB dual-backend) | ✅ Working |
| 1.5 | Graph Embedding Search (Node2Vec + text, ChromaDB) | ✅ Working |
| 1.75 | QM Semantic Search | ✅ Working |
| 2 | SQL Pattern RAG (Qdrant + ChromaDB, 68+ patterns) | ✅ Working |
| 2b | Temporal Detection | ✅ Working |
| 2c | Phase 7 Temporal Analysis Engine | ✅ Working |
| 2d | Phase 8 Negotiation Briefing | ✅ Working |
| 3 | Graph RAG (AllPathsExplorer + TemporalGraphRAG) | ✅ Working |
| 4 | SQL Assembly + MANDT + AuthContext + Temporal filters | ✅ Working |
| 5 | Critique Gate (7-point SQL validation) | ✅ Working |
| **5.5** | **Validation Harness (Dry-Run SELECT COUNT\* — IMPLEMENTED)** | ✅ **NEW** |
| 6 | Self-Healer (10 error codes → 6 heal strategies) | ✅ Working |
| **6b** | **Memory Compounding (Qdrant auto-vectorization — IMPLEMENTED)** | ✅ **NEW** |
| **6c** | **Proactive Threat Sentinel (6 engines — IMPLEMENTED)** | ✅ **NEW** |
| 7 | Execution (SAP HANA mock — `hdbcli` swap pending) | ✅ Working |
| 8 | Result Masking (Role-based column redaction) | ✅ Working |
| 9 | Frontend Modernization (8-phase + confidence gauge + dark card) | ✅ Working |
| **10** | **Multi-Agent Domain Swarm (LIVE on port 8001 — IMPLEMENTED)** | ✅ **NEW → LIVE** |
| M1 | Memgraph 2.12.0 + Lab — Docker Compose | ✅ Complete |
| M2 | Memgraph Cypher port (replace NetworkX with Memgraph queries) | 🚧 Pending |
| M3 | `use_memgraph` flag in main.py | 🚧 Pending |
| M4 | Qdrant cluster migration (Schema + Pattern RAG) | 🚧 Pending |
| M5 | Celery async worker pool | 🚧 Pending |
| M6 | Load testing + production tuning | 🚧 Pending |
| — | **BAPI Workflow Harness (Read-to-Write)** | 🚧 Pending |

---

## Next Steps

### 🚧 Pending: BAPI Workflow Harness (Read-to-Write)
Build a new tool harness for SAP BAPIs to move beyond data retrieval to autonomous transactions:
- `BAPI_PO_CHANGE` — Update PO delivery dates
- `BAPI_VENDOR_CREATE` — Create new vendor master records
- `BAPI_MATERIAL_SAVEDATA` — Create/update material masters
- `BAPI_SALESORDER_CHANGE` — Modify sales orders

The orchestrator would ask the user: *"I see you want to update delivery dates. Can I execute `BAPI_PO_CHANGE` to apply this change directly in SAP?"*

### 🚧 Pending: Multi-Agent Domain Swarms — Inter-Agent Message Bus
Break domain agents out of star-topology via a shared message bus for direct agent-to-agent negotiation.

### 🚧 Pending: ChromaDB → Qdrant Cluster Migration
Migrate Schema + Pattern RAG from local ChromaDB to a production Qdrant cluster for horizontal scalability. *(Note: Qdrant is already ACTIVE and seeded with 4 collections — ChromaDB is now legacy.)*

---

## ✅ Implemented: Multi-Agent Domain Swarm Architecture

**Status:** ✅ **LIVE — April 12, 2026** (Port 8001 backend + Port 8501 frontend)

**New Files:**
- `backend/app/agents/swarm/planner_agent.py` (19KB) — Planner Agent + Complexity Analyzer + routing logic
- `backend/app/agents/swarm/synthesis_agent.py` (16KB) — Synthesis Agent + merge + deduplication + conflict resolution
- `backend/app/agents/swarm/__init__.py` (2KB) — `run_swarm()` entry point
- `docs/MULTI_AGENT_SWARM_ARCHITECTURE.md` (9KB) — full architecture docs

**Architecture:**
```
Query → PlannerAgent.plan()
          ├── SINGLE: DomainAgent → Response
          ├── PARALLEL: DomainAgents [parallel] → SynthesisAgent → Response
          ├── CROSS_MODULE: CROSS_AGENT + domains → SynthesisAgent → Response
          └── NEGOTIATION: SpecialistAgents → SynthesisAgent → Response
```

**Key Design:**
- Complexity scoring (0.0–1.0) across 7 dimensions determines routing strategy
- Domain agents run in parallel threads (ThreadPoolExecutor, max_workers=4)
- Synthesis Agent deduplicates by entity key, ranks by cross-domain relevance, resolves value conflicts
- `use_swarm=True/False` flag in `run_agent_loop` gates swarm vs monolith
- Graceful degradation: all-agents-fail → fallback to monolithic orchestrator

---

## Evening Session Update: Swarm LIVE on Port 8001 (April 12, 2026)

### Bugs Fixed During Activation
1. `tables_involved` referenced before initialization → early init added before sentinel evaluation
2. `cross_agent` `list index out of range` → `_mask_results` guard for empty `primary_tables` → fixed: `table = self.primary_tables[0] if self.primary_tables else ""`
3. `abs(min(vals), 0.01)` Python syntax error in `synthesis_agent` → fixed to `max(abs(min(vals)), 0.01)`

### API + Frontend Activation
- Backend API: **http://localhost:8001** (swarm-enabled via `use_swarm=True`)
- Frontend: **http://localhost:8501** (Streamlit, `use_swarm=True` default, swarm badge in header)
- `use_swarm=True` added to `POST /api/v1/chat/master-data` — new fields: `swarm_routing`, `planner_reasoning`, `agent_summary`, `domain_coverage`, `conflicts`, `complexity_score`

### Live Test Results
| Query | Swarm Routing | Agents | Result |
|---|---|---|---|
| vendor open POs > 50k + material | `cross_module` | pur + cross | ✅ 2 agents |
| vendor payment terms vs customer credit | `cross_module` | bp + cross | ✅ 2 agents |
| quality inspection results + material | `cross_module` | mm + qm + cross | ✅ 3 agents |

### Phase 10 Status
**LIVE** — Multi-Agent Domain Swarm activated on ports 8001 + 8501.
