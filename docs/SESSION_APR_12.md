# Session: April 12, 2026 â Harness Engineering: Validation Harness, Memory Compounding & Threat Sentinel

**Context:** Applied 3 bleeding-edge Harness Engineering principles from John Kim's 5 Pillars of Agentic Engineering to the SAP Masters architecture. Full implementations wired into the orchestrator.

---

## What was built today:

### 1. Token Budget Tracking (Cost Governance)
- **Goal:** Provide observability into LLM token consumption and estimated costs per orchestrator call.
- **Component:** `app/core/token_tracker.py`
- **Implementation:**
  - `TokenTracker` class created to calculate `prompt_tokens`, `completion_tokens`, and `estimated_cost_usd` based on dynamic model pricing (GPT-4, Claude 3 variants).
  - Integrated directly into the main orchestrator loop (`app/agents/orchestrator.py`).
  - Added mock token accounting to both standard graph routing and supervisor pathways.
  - Exposed via the `ChatResponse` API payload so the frontend can retrieve the summary.
- **Status:** Complete â

### 2. Eval Alerting (UI Integration)
- **Goal:** Proactive quality monitoring through frontend alerts when backend benchmark/eval metrics degrade.
- **Component:** `app/api/endpoints/eval.py` + `frontend/app.py`
- **Implementation:**
  - Created a new `/eval/alerts` endpoint pointing to the existing `EvalAlertMonitor`.
  - Registered the new router in `app/api/api.py` (under `/api/v1/eval/alerts`).
  - Injected an alert-polling block into the Streamlit `app.py`. If active alerts exist (e.g., `success_rate < 0.70`, latency spike), Streamlit flashes a high-visibility warning banner above the chat interface.
- **Status:** Complete â

### 3. Qdrant Graph Embedding Search Bugfix
- **Issue:** The Graph Enhanced Discovery tool (Pillar 5Â½) was silently failing with `list indices must be integers or slices, not str`.
- **Root Cause:** A remnant from the ChromaDB â Qdrant migration (Phase M6). The Qdrant `search()` returns a list of `ScoredPoint` objects, but the graph search algorithm was still trying to parse it as a ChromaDB dictionary (`text_results["metadatas"][0]`).
- **Fix:** Rewrote "Step 3" and "Step 4" of `search_graph_tables()` in `app/core/graph_embedding_store.py` to correctly extract `.payload` and `.score` attributes natively from the Qdrant object format.
- **Status:** Complete â

---

## HARNESS ENGINEERING IMPLEMENTATIONS (April 12, Evening)

### â 4. Phase 5.5: Deep Harnessing via Sandboxed Validation
**Files:** `backend/app/tools/sql_executor.py`, `backend/app/agents/orchestrator.py`

**What changed:**
- `_mock_execution()` now strictly validates SQL syntax before returning mock data. It parses for: missing `FROM` clauses, `JOIN`s without `ON`, trailing commas, duplicate `WHERE` keywords, division by zero, and raises native SQL exception codes (`37000`, `ORA-01476`).
- Orchestrator injects **Step 5.5: DRY-RUN VALIDATION HARNESS** between the critique gate and final execution.
- Generated SQL is wrapped in `SELECT COUNT(*) FROM (...) AS dry_run_sub` and passed to `sql_execute(dry_run=True)`.
- If the dry-run fails: error code â `SelfHealer.heal()` â autonomous correction â re-test â proceed to execution.
- Zero human intervention required for syntax recovery.

**Validation Harness Error Codes:**
```
37000     â Syntax error (missing FROM, JOIN without ON, trailing comma, duplicate WHERE)
ORA-01476 â Division by zero
ORA-00942 â Table not found
ORA-01799 â Column not in subquery
SAP_AUTH  â Authorization block
```

### â 5. Phase 6b: Automated Memory Compounding (Qdrant Vectorization)
**File:** `backend/app/agents/orchestrator.py` â Step 8b

**What changed:**
- Orchestrator now monitors `heal_info` after execution. If a self-heal was applied AND the query succeeded:
  1. Builds a new intent string: `"{pattern_name} (Auto-Healed: {heal_reason})"`
  2. Calls `store_manager.load_domain(domain, {}, [{"intent": new_intent, "sql": healed_sql}])`
  3. Qdrant adapter vectorizes the healed SQL via `all-MiniLM-L6-v2` and upserts it into the `sql_patterns` collection.
