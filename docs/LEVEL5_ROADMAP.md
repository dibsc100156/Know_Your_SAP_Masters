# KYSM Level-5 Roadmap — Consolidated Implementation Status
**Last Updated:** April 19, 2026 | Project: Know Your SAP Masters (SAP Masters)

---

## Executive Summary

17-phase autonomous enterprise SAP assistant. Each phase is independently deployable
and wires into the orchestrator via clearly defined entry/exit contracts.

**Tonight's commits (April 19):**
- `c4d087e` — Phase 14 Voting Executor (3-path parallel, consensus boosting)
- `acb50ea` — Phase 15 CIBA Approval Flow (block/tighten → async approve/deny)
- `9ef51de` — Phase 16 Self-Healing Patterns DB (Qdrant-stored healed SQL → PATH_D fast-path)

**Infrastructure (April 19):**
- Qdrant ✅ — 5 collections (sap_schema, sql_patterns, graph_node_embeddings, graph_table_context, qm_semantic_notifications)
- Memgraph ✅ — bolt://localhost:7687, 114 nodes / 47 edges
- Redis ✅ — localhost:6379/0 (CIBA store + Celery broker + harness runs)
- RabbitMQ ✅ — amqp://sapmasters:sapmasters123@localhost:5672//
- Celery Worker ✅ — 4 threads, queues: agent + priority

---

## 5-Pillar RAG Architecture

| Pillar | Name | Component | Status |
|--------|------|-----------|--------|
| 1 | Role-Aware Security | `security.py` — SAPAuthContext, AuthContext masking, denied_tables | ✅ Working |
| 2 | Agentic Orchestrator | `orchestrator.py` — `run_agent_loop()`, 8-step execution flow | ✅ Working |
| 3 | Schema RAG | Qdrant semantic search over DDIC metadata | ✅ Working |
| 4 | SQL Pattern RAG | `sql_pattern_lookup()`, 68+ patterns across 18 domains | ✅ Working |
| 5 | Graph RAG | NetworkX FK graph, `AllPathsExplorer`, `TemporalGraphRAG`, Meta-Path Library | ✅ Working |
| 5½ | Graph Embedding Search | Node2Vec + text hybrid in Qdrant | ✅ Working |

---

## 17-Phase Execution Roadmap

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
| 5.5 | Validation Harness | `SELECT COUNT(*)` dry-run → syntax validation → autonomous fix | ✅ Apr 12 |
| 6 | Self-Healing | Rule-based SQL correction (10 error codes → 6 heal strategies) | ✅ Working |
| **6b** | **Memory Compounding** | Auto-vectorize healed SQL back into Qdrant pattern store | ✅ Apr 12 |
| **6c** | **Proactive Threat Sentinel** | 6 threat engines + dynamic AuthContext tightening | ✅ Apr 12 |
| **14** | **Voting Executor** | 4-path parallel SQL generation + consensus (Phase 16 — Apr 19) | ✅ **LIVE** |
| **15** | **CIBA Approval Flow** | Block verdict → async approve/deny via Redis-backed store (Apr 19) | ✅ **LIVE** |
| **17** | **Semantic Answer Validation** | Qdrant cross-check + 4-component scoring (semantic_sim, row_plausibility, intent_match, table_match) | ✅ **LIVE — Apr 19** |
| 7 | Execution | SAP HANA mock executor — swap `hdbcli` for real connection to close P0 | ✅ Working (mock) |
| 8 | Result Masking | Role-based column redaction (Pillar 1) | ✅ Working |
| 9 | Frontend Modernization | 8-phase + confidence gauge + signal table + dark card | ✅ Apr 5 |
| **10** | **Multi-Agent Domain Swarm** | Planner + 7 Domain Agents + Synthesis Agent — ThreadPoolExecutor | ✅ **LIVE — Apr 12** |
| 11 | Meta-Harness Loop | `meta_harness_loop.py` — collect→analyze→YAML→approve→patch | ✅ WIRED |
| 12 | Quality Evaluator | `QualityEvaluator` — correctness_score + trajectory_adherence from Redis traces | ✅ WIRED |
| 13 | Inter-Agent Message Bus | Redis pub/sub + streams, 6 message types | ✅ IMPLEMENTED |
| 13b | Negotiation Protocol | 4-phase ASSERTING→CHALLENGING→NEGOTIATING→COMMITTED | ✅ IMPLEMENTED |

---

## Phase 14 — Voting Executor ✅ LIVE (April 19)

