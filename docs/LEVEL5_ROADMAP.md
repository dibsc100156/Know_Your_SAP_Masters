# KYSM Level-5 Roadmap — Consolidated Implementation Status
**Last Updated:** April 22, 2026 | Project: Know Your SAP Masters (SAP Masters)

---

## Executive Summary

**Status labels used in this roadmap:** ✅ Complete | 🟡 Partial | 🚧 Planned

A 17-phase roadmap for an autonomous enterprise SAP assistant. Each phase is independently deployable
and wires into the orchestrator via clearly defined entry/exit contracts.

**April 19 commits:**
- `c4d087e` — Phase 14 Voting Executor (3-path parallel, consensus boosting)
- `acb50ea` — Phase 15 CIBA Approval Flow (block/tighten → async approve/deny)
- `9ef51de` — Phase 16 Self-Healing Patterns DB (Qdrant-stored healed SQL → PATH_D fast-path)

**April 20 evening commits:**
- `(wip)` — Phases L5+20+21: Restored clean orchestrator, re-applied L5 routing + Phase 20 cost tracker + Phase 21 Formal Revision Loop (correct 12-space else-block indentation)
- **2026-04-22:** Phase 21 Formal Revision Loop wired through the live orchestrator/API path — bounded critique/validation/execution revision attempts now honor `max_iterations=3`, apply explicit confidence/stability exit conditions, and surface `formal_trace` + `revision_summary` in API responses. Targeted unittest coverage added in `backend/tests/test_phase21_formal_revision_loop.py`.

**April 20 commits:**
- `78366d7` — Phase L5: Tuned Complexity Router (TRIVIAL threshold 0.00)
- `b91aec6` — Priority 3: Per-Tier Quality Metrics Dashboard (Harness Runs metrics)
- `cd483bf` — Priority 5: CIBA Tier Configuration (Risk-adjusted approvals)
- `7be3aa3` — Priority 9: Dynamic Tool Injection by Tier, Priority 4: Graph Provenance Recorder
- `259ac2f` — Priority 7: BM25 Schema Scoring (3-signal RRF + centrality)
- `c36ff76` — Priority 8: SAP Note Knowledge Graph (Memgraph operational entities)
- `e2a0d05` — Priority 6: MCP Server for KYSM
- `8782e9f` — Priority 10: Fluent Orchestrator Builder Syntax

**April 22 work:**
- Hybrid graph runtime perf/load sign-off is now **GREEN** (`backend/reports/hybrid_graph_signoff_20260422T094235Z.json`)
- Native ranked-path probing tuned to BFS-limited Bolt execution; sign-off harness switched to direct Bolt measurement instead of subprocess overhead
- Passing metrics: native ranked-path p95 `6.716 ms`, mixed workload p95 `28.337 ms`, burst p95 `14.702 ms`, steady-state p95 `4.396 ms`
- Phase 19 core live wiring landed: Sentinel/CIBA pre-swarm override, tool-mode parallel dispatch, `dedup_only` tool-mode synthesis, session-aware API context, and targeted unittest coverage
- Phase 20 now runs on the live API path: `chat.py` uses `route_with_cost(...)`, exposes `cost_stats` / `routing_bypass_reason`, and has targeted unittest coverage for bypass + cache behavior
- Phase 23/24 platform extras now surface live layered guardrail + episodic session metadata through the sync chat API, with targeted unittest coverage for guardrail adapter behavior and episodic memory retention/dedup
- Phase 24 now goes beyond raw history loading: duplicate-turn lookup, recent query/result pairs, scratchpad-aware prompt context, and richer episodic metadata are wired into the live orchestrator path
- Phase 19 operator guidance is now documented in `docs/PHASE19_OPERATOR_GUIDE.md`
- Phase 22 fairness tests + queue policy are now documented/covered in `docs/PHASE22_QUEUE_POLICY.md` and `backend/tests/test_phase22_query_prioritization.py`
- Unified Memory Architecture follow-through is now live: `memory_context.py`, `memory_orchestrator.py`, `memory_policy.py`, and `memory_writeback.py` unify episodic/session/persistent memory reads and writes, with `memory_context` + `memory_trace` surfaced in the sync chat API.
- F3 + Phase 12 benchmark artifacts now live in `backend/benchmark_f3_phase12.py`, `backend/reports/benchmark_f3_phase12.json`, and `docs/F3_PHASE12_BENCHMARK.md`
- Meta-Harness reporting/apply flow now has targeted close-out coverage in `backend/tests/test_phase11_meta_harness_loop.py`
- Agent Inbox + Push Notifications are now live via `backend/app/core/agent_notifications.py`, `/chat/notifications*` endpoints, and targeted coverage in `backend/tests/test_phase17_agent_notifications.py`
- Long-running agent infrastructure is now live via `backend/app/core/long_running_jobs.py`, `run_orchestrator_long_task`, `/chat/jobs*`, and `/tasks/{task_id}/resume`
- Ralph Wiggum PR Review Loop is now live via `backend/app/core/pr_review_loop.py` and `/automation/pr-review-loop`
- Doc-Gardening Agent is now live via `backend/app/core/doc_gardening_agent.py` and `/automation/doc-gardening`
- Observability Query Interface is now live via `backend/app/core/observability_interface.py` and `/automation/observability/*`
- End-to-end validation sweep is now repeatable via `backend/end_to_end_validation_sweep.py` with report output at `backend/reports/end_to_end_validation_sweep.json`

