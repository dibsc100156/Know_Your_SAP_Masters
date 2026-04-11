# Level 5 Roadmap — Last Updated: 2026-04-05

> **Project:** Know Your SAP Masters
> **Phase Status:** Phase 8 COMPLETE ✅ | Phase 9 IN PROGRESS 🚧
> **Stack:** FastAPI + Streamlit | ChromaDB (Schema + SQL + QM) | NetworkX (Graph RAG) | Node2Vec (Structural Embeddings)

---

## Phase Status Dashboard

| Phase | Name | Status | Date |
|-------|------|--------|------|
| 1 | Isolated Master Data Foundations | ✅ Complete | Mar 2026 |
| 2 | Graph RAG + Meta-Paths | ✅ Complete | Apr 2 |
| 3 | Real SAP HANA Connection | 📋 P0 Pending | — |
| 4 | Self-Critique + Domain Agents + Self-Healer | ✅ Complete | Apr 4 |
| 5 | Intelligence Layer (DDIC Auto-Disco, Eval, Feedback) | ✅ Complete | Apr 4 |
| 6 | Autonomous Orchestration (Dialog, Self-Improve) | ✅ Complete | Apr 4 |
| 7 | Temporal Engine (SPI, CLV, FY Analysis, Economic Cycles) | ✅ Complete | Apr 4 |
| 8 | Intelligence Synthetics (QM Semantic, Negotiation Briefing) | ✅ Complete | Apr 5 |
| **9** | **Frontend Modernization + Confidence Scoring** | 🚧 **IN PROGRESS** | Apr 5 |

---

## What's Built — Full Inventory (Apr 5, 2026)

### Backend Components

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Orchestrator (8-phase) | `agents/orchestrator.py` | 1,290 | ✅ |
| Orchestrator Tools (18 tools) | `agents/orchestrator_tools.py` | — | ✅ |
| Critique Agent (7-point gate) | `agents/critique_agent.py` | — | ✅ |
| Domain Agents (7 specialists) | `agents/domain_agents.py` | — | ✅ |
| Supervisor Agent | `agents/supervisor_agent.py` | — | ✅ |
| Self-Healer (10-rule repair) | `core/self_healer.py` | — | ✅ |
| Memory Layer (6-store) | `core/memory_layer.py` | — | ✅ |
| Dialog Manager | `core/dialog_manager.py` | — | ✅ |
| Self-Improver | `core/self_improver.py` | — | ✅ |
| Temporal Engine | `core/temporal_engine.py` | 1,100+ | ✅ |
| Negotiation Briefing | `core/negotiation_briefing.py` | 1,050+ | ✅ |
| QM Semantic Search | `core/qm_semantic_search.py` | 650+ | ✅ |
| Schema Auto-Discover | `core/schema_auto_discover.py` | — | ✅ |
| Eval Dashboard | `core/eval_dashboard.py` | — | ✅ |
| Feedback Agent | `agents/feedback_agent.py` | — | ✅ |
| Graph Store (80+ nodes) | `core/graph_store.py` | — | ✅ |
| Graph Embedding Store (Node2Vec) | `core/graph_embedding_store.py` | 87KB | ✅ |
| Meta-Path Library (14 paths) | `core/meta_path_library.py` | 87KB | ✅ |
| Security Mesh (4 roles) | `core/security.py` | — | ✅ |
| SQL Library (68 patterns) | `core/sql_library.py` | — | ✅ |
| API Endpoint (chat.py) | `api/endpoints/chat.py` | 205 | ✅ |

### Frontend Components

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Streamlit App v2 | `frontend/app.py` | 695 | ✅ |

---

## Phase 8 — Intelligence Synthetics (Apr 5, 2026) ✅

### What was built

#### Negotiation Briefing Generator (`negotiation_briefing.py`)
- `NegotiationBriefingGenerator` facade — PSI, churn risk, CLV tier, BATNA, payment score
- `NegotiationSQLGenerator` — 5 core SAP SQL templates for relationship analysis
- `NegotiationBriefFormatter` — text + JSON structured output
- 5 computed metrics: Price Sensitivity Index, Payment Reliability, Churn Risk, CLV Tier, BATNA Strength
- Triggers on: negotiation, price increase, contract renewal, vendor, customer — keywords

#### QM Long-Text Semantic Search (`qm_semantic_search.py`)
- Embeds QMEL/VIQMET/AFIH/IHPA free-text in ChromaDB via sentence-transformers
- `QMSemanticSearch.search()` — semantic query across 20 years of mechanic notes
- `QMSemanticSearch.get_failure_context()` — prior failure context for root cause
- `QMTextExtractor` — mock QM notification generator (reproducible, 500+ notifications)
- ChromaDB 1.5.x compatible, TF-IDF fallback if sentence-transformers unavailable

#### Orchestrator Wiring
- Step 0: Meta-Path Match (fast-path — pre-computed JOIN templates)
- Step 1: Schema RAG (table discovery via Qdrant)
- Step 1.5: Graph Embedding Search (Node2Vec structural discovery)
- **Step 1.75: QM Semantic Search** ← Phase 8 fires after fast path
- Step 2: SQL Pattern RAG (proven patterns via ChromaDB)
- Step 2b: Temporal Detection (date/fiscal period → temporal SQL filters)
- Step 2c: Temporal Analysis Engine (Phase 7 — FY analysis, CLV, supplier SPI)
- **Step 2d: Negotiation Briefing** ← Phase 8 fires after temporal analysis
- Step 3: Graph RAG (all-ranked-paths → best JOIN)
- Step 4: SQL Assembly + AuthContext + Temporal filter injection
- Step 5: Validate → Execute → Mask