**Commit:** `c4d087e` | **Trigger:** confidence < 0.70 OR domain in {finance, tax, treasury, compliance}

### 4 Voting Paths

| Path | Strategy | Primary Pillar | Speed |
|------|----------|----------------|-------|
| **PATH_A** | Graph RAG — `find_path()` + `search_graph_tables()` | Pillar 5 | ~20ms |
| **PATH_B** | SQL Pattern RAG — `SQLRAGStore.search()` + `critique()` | Pillar 4 | ~15ms |
| **PATH_C** | Meta-Path Fast — pre-assembled JOIN templates | Pillar 0 | ~5ms |
| **PATH_D** | Healed Pattern — Qdrant `find_similar_healed()` | Phase 16 | ~10ms |

### Voting Logic
- **Table-set majority vote:** ≥2 paths agree on table set → consensus
- **SQL Jaccard similarity:** ≥0.75 token overlap → merge to consensus_sql
- **Disagreement:** escalate with disagreement report
- **Confidence boost:** 0.406 → 0.506 (measured on `vendor master for company code 1000`)

### Tool
Registered as `voting_sql_generate` in TOOL_REGISTRY. Fires at Step 6 of orchestrator.

---

## Phase 15 — CIBA Approval Flow ✅ LIVE (April 19)

**Commit:** `acb50ea`

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `ciba_approval_store.py` | 391 | Redis-backed store, PENDING/APPROVED/DENIED states, auto-approve/deny hash |
| `ciba.py` | 263 | FastAPI endpoints — `/pending`, `/approve`, `/deny`, `/check`, `/stats` |
| `orchestrator.py` | +61 | Block/tighten branching patch |

### Flow
```
Sentinel verdict: "block"
  → check is_query_approved(session, query)? → auto-proceed
  → check is_query_denied(session, query)?    → hard rejection (30min)
  → else: create_approval_request() → return ciba_pending + request_id
        ↓
    Supervisor approves via POST /api/v1/ciba/approve/{id}
        ↓
    Query auto-approved for 1hr; re-submit → passes

Sentinel verdict: "tighten"
  → apply_tightening_to_auth_context() → continue execution
```

### CIBA Endpoints
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/ciba/pending?session_id=X` | GET | List pending approvals for session |
| `/api/v1/ciba/pending/{request_id}` | GET | Get specific request (time remaining) |
| `/api/v1/ciba/approve/{request_id}?approver_id=X` | POST | Approve → query auto-approved 1hr |
| `/api/v1/ciba/deny/{request_id}?denier_id=X` | POST | Deny → query hard-rejected 30min |
| `/api/v1/ciba/check/{session_id}?query=X` | GET | Pre-check: approved/denied? |
| `/api/v1/ciba/stats` | GET | Store stats |

### Verified (Redis backend)
- `create_approval_request()` → request created ✅
- `approve()` → `is_query_approved()` returns True ✅
- `deny()` → `is_query_denied()` returns True ✅
- Stats: pending/approved/denied counts ✅

---

## Phase 16 — Self-Healing Patterns DB ✅ LIVE (April 19)

**Commit:** `9ef51de`

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `healed_pattern_store.py` | 266 | Qdrant store: `store_healed_pattern()`, `find_similar_healed()`, `increment_reuse()` |
| `voting_executor.py` | +95 | PATH_D — 4th vote path checking Qdrant before orchestrator heal loop |
| `orchestrator.py` | +35 | Store call on critique-heal success + validation-heal success |

### Store Call Sites (Orchestrator)
1. **Critique self-heal:** after `re_critique["passed"]` — stores successful SQL correction
2. **Validation self-heal:** after `revalidate.status == SUCCESS` — stores validation-error fix

### PATH_D Fast Path
```
Voting executor fires → PATH_D checks Qdrant
  → match found (score ≥ 0.70)? → apply healed SQL directly, skip self-heal loop
  → no match? → abstain, let orchestrator handle normally
