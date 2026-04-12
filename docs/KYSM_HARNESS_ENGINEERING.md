ï»¿# Know Your SAP Masters (KYSM) - Harness Engineering & Agentic AI
## Session: April 12, 2026 | Status: IN PROGRESS

---

## Top Trends in Agentic AI & Harness Engineering (2026)

1. **Agentic AI Systems & Multi-Agent Frameworks:** Single-prompt AI is being replaced by autonomous, end-to-end agents that can break down tasks, reason, and act independently. Teams of specialized agents collaborate on complex tasks.
2. **The Rise of "Harness Engineering":** Shifting from "Context Engineering" (prompting) to "Harnessing Engineering"Ã¢ÂÂpushing domain knowledge directly into code bases, tools, and sandboxes so agents can self-serve.
3. **Agentic Validation & Self-Healing Loops:** Separating "vibe coding" from reliable engineering requires validation. Agents are now equipped with self-validation loops (tests, screenshots, LogQL) to critique and fix their own outputs.
4. **Autonomous Workflow Orchestration:** AI is moving from a co-pilot to an orchestrator, capable of organizing and executing end-to-end enterprise functions.
5. **On-Device Generative AI:** Generative models are increasingly running directly on user devices or edge nodes for privacy and latency improvements.
6. **AI Production Scaling & Micro-Payments:** The ecosystem is adapting to support massive autonomous API consumption and agent-to-agent commerce.
7. **Hybrid Computing Architectures for Agents:** AI workloads are distributing across specialized hardware, routing tasks dynamically based on complexity and security.
8. **Context & Memory Compounding:** Agents are developing "second brains" for teams, logging mistakes and building rules to compound learning over time.
9. **Visual Agent Builders & No-Code Orchestration:** Platforms are introducing canvas interfaces that combine models, tools, and logic nodes.
10. **Advanced Security and Threat Response:** With autonomous agents, security shifts to hyper-autonomous threat response capable of detecting anomalies and deploying patches instantly.

---

## Application to SAP Masters Architecture Ã¢ÂÂ Implementation Status

### Ã¢ÂÂ 1. Deep Harnessing via Sandboxed Validation (Phase 6 Ã¢ÂÂ VALIDATION HARNESS)
**Status:** IMPLEMENTED Ã¢ÂÂ April 12, 2026

**Files Modified:**
- `backend/app/tools/sql_executor.py` Ã¢ÂÂ `_mock_execution()` now acts as a true validation sandbox
- `backend/app/agents/orchestrator.py` Ã¢ÂÂ Step 5.5 injected into orchestrator

**How It Works:**
- The orchestrator wraps the generated SQL in a `SELECT COUNT(*) FROM (...)` dry-run subquery
- The executor strictly validates syntax: missing `FROM`, `JOIN` without `ON`, trailing commas, duplicate `WHERE`, division by zero
- If the dry-run fails, the exception code (`37000`, `ORA-01476`) is fed to `SelfHealer.heal()`
- Self-healer applies regex-driven corrections (add MANDT, strip JOIN, remove invalid column, simplify ORDER BY, etc.)
- Healed SQL is re-tested in the validation harness before proceeding to execution Ã¢ÂÂ zero human intervention

**Validation Harness Error Codes:**
```
37000      Ã¢ÂÂ Syntax error (missing FROM, JOIN without ON, trailing comma, duplicate WHERE)
ORA-01476  Ã¢ÂÂ Division by zero
ORA-00942  Ã¢ÂÂ Table not found
ORA-01799  Ã¢ÂÂ Column not in subquery
SAP_AUTH   Ã¢ÂÂ Authorization block (inject MANDT filter)
```

---

### Ã¢ÂÂ 2. Automated Memory Compounding (Dynamic Qdrant Vectorization)
**Status:** IMPLEMENTED Ã¢ÂÂ April 12, 2026

**Files Modified:**
- `backend/app/agents/orchestrator.py` Ã¢ÂÂ Step 8b (Memory Compounding loop)

**How It Works:**
- Every time the Validation Harness triggers a self-heal and the corrected query succeeds, the orchestrator automatically:
  1. Builds a new intent string: `"{pattern_name} (Auto-Healed: {heal_reason})"`
  2. Calls `store_manager.load_domain(domain, {}, [{"intent": new_intent, "sql": healed_sql}])`
  3. The Qdrant adapter vectorizes the new healed SQL via `all-MiniLM-L6-v2` and upserts it into the `sql_patterns` collection
- The AI literally expands its own pattern library in real-time Ã¢ÂÂ no manual seeding required
- Next time a similar query is asked, the orchestrator pulls the pre-healed pattern from Qdrant instead of regenerating broken SQL

**Memory Compounding Flow:**
```
Query Ã¢ÂÂ Orchestrator Ã¢ÂÂ Self-Heal Fix Ã¢ÂÂ Qdrant Upsert Ã¢ÂÂ Pattern Boosted
  Ã¢ÂÂ
Next identical query Ã¢ÂÂ Qdrant hit Ã¢ÂÂ Pre-healed SQL returned (no regeneration)
```