**April 21 commits:**
- `eba82a6` — Feature 4: Plain-English Safeguards + Feature 5: Scatter-Gather Swarm
- `114aff4` — Feature 3: Bootstrap Model-Driven Tool Sequencing (Strands pattern)

**April 20 morning commits:**
- `fd038f1` — Phase L5: Complexity-Based Query Routing — 8 patches applied to orchestrator.py (TRIVIAL/SIMPLE/COMPLEX/EXPERT tier routing)
- `f049558` — Phase L5: wire get_routing_decision into chat API, return routing_tier/score in ChatResponse
- `VIDEO20` — docs: AGENTIC_DESIGN_PATTERNS_KYSM.md — 23-pattern analysis + 7-phase roadmap (Phases 18–24)

**Infrastructure snapshot (April 19):**
- Qdrant ✅ — 5 collections (sap_schema, sql_patterns, graph_node_embeddings, graph_table_context, qm_semantic_notifications)
- Memgraph ✅ — bolt://localhost:7687, hybrid Memgraph + NetworkX mirror runtime with native ranked-path querying and edge sync from NX metadata
- Redis ✅ — localhost:6379/0 (CIBA store + Celery broker + harness runs)
- RabbitMQ ✅ — amqp://sapmasters:sapmasters123@localhost:5672//
- Celery Worker ✅ — 4 threads, queues: agent + priority

---

## 5-Pillar RAG Architecture

| Pillar | Name | Component | Status |
|--------|------|-----------|--------|
| 1 | Role-Aware Security | `security.py` — SAPAuthContext, AuthContext masking, denied_tables | ✅ Complete |
| 2 | Agentic Orchestrator | `orchestrator.py` — `run_agent_loop()`, 8-step execution flow | ✅ Complete |
| 3 | Schema RAG | Qdrant semantic search over DDIC metadata | ✅ Complete |
| 4 | SQL Pattern RAG | `sql_pattern_lookup()`, 68+ patterns across 18 domains | ✅ Complete |
| 5 | Graph RAG | NetworkX FK graph, `AllPathsExplorer`, `TemporalGraphRAG`, Meta-Path Library | ✅ Complete |
| 5½ | Graph Embedding Search | Node2Vec + text hybrid in Qdrant | ✅ Complete |
| **L5** | **Complexity Routing** | `ComplexityRouter` — 4-tier skip guards + adaptive voting threshold | ✅ Complete |
| **L5+20** | **Resource-Aware Cost Router** | `RouterCostTracker` — per-tier budgets (TRIVIAL=5ms, SIMPLE=15ms, COMPLEX=50ms), adaptive bypass, and cheap-query validation coverage | ✅ Complete |
| **L5+21** | **Formal Revision Loop** | `FormalRevisionLoop` — CoT trace accumulation, bounded critique/validation/execution revisions, `max_iterations=3`, API `formal_trace` + `revision_summary` | ✅ Complete |
| **F3** | **Model-Driven Tool Sequencing** | `model_driven_sequencer.py` — description-aware bootstrap planning + iterative replanning/history surfaced in API for COMPLEX/EXPERT tiers, benchmarked Apr 22 | ✅ Complete |
| **F4** | **Plain-English Safeguards** | Tool descriptions encode mandatory safety guidance close to tool contracts | ✅ Complete |
| **F5** | **Scatter-Gather Swarm** | Multi-entity swarm routing with parallel fan-out and synthesis gather | ✅ Complete |