```

### Verified (Qdrant)
```
Stored pattern ID: db16573f2d7d437184218ca8b2a11983
Find similar:      1 match (score=1.0, heal_code=MANDT_MISSING)
sql_patterns:      27 → 28 points ✅
Embedding model:   all-MiniLM-L6-v2 (384-dim, cosine, normalized)
```

### Payload Schema (Qdrant `sql_patterns`)
```python
{
    "intent": str,           # natural-language query
    "sql": str,              # healed SQL
    "sql_template": str,
    "domain": str,
    "tables_used": List[str],
    "tags": List[str],       # [heal_code, error_type, "healed", "phase16", ...]
    "heal_code": str,        # e.g. "MANDT_MISSING"
    "error_type": str,
    "healed_at": float,
    "heal_reason": str,
    "times_reused": int,
    "query_example": str,
    "original_sql": str,
}
```

---

## Multi-Agent Domain Swarm Architecture — ✅ LIVE (April 12, 2026)

| Component | File | Status |
|---|---|---|
| Domain Agents (7 specialists) | `domain_agents.py` | ✅ Working |
| Planner Agent + Complexity Analyzer | `swarm/planner_agent.py` (19KB) | ✅ **LIVE** |
| Synthesis Agent (merge + rank + conflicts) | `swarm/synthesis_agent.py` (16KB) | ✅ **LIVE** |
| Swarm entry point | `swarm/__init__.py` (2KB) | ✅ **LIVE** |
| Inter-Agent Message Bus | `app/core/message_bus.py` | ✅ Phase 13 |
| Negotiation Protocol | `app/core/negotiation_protocol.py` | ✅ Phase 13b |
| Message Dispatcher + Agent Registry | `app/agents/swarm/message_dispatcher.py` | ✅ Phase 13 |
| Agent Inbox | `app/core/agent_inbox.py` (19.7KB) | ✅ Apr 17 |

### Live Test Results (April 12)
| Query | Swarm Routing | Agents | Result |
|---|---|---|---|
| vendor open POs > 50k + material | `cross_module` | pur + cross | ✅ 2 records |
| vendor payment terms vs customer credit | `cross_module` | bp + cross | ✅ 2 records |
| quality inspection results + material | `cross_module` | mm + qm + cross | ✅ 2 records |

---

## Memgraph Migration (M1–M6)

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| M1 | Memgraph 2.12.0 + Lab — Docker Compose | ✅ Complete | |
| M2 | Native Cypher paths (`[*..5]` variable-length) | ✅ Complete | Memgraph 2.x compatible |
| M3 | `use_memgraph` flag + auto-sync at startup | ✅ Complete | |
| M4 | Celery async worker pool | ✅ Complete | 4 threads, queues: agent + priority |
| M5 | Redis Dialog State | ✅ Complete | |
| M6 | Qdrant cluster migration | ✅ Complete | 5 collections active |
| M7 | Load testing + production tuning | 🚧 Pending | p95 773ms; needs conc=10 sign-off |
| M8 | Real SAP HANA connection (`hdbcli`) | 🚧 Pending | Env: HANA_HOST, HANA_PORT, HANA_USER, HANA_PASSWORD |
| M9 | Kubernetes HPA | ✅ Complete | Max 20 replicas |
| M10 | LeanIX agent governance | ✅ Complete | |
| M11 | Multi-tenant isolation | ✅ Complete | `TENANT_ID` env wired |

> **Note:** Memgraph 2.x Cypher limitations — `LENGTH(path)`, `relationships(path)`, `shortestPath()`, path-list comprehensions NOT implemented.

---

## Harness Engineering — Implemented Principles

| Phase | Principle | File | Status |
|-------|-----------|------|--------|
| 5.5 | Sandboxed Validation | `sql_executor.py`, `orchestrator.py` | ✅ Apr 12 |
| 6b | Memory Compounding | `orchestrator.py` (Step 8b) | ✅ Apr 12 |
| 6c | Proactive Threat Sentinel | `security_sentinel.py` (32KB) | ✅ Apr 12 |
| 11 | Meta-Harness Loop | `meta_harness_loop.py` + `failure_trigger.py` | ✅ WIRED |
| 12 | Quality Evaluator | `quality_evaluator.py` | ✅ WIRED |
| 12b | Trajectory Log | `HarnessRun.trajectory_log[]` | ✅ ANALYZED |
| 14 | Voting Executor | `voting_executor.py` | ✅ Apr 19 |
| 15 | CIBA Approval | `ciba_approval_store.py` + `ciba.py` | ✅ Apr 19 |
| 16 | Self-Healing Patterns DB | `healed_pattern_store.py` | ✅ Apr 19 |
| 17 | Semantic Answer Validation | `semantic_answer_validator.py` | ✅ Apr 19 |

---

## Priority Build Order

| # | Priority | Item | Phase | Status |
|---|----------|------|-------|--------|
| 1 | 🔴 P0 | Real SAP HANA connection (`hdbcli`) | M8 | 🚧 Pending |
| 2 | 🔴 P0 | M7 Load Testing sign-off (p95 ≤ 300ms @ conc=10) | M7 | 🚧 Pending |
| 3 | 🟡 P1 | Agent Inbox + Push Notifications | Phase 17 | 📋 Next |
| 4 | 🟡 P1 | BAPI Workflow Harness (Read-to-Write) | P1 | 📋 Planned |
| 5 | 🟡 P1 | Long-Running Agent Infrastructure (6hr runs) | P1 | 📋 Planned |
| 6 | 🟢 P2 | Ralph Wiggum PR Review Loop | P2 | 📋 Planned |
| 7 | 🟢 P2 | Doc-Gardening Agent (stale doc scanner) | P2 | 📋 Planned |
| 8 | 🟢 P2 | Observability Query Interface (LogQL/PromQL) | P2 | 📋 Planned |

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `backend/app/agents/orchestrator.py` | Main agentic loop (Pillar 2) — Phase 15/16 patches applied |
| `backend/app/core/security.py` | AuthContext + SecurityMesh (Pillar 1) |
| `backend/app/core/security_sentinel.py` | Proactive Threat Sentinel (32KB) — Phase 6c |
| `backend/app/core/self_healer.py` | SQL self-healing engine (Phase 6) |
| `backend/app/core/voting_executor.py` | **NEW** — Phase 14 Voting Executor (4-path, 627 lines) |
| `backend/app/core/healed_pattern_store.py` | **NEW** — Phase 16 Self-Healing Patterns DB (266 lines) |
| `backend/app/core/ciba_approval_store.py` | **NEW** — Phase 15 CIBA store (391 lines) |
| `backend/app/api/endpoints/ciba.py` | **NEW** — Phase 15 CIBA endpoints (263 lines) |
| `backend/app/core/vector_store.py` | Dual-backend Qdrant manager |
| `backend/app/core/graph_embedding_store.py` | Node2Vec + text hybrid (Pillar 5½) |
| `backend/app/core/meta_path_library.py` | 14 meta-paths, 22+ JOIN variants |
| `backend/app/core/graph_store.py` | NetworkX FK graph + AllPathsExplorer + TemporalGraphRAG |
| `backend/app/core/message_bus.py` | Redis pub/sub + streams (Phase 13) |
| `backend/app/core/negotiation_protocol.py` | 4-phase Negotiation Engine (Phase 13b) |
| `backend/app/core/agent_inbox.py` | AgentInbox per-agent inbox listener (19.7KB) |
| `backend/app/core/quality_evaluator.py` | QualityEvaluator — correctness_score + trajectory_adherence |
| `backend/app/core/meta_harness_loop.py` | Meta-Harness Loop (45KB) |
| `backend/app/core/failure_trigger.py` | Phase 11 failure trigger (12.6KB) |
| `backend/app/agents/swarm/planner_agent.py` | Planner Agent + Complexity Analyzer (19KB) |
| `backend/app/agents/swarm/synthesis_agent.py` | Synthesis Agent (16KB) |
| `backend/app/agents/swarm/message_dispatcher.py` | Bus integration + Agent Registry |
| `backend/app/tools/sql_executor.py` | SAP HANA executor (mock + hdbcli) |
| `backend/app/agents/orchestrator_tools.py` | Tool registry + 12 tool implementations |
| `docs/KYSM_HARNESS_ENGINEERING.md` | Harness Engineering principles + implementation |
| `docs/GRAPH_RAG_SAP_HANA_TECHNIQUES.md` | Graph RAG techniques deep-dive |
| `docs/MULTI_AGENT_SWARM_ARCHITECTURE.md` | Full swarm architecture documentation |
| `docs/MEMGRAPH_MIGRATION_GUIDE.md` | Memgraph Phase M1–M11 migration guide |
| `docs/SANDBOX_ARCHITECTURE.md` | 7-layer sandbox stack |
| `docs/INTER_AGENT_MESSAGE_BUS_DESIGN.md` | Phase 13 bus design |
| `docs/LEVEL5_ROADMAP.md` | **This file** |

---

## Recent Commits

```
9ef51de  feat(apr19): Phase 16 - Self-Healing Patterns DB (Qdrant-stored healed SQL)
acb50ea  feat(apr19): Phase 15 CIBA Approval Flow - block/tighten branching with async approve/deny
c4d087e  fix(apr19): Phase 14 Voting Executor integration bugs fixed
9554e79  docs: KYSM video research summary — 5 AI Engineer talks + 8 new ideas
9326438  fix(apr18): 5 healing fixes + EIGER schema + 50-query benchmark 49/50 pass
8014d78  docs: SESSION_APR_17.md — full audit sprint session log
```