---

### Ã¢ÂÂ 3. Proactive Threat Sentinel (Phase 6 Ã¢ÂÂ Security Sentinel)
**Status:** IMPLEMENTED Ã¢ÂÂ April 12, 2026

**New File:** `backend/app/core/security_sentinel.py` (32KB)

**6 Threat Detection Engines:**

| Check | Method | Severity |
|---|---|---|
| `CROSS_MODULE_ESCALATION` | Detects role attempting to access tables outside `ROLE_SCOPE_MAP` via multi-hop graph traversal | MEDIUM Ã¢ÂÂ HIGH |
| `SCHEMA_ENUMERATION` | Flags bulk table discovery probes (>5 new tables per query burst) | LOW Ã¢ÂÂ HIGH |
| `DENIED_TABLE_PROBE` | Tracks repeated attempts to access explicitly denied tables | MEDIUM Ã¢ÂÂ HIGH |
| `DATA_EXFILTRATION` | Flags unusually large result sets (>5,000 rows) | MEDIUM |
| `TEMPORAL_INFERENCE` | Detects restricted historical period queries by HR_ADMIN / AP_CLERK | MEDIUM |
| `ROLE_IMPERSONATION` | Detects sudden cross-domain shift mid-session (3+ domain buckets hit by single role) | MEDIUM |

**Three Operating Modes:**
- `DISABLED` Ã¢ÂÂ Pass through, no monitoring (dev only)
- `AUDIT` Ã¢ÂÂ Monitor and log, never intervene
- `ENFORCING` Ã¢ÂÂ Monitor + dynamically tighten `SAPAuthContext` + fire alerts

**Dynamic Tightening Actions (ENFORCING mode):**
1. Adds out-of-scope tables to `auth_context.denied_tables`
2. Expands `auth_context.masked_fields` with sensitive columns from suspicious tables
3. Escalates session tightness level (0=normal Ã¢ÂÂ 3=lockdown)

**Alert System:**
- `sentinel.register_alert_callback(callback)` Ã¢ÂÂ Register webhooks, SIEM integrations, email
- Default alert: formatted audit log to console with threat type, confidence, evidence, session ID

**Orchestrator Integration:**
- Evaluates BEFORE query executes (pre-execution gate)
- Verdict surfaced in API response under `"sentinel"` key
- Sentinel stats included in response under `"sentinel_stats"` key

---

## Architecture Integration Map

```
Orchestrator (orchestrator.py)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 0: Meta-Path Match (fast path)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 1: Schema RAG (Qdrant)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 1.5: Graph Embedding Search (Node2Vec)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 1.75: QM Semantic Search
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 2: SQL Pattern RAG (Qdrant)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 2b: Temporal Detection
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 2c: Phase 7 Temporal Analysis
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 2d: Phase 8 Negotiation Briefing
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 3: Graph RAG (AllPathsExplorer)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 4: SQL Assembly + AuthContext
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 5: Critique Agent (7-point gate)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 5.5: Ã¢ÂÂ VALIDATION HARNESS (Dry-Run)     Ã¢ÂÂ NEW
  Ã¢ÂÂ       Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Ã¢ÂÂ FAIL Ã¢ÂÂ SelfHealer.heal() Ã¢ÂÂ Re-test
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 6: Execute (SAP HANA Mock)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 7: Result Masking
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Step 8b: Ã¢ÂÂ MEMORY COMPOUNDING (Qdrant Upsert) Ã¢ÂÂ NEW

Security Mesh (security.py)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ SAPAuthContext (role-based row/col masking)
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ denied_tables enforcement
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ masked_fields redaction

Security Sentinel (security_sentinel.py)             Ã¢ÂÂ NEW
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ CROSS_MODULE_ESCALATION
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ SCHEMA_ENUMERATION
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ DENIED_TABLE_PROBE
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ DATA_EXFILTRATION
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ TEMPORAL_INFERENCE
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ ROLE_IMPERSONATION
  Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ Dynamic AuthContext Tightening + Alerts
```

---

## Phase Roadmap Ã¢ÂÂ Updated Status