---

## 17-Phase Execution Roadmap

| Phase | Name | Description | Status |
|-------|------|-------------|--------|
| 0 | Meta-Path Match | Fast-path template matching (14 pre-computed JOIN paths) | ✅ Complete |
| 1 | Schema RAG | Qdrant semantic search over DDIC metadata | ✅ Complete |
| 1.5 | Graph Embedding | Node2Vec structural + text hybrid table discovery | ✅ Complete |
| 1.75 | QM Semantic Search | 20yr QM notification long-text semantic search | ✅ Complete |
| 2 | SQL Pattern RAG | Qdrant proven SQL patterns (18 domains) | ✅ Complete |
| 2b | Temporal Detection | Date/fiscal anchor detection → temporal filters | ✅ Complete |
| 2c | Phase 7 Temporal Engine | FY analysis, CLV, Supplier SPI, Economic Cycle | ✅ Complete |
| 2d | Phase 8 Negotiation Briefing | CLV, PSI, churn risk, BATNA synthesis | ✅ Complete |
| 3 | Graph RAG | All-ranked-paths → best JOIN via NetworkX + AllPathsExplorer | ✅ Complete |
| **L5** | **Complexity Routing** | TRIVIAL/SIMPLE/COMPLEX/EXPERT tier routing — 9-step skip guards + adaptive voting threshold | ✅ Complete |
| **1+** | **Prompt Chain Controller Architecture** | `ChainStep` + chain controller + quality gates + retry/stop policy + trace surfacing (C1.1–C1.5) | ✅ Complete |
| 4 | SQL Assembly | MANDT injection + AuthContext + Temporal filters | ✅ Complete |
| 5 | Critique Gate | 7-point SQL validation (SELECT-only, MANDT, JOIN sanity, LIMIT) | ✅ Complete |
| 5.5 | Validation Harness | `SELECT COUNT(*)` dry-run → syntax validation → autonomous fix | ✅ Complete |
| 6 | Self-Healing | Rule-based SQL correction (10 error codes → 6 heal strategies) | ✅ Complete |
| **6b** | **Memory Compounding** | Auto-vectorize healed SQL back into Qdrant pattern store | ✅ Complete |
| **6c** | **Proactive Threat Sentinel** | 6 threat engines + dynamic AuthContext tightening | ✅ Complete |
| **14** | **Voting Executor** | 4-path parallel SQL generation + consensus (Phase 16 — Apr 19) | ✅ Complete |
| **15** | **CIBA Approval Flow** | Block verdict → async approve/deny via Redis-backed store (Apr 19) | ✅ Complete |
| **17** | **Semantic Answer Validation** | Qdrant cross-check + 4-component scoring (semantic_sim, row_plausibility, intent_match, table_match) | ✅ Complete |
| 7 | Execution | SAP HANA mock executor — swap `hdbcli` for real connection to close P0 | 🟡 Partial |
| 8 | Result Masking | Role-based column redaction (Pillar 1) | ✅ Complete |
| 9 | Frontend Modernization | 8-phase + confidence gauge + signal table + dark card | ✅ Complete |
| **10** | **Multi-Agent Domain Swarm** | Planner + 7 Domain Agents + Synthesis Agent — ThreadPoolExecutor | ✅ Complete |
| 11 | Meta-Harness Loop | `meta_harness_loop.py` — collect→analyze→YAML→approve→patch with structured reporting/apply coverage | ✅ Complete |
| 12 | Quality Evaluator | `QualityEvaluator` — correctness_score + trajectory_adherence from phase states + structured trajectory log; live persistence/surfacing + benchmark artifacts expanded Apr 22 | ✅ Complete |
| 13 | Inter-Agent Message Bus | Redis pub/sub + streams, 6 message types | ✅ Complete |
| 13+ | Retrieval Quality Architecture | `RetrievalBundle` + reranker + retrieval critic + query-aware retrieval profiles + trace surfacing (R13.1–R13.5) | 🟡 Partial |
| 13b | Negotiation Protocol | 4-phase ASSERTING→CHALLENGING→NEGOTIATING→COMMITTED | ✅ Complete |
| **18** | **Exploration & Discovery** | Dynamic FK probing + hierarchical task decomposition with live orchestrator merge + surfaced decomposition plan | ✅ Complete |
| **19** | **Agent-as-Tool Dynamic Override** | Sentinel/CIBA triggers tool-mode suppression of agent autonomy; live wiring, tests, and operator guide now complete | ✅ Complete |
| **20** | **Resource-Aware Cost Router** | Per-tier routing cost tracking + bypass when overhead > threshold; live API path, trace output, and cheap-query validation complete | ✅ Complete |
| **21** | **Formal Revision Loop** | `RevisionLoop` class with live orchestrator/API integration, CoT trace + convergence detection | ✅ Complete |
| **22** | **Dynamic Query Prioritization** | Urgency×recency×role_authority scoring for Celery queue; live sync/async API wiring, fairness tests, and queue policy docs complete | ✅ Complete |
| **23** | **Safety Guardrails (Standalone)** | `safety_guardrails.py` now owns the live layered safety contract behind the sentinel adapter; guardrail verdict/profile surfaced in API | ✅ Complete |
| **24** | **Episodic Memory Store** | Redis-backed session scratchpad with live context/dedup integration, duplicate-turn lookup, recent query/result pairs, and surfaced episodic metadata in API | ✅ Complete |
| **24+** | **Unified Memory Architecture Follow-Through** | `MemoryContext` + memory orchestrator + write-back router + policy layer + trace surfacing (M8.1–M8.5) | 🟡 Partial |