#### Integration Tests: 3/3 PASSING ✅
- QM query (fast path MATCHED) → QM semantic fires AFTER fast path ✅
- Negotiation query (no fast path) → Negotiation Brief generated ✅
- Vendor master (fast path MATCHED) → Phase 8 correctly skipped ✅

---

## Phase 9 — Frontend Modernization + Confidence Scoring (Apr 5, 2026) 🚧

### What was built today

#### API Endpoint Rewrite (`api/endpoints/chat.py`)
- **Before:** Called `rag_service.py` → old `OrchestratorAgent` (LLM-based, limited fields)
- **After:** Calls `orchestrator.py` → `run_agent_loop()` (tool-based, full 8-phase)
- All 8-phase fields exposed: `critique`, `tool_trace`, `temporal`, `qm_semantic`, `negotiation_brief`, `self_heal`, `confidence_score`, `routing_path`, `pattern_name`
- NegotiationBrief dataclass → dict conversion for JSON serialization
- New endpoints: `/domains` (all 18 domains) + `/roles` (with auth scopes)

#### Multi-Signal Confidence Scoring (`orchestrator.py`)
New `_compute_confidence_score()` function — 6 signals, weighted composite:

| Signal | Weight | What it measures |
|--------|--------|-----------------|
| SQL Critique | 30% | 7-point gate normalized → query correctness |
| Result Density | 25% | Row count: 0=uncertain, 1-5=sparse, 6-100=healthy, 100+=rich |
| Routing Path | 15% | Fast path (meta-path match) = 100%, standard = 65% |
| Autonomous Repair | 10% | Self-heal fired = penalty (60%), clean = 100% |
| Temporal Precision | 10% | Date/fiscal filter present = higher specificity |
| Cross-Module Breadth | 10% | More tables = broader schema confidence |

New `result_dict` fields: `confidence_score` (full dict), `routing_path`, `pattern_name`

#### Frontend v2 (`frontend/app.py` — 695 lines)

**New panels added:**

| Panel | What it shows |
|-------|--------------|
| 📊 Confidence Score | Gauge bar + per-signal HTML table with colored score bars |
| 🗺️ Pillar Activation Map | 8 badges (P1-P8) showing which phases fired |
| 📅 Phase 7 Temporal Analysis | SPI / CLV / FY / Economic Cycle content in JSON + chips |
| 🎯 Negotiation Intelligence Card | Dark card — CLV tier, PSI, payment score, churn, tactics |
| 🔬 QM Semantic Results | Score chips + top 5 QM notification results |
| Routing Path Badge | ⚡Fast Path / 🔗Cross-Module / 📋Standard — color coded |
| Pattern Name Badge | Which SQL pattern template was used |
| Critique panel | Score/7 gates with pass/fail styling |
| Tool Trace | Numbered steps with phase labels, color-coded status |
| Self-Heal banner | Amber warning when autonomous repair fires |

**Sidebar upgrades:**
- Role auth scope displayed (company codes, description)
- All 21 domains (18 domains + auto + cross_module + transactional_purchasing)
- Backend health check on page load
- 8-phase stack caption

---

## Phase 3 — Real SAP HANA Connection (P0 — REMAINING)

**This is the only thing that matters before production.**

```
pip install hdbcli
```

Environment variables needed:
```
SAP_HANA_HOST=your-hana-host
SAP_HANA_PORT=30015
SAP_HANA_USER=your-user
SAP_HANA_PASSWORD=your-password
SAP_HANA_MANDT=100
```

Once wired:
1. Replace `sql_execute` mock `dry_run=True` with real `hdbcli` connection
2. Test 50-query golden dataset
3. Enable `MOCK_EXECUTION=false`
4. Load test: 100 concurrent queries

---

## Simon Willison Alignment (Updated Apr 5, 2026)

**Score: 12/14 Strong ✅ | 2/14 Partial ⚠️**

| Strong ✅ | Partial ⚠️ |
|----------|-----------|
| Agent Loop, Specialist Subagents, Parallel Subagents, Routing Handoffs | Token Budget Tracking (no per-call measurement) |
| Red/Green TDD (critique → self-heal → re-critique) | Eval Alerting (threshold-based alerts not wired to UI) |
| Hoarding (68 SQL patterns, 14 meta-paths, 80+ DDIC tables) | |
| Recombination (Graph RAG AllPathsExplorer) | |
| Self-Improvement (self_improver closed loop) | |
| Anti-Patterns auto-enforcement (7-pt critique) | |
| Multi-signal confidence scoring (6 signals, weighted composite) | |
| Context Engineering (5-pillar context assembly) | |

---

## What's Left

| Priority | Item | Impact |
|----------|------|--------|
| P0 | Real SAP HANA via `hdbcli` | Makes everything real |
| P1 | Benchmark Suite (50-query golden dataset) | Regression safety net |
| P1 | Eval Alerting (success_rate < 0.7 → alert) | Proactive quality monitoring |
| P2 | Token Budget Tracking per orchestrator call | Cost governance |
| P2 | CDS view equivalents for S/4HANA Cloud | Cloud compatibility |
| P3 | DDIC auto-population from DD08L | Zero manual graph building |

*Phase 3 is the only P0. Everything else compounds once real data flows.* 🦞