| Phase | Component | Status |
|---|---|---|
| 1 | 5-Pillar RAG (Role-Graph-Schema-SQL-MetaPath) | Ã¢ÂÂ Working |
| 2 | Self-Healer (SQL critique + fix) | Ã¢ÂÂ Working |
| 3 | Validation Harness (Dry-Run) | Ã¢ÂÂ **NEW Ã¢ÂÂ IMPLEMENTED** |
| 4 | Memory Compounding (Qdrant auto-vectorization) | Ã¢ÂÂ **NEW Ã¢ÂÂ IMPLEMENTED** |
| 5 | Graph Embedding Search (Node2Vec + text, ChromaDB) | Ã¢ÂÂ Working |
| 6 | Self-Healer wired | Ã¢ÂÂ Working |
| 7 | Temporal Analysis Engine | Ã¢ÂÂ Working |
| 8 | QM Semantic Search | Ã¢ÂÂ Working |
| 8 | Negotiation Briefing | Ã¢ÂÂ Working |
| 9 | Frontend Modernization (8-phase + confidence) | Ã¢ÂÂ Working |
| M1-M6 | Memgraph Migration | Ã°ÂÂÂ§ Planned |
| API | FastAPI + startup init | Ã¢ÂÂ Working |
| Ã¢ÂÂ | **Proactive Threat Sentinel** | Ã¢ÂÂ **NEW Ã¢ÂÂ IMPLEMENTED** |
| Ã¢ÂÂ | **BAPI Workflows (Read-to-Write)** | Ã°ÂÂÂ§ Pending |

---

## Next Steps

### Ã°ÂÂÂ§ Pending: BAPI Workflow Harness (Read-to-Write)
Build a new tool harness for SAP BAPIs to move beyond Data Retrieval to autonomous transactions:
- `BAPI_PO_CHANGE` Ã¢ÂÂ Update PO delivery dates
- `BAPI_VENDOR_CREATE` Ã¢ÂÂ Create new vendor master records
- `BAPI_MATERIAL_SAVEDATA` Ã¢ÂÂ Create/update material masters
- `BAPI_SALESORDER_CHANGE` Ã¢ÂÂ Modify sales orders

The orchestrator would ask the user: *"I see you want to update delivery dates. Can I execute `BAPI_PO_CHANGE` to apply this change directly in SAP?"*

### Ã°ÂÂÂ§ Pending: Multi-Agent Domain Swarms
Break the single `run_agent_loop` into a **Planner Agent** + **Domain Agents** (MM, FI, SD, QM) that collaborate on cross-module queries.

### Ã°ÂÂÂ§ Pending: ChromaDB Ã¢ÂÂ Qdrant Cluster Migration
Migrate Schema + Pattern RAG from local ChromaDB to a production Qdrant cluster for horizontal scalability.

---

## ? Implemented: Multi-Agent Domain Swarm Architecture

**Status:** ? **IMPLEMENTED Â' April 12, 2026**

**New Files:**
- ackend/app/agents/swarm/planner_agent.py (19KB) Â' Planner Agent + Complexity Analyzer + routing logic
- ackend/app/agents/swarm/synthesis_agent.py (16KB) Â' Synthesis Agent + merge + deduplication + conflict resolution
- ackend/app/agents/swarm/__init__.py (2KB) Â' un_swarm() entry point
- docs/MULTI_AGENT_SWARM_ARCHITECTURE.md (9KB) Â' full architecture docs

**Architecture:**
`
Query ? PlannerAgent.plan()
          +- SINGLE: DomainAgent ? Response
          +- PARALLEL: DomainAgents [parallel] ? SynthesisAgent ? Response
          +- CROSS_MODULE: CROSS_AGENT + domains ? SynthesisAgent ? Response
          +- NEGOTIATION: SpecialistAgents ? SynthesisAgent ? Response
`

**Key Design:**
- Complexity scoring (0.0Â1.0) across 7 dimensions determines routing strategy
- Domain agents run in parallel threads (ThreadPoolExecutor, max_workers=4)
- Synthesis Agent deduplicates by entity key, ranks by cross-domain relevance, resolves value conflicts
- use_swarm=True/False flag in un_agent_loop gates swarm vs monolith
- Graceful degradation: all-agents-fail ? fallback to monolithic orchestrator


---

## Evening Session Update: Swarm LIVE on Port 8001 (April 12, 2026)

### Bugs Fixed During Activation
1. `tables_involved` referenced before initialization â early init before sentinel evaluation
2. `cross_agent` list index out of range â `_mask_results` guard for empty `primary_tables`  
3. `abs(min(vals), 0.01)` Python syntax error â `max(abs(min(vals)), 0.01)`

### API + Frontend Activation
- Backend API: **http://localhost:8001** (swarm-enabled via `use_swarm=True`)
- Frontend: **http://localhost:8501** (Streamlit, `use_swarm=True` default, swarm badge in header)
- `use_swarm=True` added to `POST /api/v1/chat/master-data` â new fields: `swarm_routing`, `planner_reasoning`, `agent_summary`, `domain_coverage`, `conflicts`, `complexity_score`

### Live Test Results
| Query | Swarm Routing | Agents | Result |
|---|---|---|---|
| vendor open POs > 50k + material | cross_module | pur + cross | â 2 agents |
| vendor payment terms vs customer credit | cross_module | bp + cross | â 2 agents |
| quality inspection results + material | cross_module | mm + qm + cross | â 3 agents |

### Phase 10 Status
**LIVE** â Multi-Agent Domain Swarm activated on ports 8001 + 8501.