---

## Phase 14 — Voting Executor

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

## Phase 15 — CIBA Approval Flow

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

## Phase 16 — Self-Healing Patterns DB

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

## Multi-Agent Domain Swarm Architecture

| Component | File | Status |
|---|---|---|
| Domain Agents (7 specialists) | `domain_agents.py` | ✅ Complete |
| Planner Agent + Complexity Analyzer | `swarm/planner_agent.py` (19KB) | ✅ Complete |
| Synthesis Agent (merge + rank + conflicts) | `swarm/synthesis_agent.py` (16KB) | ✅ Complete |
| Swarm entry point | `swarm/__init__.py` (2KB) | ✅ Complete |
| Inter-Agent Message Bus | `app/core/message_bus.py` | ✅ Complete |
| Negotiation Protocol | `app/core/negotiation_protocol.py` | ✅ Complete |
| Message Dispatcher + Agent Registry | `app/agents/swarm/message_dispatcher.py` | ✅ Complete |
| Agent Inbox | `app/core/agent_inbox.py` (19.7KB) | ✅ Complete |

### Live Test Results (April 12)
| Query | Swarm Routing | Agents | Result |
|---|---|---|---|
| vendor open POs > 50k + material | `cross_module` | pur + cross | ✅ 2 records |
| vendor payment terms vs customer credit | `cross_module` | bp + cross | ✅ 2 records |
| quality inspection results + material | `cross_module` | mm + qm + cross | ✅ 2 records |

---

## Memgraph Migration

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| M1 | Memgraph 2.12.0 + Lab — Docker Compose + adapter scaffold | ✅ Complete | `docker-compose.memgraph.yml`, `memgraph_adapter.py` |
| M2 | Native Cypher ranked paths (`[*BFS..N]`) | ✅ Complete | Hybrid model: native ranked-path exploration + NetworkX mirror for compatibility; April 22 sign-off green |
| M3 | `use_memgraph()` startup wiring | ✅ Complete | Activated from `main.py` when `MEMGRAPH_URI` is set |
| M4 | Celery async worker fleet | ✅ Complete | RabbitMQ-backed async execution |
| M5 | Redis dialog state | ✅ Complete | Session/dialog state hardened for distributed runtime |
| M6 | Qdrant migration | ✅ Complete | 5 collections active; vector backend is Qdrant, not Memgraph native vector search |
| M7 | SAP HANA connection pooling | 🟡 Partial | `hana_pool.py` + `HANA_MODE=pool` exist; real HANA is still not the default live runtime |
| M8 | Kubernetes autoscaling | ✅ Complete | KEDA `ScaledObject` manifests present for Celery workers |
| M9 | Multi-tenant isolation | ✅ Complete | `TENANT_ID` env wired into Memgraph tenant labels |

> **Note:** The current graph runtime is hybrid: Memgraph for persistence/native path querying, NetworkX mirror for compatibility and in-process graph algorithms.
> **Note:** Memgraph 2.x Cypher limitations — `LENGTH(path)`, `relationships(path)`, `shortestPath()`, path-list comprehensions NOT implemented.