- The AI literally expands its own pattern library in real-time â every healed query becomes a future fast-path hit.
- **Memory Compounding Flow:** Query â Self-Heal Fix â Qdrant Upsert â Pattern Boosted â Next identical query hits pre-healed SQL.

### â 6. Phase 6c: Proactive Threat Sentinel
**New File:** `backend/app/core/security_sentinel.py` (32KB)

**What was built:**
- 6 real-time behavioral anomaly detection engines running as a pre-execution gate:
  1. `CROSS_MODULE_ESCALATION` â Role accessing out-of-scope tables via multi-hop graph traversal
  2. `SCHEMA_ENUMERATION` â Bulk table discovery probes (>5 new tables per query burst)
  3. `DENIED_TABLE_PROBE` â Repeated attempts to access explicitly blocked tables
  4. `DATA_EXFILTRATION` â Unusually large result sets (>5,000 rows)
  5. `TEMPORAL_INFERENCE` â HR_ADMIN / AP_CLERK querying restricted historical periods
  6. `ROLE_IMPERSONATION` â Sudden cross-domain shift mid-session (3+ domain buckets hit)
- Three operating modes: `DISABLED` | `AUDIT` | `ENFORCING`
- **Dynamic Tightening (ENFORCING mode):** Adds out-of-scope tables to `auth_context.denied_tables`, expands `masked_fields`, escalates session tightness level (0â3).
- **Alert system:** Register webhooks/SIEM via `sentinel.register_alert_callback()`. Default: formatted console audit log with threat type, confidence, evidence, session ID.
- **Orchestrator Integration:** Pre-execution gate + verdict surfaced in API response under `"sentinel"` key + sentinel stats in `"sentinel_stats"`.

---

## Architecture Integration Map (April 12 Update)

```
Orchestrator (orchestrator.py)
  âââ Step 0: Meta-Path Match (fast path)
  âââ Step 1: Schema RAG (Qdrant)
  âââ Step 1.5: Graph Embedding Search (Node2Vec)
  âââ Step 1.75: QM Semantic Search
  âââ Step 2: SQL Pattern RAG (Qdrant)
  âââ Step 2b: Temporal Detection
  âââ Step 2c: Phase 7 Temporal Analysis
  âââ Step 2d: Phase 8 Negotiation Briefing
  âââ Step 3: Graph RAG (AllPathsExplorer)
  âââ Step 4: SQL Assembly + AuthContext
  âââ Step 5: Critique Agent (7-point gate)
  âââ Step 5.5: â VALIDATION HARNESS (Dry-Run)     â NEW
  â       âââ â FAIL â SelfHealer.heal() â Re-test
  âââ Step 6: Execute (SAP HANA Mock)
  âââ Step 7: Result Masking
  âââ Step 8b: â MEMORY COMPOUNDING (Qdrant Upsert) â NEW

Security Mesh (security.py)
  âââ SAPAuthContext (role-based row/col masking)
  âââ denied_tables enforcement
  âââ masked_fields redaction

Security Sentinel (security_sentinel.py)             â NEW
  âââ CROSS_MODULE_ESCALATION
  âââ SCHEMA_ENUMERATION
  âââ DENIED_TABLE_PROBE
  âââ DATA_EXFILTRATION
  âââ TEMPORAL_INFERENCE
  âââ ROLE_IMPERSONATION
  âââ Dynamic AuthContext Tightening + Alerts
```

---

## Current Roadmap Status

| Phase | Component | Status |
|---|---|---|
| 1-5 | 5-Pillar RAG | â Working |
| 5.5 | Validation Harness (Dry-Run) | â **NEW â IMPLEMENTED** |
| 6 | Self-Healer | â Working |
| 6b | Memory Compounding (Qdrant auto-vectorization) | â **NEW â IMPLEMENTED** |
| 6c | Proactive Threat Sentinel | â **NEW â IMPLEMENTED** |
| 7 | Temporal Analysis Engine | â Working |
| 8 | QM Semantic Search | â Working |
| 8 | Negotiation Briefing | â Working |
| 9 | Frontend Modernization | â Working |
| M1-M6 | Memgraph Migration | ð§ Planned |
| API | FastAPI + startup init | â Working |