---

## Harness Engineering — Implemented Principles

| Phase | Principle | File | Status |
|-------|-----------|------|--------|
| 5.5 | Sandboxed Validation | `sql_executor.py`, `orchestrator.py` | ✅ Complete |
| 6b | Memory Compounding | `orchestrator.py` (Step 8b) | ✅ Complete |
| 6c | Proactive Threat Sentinel | `security_sentinel.py` (32KB) | ✅ Complete |
| 11 | Meta-Harness Loop | `meta_harness_loop.py` + `failure_trigger.py` | ✅ Complete |
| 12 | Quality Evaluator | `quality_evaluator.py` | ✅ Complete |
| 12b | Trajectory Log | `HarnessRun.trajectory_log[]` with persisted `trajectory_event_count` + richer major-phase spans | ✅ Complete |
| 14 | Voting Executor | `voting_executor.py` | ✅ Complete |
| 15 | CIBA Approval | `ciba_approval_store.py` + `ciba.py` | ✅ Complete |
| 16 | Self-Healing Patterns DB | `healed_pattern_store.py` | ✅ Complete |
| 17 | Semantic Answer Validation | `semantic_answer_validator.py` — Qdrant cross-check + 4-component scoring | ✅ Complete |
| L4 | Real-Time Operations Monitoring | `monitoring_dashboard.py` + `eval.py` + `monitoring_panel.py` | ✅ Complete |
| **Videos** | Agentic Design Patterns Video Research | `docs/AGENTIC_DESIGN_PATTERNS_KYSM.md` (23-pattern analysis) | 🟡 Partial |

---

## Priority Build Order

| # | Priority | Item | Phase | Status |
|---|----------|------|-------|--------|
| L5 | — | Phase L5 Complexity Router — complete with adaptive voting thresholds | L5 | ✅ Complete |
| 18 | 🔴 P0 | Phase 18: Exploration & Discovery — dynamic FK probing + hierarchical decomposer | 18 | ✅ Complete (live wiring + tests Apr 22) |
| 19 | 🔴 P0 | Phase 19: Agent-as-Tool Dynamic Override — suppress autonomy on Sentinel/CIBA trigger | 19 | ✅ Complete (operator guide + tests Apr 22) |
| 20 | 🟢 P1 | Phase 20: Resource-Aware Cost Router — per-tier routing cost tracking | 20 | ✅ Complete (cheap-query validation added Apr 22) |
| 21 | 🟡 P1 | Phase 21: Formal Revision Loop — `exit_conditions` + `max_iterations=3` | 21 | ✅ Complete (live wiring + API surfacing Apr 22) |
| 22 | 🟡 P1 | Phase 22: Dynamic Query Prioritization — Celery queue scoring engine | 22 | ✅ Complete (fairness tests + queue policy Apr 22) |
| 23 | 🟢 P2 | Phase 23: Safety Guardrails (Standalone layer) — Sentinel split | 23 | ✅ Complete |
| 24 | 🟢 P2 | Phase 24: Episodic Memory — Redis session scratchpad | 24 | ✅ Complete |
| 24+ | 🟡 P2 | Unified Memory Architecture Follow-Through — `MemoryContext` + orchestrator + policy + write-back + trace | M8.1–M8.5 | 🟡 Partial (design defined Apr 22; follows live Phase 24) |
| 13+ | 🟡 P2 | Retrieval Quality Architecture — `RetrievalBundle` + reranker + critic + retrieval profiles + trace | R13.1–R13.5 | 🟡 Partial (design defined Apr 22; sharpens Pattern 13 retrieval quality) |
| 1+ | 🟡 P1 | Prompt Chain Controller Architecture — `ChainStep` + controller + quality gates + retry/stop + trace | C1.1–C1.5 | ✅ Complete (live chain trace + step verdicts wired Apr 22) |
| 1 | 🔴 P0 | Real SAP HANA activation (`HANA_MODE=pool`) — replace mock as the default runtime | M7 | 🚧 Planned |
| 2 | 🔴 P0 | Hybrid graph runtime load/perf sign-off (Memgraph + NX mirror, p95 target) | Ops | ✅ Complete |
| L4 | 🟢 P2 | Phase L4 Real-Time Monitoring Dashboard | L4 | ✅ Complete |
| 3 | 🟡 P1 | Agent Inbox + Push Notifications | Phase 17 | ✅ Complete (notification store + user/session endpoints Apr 22) |
| 4 | 🟡 P1 | BAPI Workflow Harness (Read-to-Write) | P1 | 🚧 Planned |
| 5 | 🟡 P1 | Long-Running Agent Infrastructure (6hr runs) | P1 | ✅ Complete (durable job store + 6h queue + resume/cancel Apr 22) |
| 6 | 🟢 P2 | Ralph Wiggum PR Review Loop | P2 | ✅ Complete (local review harness + API Apr 22) |
| 7 | 🟢 P2 | Doc-Gardening Agent (stale doc scanner) | P2 | ✅ Complete (scanner + issue scoring API Apr 22) |
| 8 | 🟢 P2 | Observability Query Interface (LogQL/PromQL) | P2 | ✅ Complete (safe query facade + traces API Apr 22) |

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `backend/app/agents/orchestrator.py` | Main agentic loop (Pillar 2) — Phase L5/15/16 patches applied |
| `backend/app/core/complexity_router.py` | **NEW** — Phase L5 4-tier complexity router (TRIVIAL→EXPERT) + skip guards |
| `backend/app/core/security.py` | AuthContext + SecurityMesh (Pillar 1)Context + SecurityMesh (Pillar 1) |
| `backend/app/core/security_sentinel.py` | Proactive Threat Sentinel (32KB) — Phase 6c |
| `backend/app/core/self_healer.py` | SQL self-healing engine (Phase 6) |
| `backend/app/core/voting_executor.py` | **NEW** — Phase 14 Voting Executor (4-path, 627 lines) |
| `docs/MONITORING_DASHBOARD.md` | Phase L4 — Real-Time Monitoring Dashboard reference doc |
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
| `backend/app/core/agent_notifications.py` | User/session-scoped task lifecycle notifications + unread badge store |
| `backend/app/core/long_running_jobs.py` | Durable long-running job state + resume/retry/cancel metadata |
| `backend/app/core/memory_context.py` | Unified `MemoryContext` contract + slice/budget/trace primitives |
| `backend/app/core/memory_orchestrator.py` | Read-path composition across episodic + persistent memory layers |
| `backend/app/core/memory_policy.py` | Central retention + visibility/redaction policy for memory slices |
| `backend/app/core/memory_writeback.py` | Event-driven write-back router for episodic/persistent memory |
| `backend/app/core/chain_types.py` | Formal `ChainStep` / gate / retry / stop contracts |
| `backend/app/core/chain_quality_gates.py` | Explicit PASS/RETRY/HALT quality gate engine |
| `backend/app/core/chain_retry_policy.py` | Central retry/stop decision policy |
| `backend/app/core/chain_controller.py` | Prompt chain controller with live step verdict tracing |
| `backend/app/core/pr_review_loop.py` | Ralph Wiggum PR review harness with bounded self/specialist review |
| `backend/app/core/doc_gardening_agent.py` | Stale-doc / broken-reference scanner with confidence+risk labels |
| `backend/app/core/observability_interface.py` | Safe LogQL/PromQL-style facade over monitoring + harness traces |
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
| `docs/MEMGRAPH_MIGRATION_GUIDE.md` | Memgraph migration guide — hybrid Memgraph + NetworkX + Qdrant status |
| `docs/SANDBOX_ARCHITECTURE.md` | 7-layer sandbox stack |
| `docs/INTER_AGENT_MESSAGE_BUS_DESIGN.md` | Phase 13 bus design |
| `docs/LEVEL5_ROADMAP.md` | **This file** |

---

## Recent Commits

```
f049558  feat(apr20): Phase L5 - wire get_routing_decision into chat API, return routing_tier/score
fd038f1  feat(apr20): Phase L5 - Complexity-Based Query Routing, 8 patches, all green
VIDEO20    docs(apr20): AGENTIC_DESIGN_PATTERNS_KYSM.md - 23 patterns + Phase 18-24 roadmap
9ef51de  feat(apr19): Phase 16 - Self-Healing Patterns DB (Qdrant-stored healed SQL)
acb50ea  feat(apr19): Phase 15 CIBA Approval Flow - block/tighten branching with async approve/deny
c4d087e  fix(apr19): Phase 14 Voting Executor integration bugs fixed
9554e79  docs: KYSM video research summary — 5 AI Engineer talks + 8 new ideas
```