**Remaining P0:** Real SAP HANA Connection (hdbcli)
**Remaining P1:** BAPI Workflow Harness (Read-to-Write)
**Remaining P2:** Multi-Agent Domain Swarms

**Next Steps:** Implement BAPI Workflow Harness or begin hdbcli integration.

### 7. Multi-Agent Domain Swarm Architecture
**New Files:** ackend/app/agents/swarm/planner_agent.py, ackend/app/agents/swarm/synthesis_agent.py, ackend/app/agents/swarm/__init__.py

**What was built:**
- **Planner Agent**  intelligent routing layer replacing the monolithic orchestrator entry point. Uses 7-dimension complexity scoring to decide: SINGLE | PARALLEL | CROSS_MODULE | NEGOTIATION | ESCALATE paths.
- **Synthesis Agent**  merges results from parallel domain agents. Deduplicates by entity key (LIFNR/MATNR/EBELN). Ranks by query relevance + cross-domain bonus. Detects and resolves value conflicts across agents.
- **Domain Agents** (existing domain_agents.py) now participate in swarm execution via ThreadPoolExecutor parallelism.
- **Orchestrator integration:** use_swarm=True/False flag in un_agent_loop gates swarm vs monolith. Swarm results include swarm_routing, planner_reasoning, gent_summary, domain_coverage, conflicts, execution_time_ms.
- **Documentation:** docs/MULTI_AGENT_SWARM_ARCHITECTURE.md  full architecture diagrams, flows, and design decisions.

**Routing Decision Tree:**
- SINGLE (confidence = 0.85 from one agent)
- PARALLEL (2+ agents, no JOIN needed)
- CROSS_MODULE (cross-module JOIN detected)
- NEGOTIATION (negotiation/QM keywords detected)
- ESCALATE (complexity = 0.6 ? fallback to monolith)

---

## Evening Session Update: Live API Activation + Bug Fixes

### Bugs Fixed During Swarm Activation
1. `tables_involved` referenced before initialization in sentinel gate — early init added before sentinel evaluation
2. `cross_agent` crashing with `list index out of range` — `_mask_results` guard added for empty `primary_tables`
3. `abs(min(vals), 0.01)` Python syntax error in `synthesis_agent` → `max(abs(min(vals)), 0.01)`

### Files Modified
- `backend/app/agents/orchestrator.py` — early `tables_involved` init, `use_swarm` gate, `swarm_routing` in result dict
- `backend/app/agents/domain_agents.py` — `_mask_results` empty guard for `cross_agent`
- `backend/app/agents/swarm/synthesis_agent.py` — `abs()` fix, helper methods added
- `backend/app/agents/swarm/planner_agent.py` — helper methods, flattened synthesis fields
- `backend/app/api/endpoints/chat.py` — `use_swarm` field + all swarm response fields
- `frontend/app.py` — `API_BASE=localhost:8001`, `use_swarm=True`, swarm badge + Swarm Execution Summary panel

### Live Test Results (localhost:8001 — `use_swarm=True`)
| Query | Swarm Routing | Agents | Domains Hit | Result |
|---|---|---|---|---|
| vendor open POs > 50k + material | cross_module | pur_agent + cross_agent | 2 | Synthesized from 2 agents |
| vendor payment terms vs customer credit | cross_module | bp_agent + cross_agent | 2 | Synthesized from 2 agents |
| quality inspection results + material | cross_module | mm_agent + qm_agent + cross_agent | 3 | **3 agents in parallel** |

### Frontend Activated
- Streamlit running at **http://localhost:8501**
- Backend API at **http://localhost:8001** (swarm-enabled)
- `use_swarm=True` default in frontend payload
- SWARM badge + Swarm Execution Summary expander visible in UI

### Phase 10 Status
Phase 10 (Multi-Agent Domain Swarm) is **LIVE** — backend API (port 8001) and frontend (port 8501) running with swarm as default.
