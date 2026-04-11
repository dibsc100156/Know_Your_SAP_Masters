# Know Your SAP Masters - Master Architecture Overview
**Project:** Know Your SAP Masters (formerly SAP S/4 HANA Vendor Chatbot)
**Date:** 2026-03-21 | **Last Updated:** 2026-04-05 | **Phase: 8 COMPLETE | Phase 9 IN PROGRESS**
**Author:** OpenClaw AI Assistant

---

## 1. Executive Summary

Building an LLM-powered Chatbot on top of SAP S/4 HANA requires solving distinct challenges: finding the right tables (90,000+ tables), understanding complex joins, replicating SAP-specific SQL idioms, decomposing multi-step business questions, and enforcing strict data governance.

This is now an **Enterprise Master Data Chatbot** named **"Know Your SAP Masters"**. The strategy builds conversational capabilities across siloed Master Data domains first, then introduces complex cross-module relationships via Graph RAG.

The architecture uses a **5-Pillar Composite RAG System**, each solving a specific layer, orchestrated by an autonomous agent. **ChromaDB** serves as the unified vector store for both Schema RAG and SQL Pattern RAG.

---

## 2. Core Master Data Domains

| Domain | SAP Module | Key Master Data Objects | Core Tables (Examples) | Status |
|---|---|---|---|---|
| **Business Partner** | Cross-Module | Vendors, Customers, Roles, Addresses | `BUT000`, `LFA1`, `KNA1`, `ADRC` | ✅ Full |
| **Material Master** | MM / SD / PP | Materials, Products, Services, Plant Data | `MARA`, `MARC`, `MARD`, `MVKE` | ✅ Full |
| **Purchasing / Sourcing** | MM-PUR | Purchasing Info Records, Source Lists, Quotas | `EINA`, `EINE`, `EORD`, `EQUK` | ✅ Full |
| **Sales & Distribution** | SD | Pricing Conditions, Customer-Material Info, Routes | `KONP`, `KNMT`, `TVRO` | ⚠️ Stub |
| **Warehouse Management** | EWM / WM | Storage Bins, Storage Types, Handling Units | `LAGP`, `LQUA`, `VEKP` | ⚠️ Stub |
| **Quality Management** | QM | Inspection Plans, Master Characteristics, Quality Info | `MAPL`, `PLMK`, `QINF` | ⚠️ Stub |
| **Project System** | PS | WBS Elements, Networks, Project Definitions | `PRPS`, `PROJ`, `AFVC` | ⚠️ Stub |
| **Transportation Mgmt** | TM / LE-TRA | Freight Forwarders, Transportation Zones | `/SCMTMS/D_TORROT`, `VTTK` | ⚠️ Stub |
| **Customer Service** | CS | Service Masters, Warranties, Service Contracts | `ASMD`, `BGMK`, `VBAK` | ⚠️ Stub |
| **Environment, Health & Safety**| EHS | Substance Data, Dangerous Goods, Specs | `ESTRH`, `ESTVH`, `DGTMD` | ⚠️ Stub |
| **Variant Configuration** | LO-VC | Characteristics, Classes, Configuration Profiles | `CABN`, `KLAH`, `CUOBJ` | ⚠️ Stub |
| **Real Estate Management**| RE-FX | Architectural Views, Usage Views, RE Contracts | `VICNCN`, `VIBDAO`, `VIBDRO` | ⚠️ Stub |
| **Global Trade Services** | GTS | Customs, Commodity Codes, Sanctioned Party Lists | `/SAPSLL/PNTPR`, `/SAPSLL/PR` | ⚠️ Stub |
| **Finance & Controlling** | FI / CO | G/L Accounts, Cost Centers, Profit Centers | `SKA1`, `SKB1`, `CSKS`, `CEPC` | ⚠️ Stub |
| **Asset Accounting** | FI-AA | Fixed Assets, Depreciation terms | `ANLA`, `ANLZ`, `ANLB` | ⚠️ Stub |
| **Plant Maintenance** | PM | Equipment, Functional Locations | `EQUI`, `IFLOT`, `EQKT` | ⚠️ Stub |
| **Production Planning** | PP | Bill of Materials (BOM), Work Centers, Routings | `MAST`, `STPO`, `CRHD`, `PLKO` | ⚠️ Stub |
| **Human Capital** | HCM / HR | Employee Mini-Master, Org Units | `PA0000`, `PA0001`, `HRP1000` | ⚠️ Stub |
| **Industry: IS-OIL** | IS-OIL | Silo/Tank Data, Joint Venture Accounting (JVA) | `OIB_A04`, `OIG_V`, `T8JV` | ⚠️ Stub |
| **Industry: IS-Retail** | IS-R | Article Master, Site Master, Assortments | `MARA` (Article), `T001W`, `WRS1` | ⚠️ Stub |
| **Industry: IS-Utilities**| IS-U | Device Locations, Installations, Connection Objects | `EGERR`, `EANL`, `EVBS` | ⚠️ Stub |
| **Industry: IS-Health** | IS-H | Patients, Business Partners (Hospitals), Cases | `NPAT`, `NBEW`, `NPNZ` | ⚠️ Stub |
| **Taxation (India)** | CIN / GST | HSN/SAC Codes, GSTIN, Vendor GST Details | `J_1IG_HSN_SAC`, `J_1BBRANCH` | ⚠️ Stub |

> **Legend:** ✅ Full = real DDIC definitions loaded into ChromaDB | ⚠️ Stub = placeholder table entries (single-column) — domain schema stubs exist but not yet populated with real SAP DDIC data

---

## 3. The 5-Pillar Architecture

| Pillar | Strategy | Core Value | What it solves |
|---|---|---|---|
| 1 | **Role-Aware RAG** | **Right Access** | Security, SOX compliance, field-level masking, and scope filtering via AuthContext. |
| 2 | **Agentic RAG** | **Right Reasoning** | Multi-step planning, tool orchestration, and error self-correction via OrchestratorAgent. |
| 3 | **Schema RAG** | **Right Tables** | ChromaDB retrieval of flat DDIC table metadata for isolated Master Data queries. |
| 4 | **SQL RAG** | **Right Patterns** | Few-shot injection of proven SAP SQL idioms per domain via 68+ embedded patterns. |
| 5 | **Graph RAG** | **Right Relationships** | NetworkX traversal for multi-hop, cross-module joins (Phase 2). |

---

## 4. The Unified Stack Diagram

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                     USER INTERFACE (UI/UX)                            │
│  Natural Language Chat | Session History | Export | Auth Login        │
└───────────────────────────────────────────────┬─────────────────────────────┘
                                    │ SSO Token
┌───────────────────────────────────────────────▼─────────────────────────────┐
│                  PILLAR 1: ROLE-AWARE RAG LAYER                       │
│  [Identity] Fetch SAP Auth Object Profile (RFC)                       │
│  [Scope] Generate AuthContext (allowed BUKRS, EKORG, masked columns)  │
└───────────────────────────────────────────────┬─────────────────────────────┘
                                    │ AuthContext + Query
┌───────────────────────────────────────────────▼─────────────────────────────┐
│                  PILLAR 2: AGENTIC RAG (ORCHESTRATOR)                 │
│  IntentAnalyzer → SQLGenerator → SQLValidator → OrchestratorAgent     │
└─┬─────────────────┬─────────────────┬─────────────────┬─────────────────────┘
  │ calls           │ calls           │ calls           │ calls
┌─▼─────────┐ ┌─────▼─────┐ ┌─────────▼─┐ ┌─────────────▼─────────┐
│ PILLAR 3: │ │ PILLAR 4: │ │ PILLAR 5: │ │ OTHER TOOLS:          │
│ SCHEMA RAG│ │ SQL RAG   │ │ GRAPH RAG │ │ - SAP RFC Lookup      │
│ ChromaDB  │ │ ChromaDB  │ │ NetworkX  │ │ - Auth Checker        │
└─┬─────────┘ └─────┬─────┘ └─────────┬─┘ └─────────────┬─────────┘
  │                 │                 │                 │
  └─────────────────┴─────────────────┴─────────────────┘
                             │ Context + Auth Filters
┌────────────────────────────▼────────────────────────────────────────────────┐
│                    SQL GENERATION & VALIDATION                        │
│  [LLM] Generates HANA SQL using retrieved schemas + SQL patterns      │
│  [Validator] Checks syntax, performance, and auth constraints         │
│  [Self-Correction] Agent retries on failure                           │
└───────────────────────────────────────────────┬─────────────────────────────┘
                             │ Validated SQL
┌───────────────────────────────────────────────▼─────────────────────────────┐
│                    SAP S/4 HANA DATABASE (EXECUTION)                  │
└───────────────────────────────────────────────┬─────────────────────────────┘
                             │ Raw Results
┌───────────────────────────────────────────────▼─────────────────────────────┐
│                 RESPONSE & MASKING LAYER (ROLE-AWARE)                 │
│  [Masking] Redact sensitive fields (e.g., Bank Account)               │
│  [Audit] Log query, user, SQL hash, and auth result to secure ledger  │
└───────────────────────────────────────────────┬─────────────────────────────┘
                             │ Final Answer
                     User Interface
```

---

## 5. Technology Stack

| Component | Technology | Notes |
|---|---|---|
| **Vector Store (Schema RAG)** | **ChromaDB** | Unified for both Schema and SQL Pattern RAG. `chromadb.PersistentClient` with `all-MiniLM-L6-v2` embeddings. |
| **Vector Store (SQL RAG)** | **ChromaDB** | 68+ SQL patterns across 18 domains, embedded and upserted. |
| **Graph Store** | **NetworkX** + JSON | 80+ nodes, 100+ FK edges across 18 domains in `graph_store.py`. |
| **LLM Providers** | **OpenAI** (default) / **Anthropic** | `LLMProvider` ABC with `OpenAIProvider` and `AnthropicProvider`. Default: `gpt-4o-mini`. |
| **Orchestrator** | **Agentic loop** | `IntentAnalyzer` → `SQLGenerator` (5-pillar context) → `SQLValidator` → response. |
| **SQL Executor** | **Mock + Real** | `SAPSQLExecutor` in `tools/sql_executor.py` with mock mode for dev. |
| **API** | **FastAPI** | `app/main.py` — runs on port 8000. |
| **Schema Metadata** | **DDIC Python** | Domain schemas in `app/domain/*_schema.py`. 3 fully populated, 15 stubs. |

---

## 6. Vector Store Design (ChromaDB)

### Collections

| Collection | Contents | Dimension |
|---|---|---|
| `sap_master_schemas` | DDIC table metadata (name, description, columns, module) | 384 |
| `sap_sql_patterns` | Proven SAP SQL patterns (intent, business_use_case, SQL) | 384 |

### Seeding
- **`seed_all.py`** — Seeds both collections from domain schemas + `sql_patterns/library.py`
- Skips stub-only domains (tables with ≤1 column definition)
- Embedding model: `all-MiniLM-L6-v2` (384-dim, cosine similarity)

### Retrieval
- **`vector_store.py`** — `VectorStoreManager` wraps ChromaDB with `search_schema()` and `search_sql_patterns()`
- Domain-filtered queries supported via `where={domain: "..."}`
- Used by `rag_service.py` for 5-pillar context injection

---

## 7. SQL Pattern Library

**Location:** `app/core/sql_patterns/library.py`
**Patterns:** 68+ real SAP SQL patterns across 18 domains
**Pattern shape:**
```python
{
    "intent": "Find vendors by city",
    "business_use_case": "Purchasing team needs to locate vendors in a specific region",
    "tables": ["LFA1", "ADRC"],
    "sql": "SELECT LIFNR, NAME1, STRAS, REGION FROM LFA1 JOIN ADRC ON ... WHERE REGION = :region"
}
```

---

## 8. Graph Store (FK Relationships)

**Location:** `app/core/graph_store.py`
**Nodes:** 80+ DDIC tables across 18 domains
**Edges:** 100+ FK relationships

Key cross-module edges include:
- `MARA → EINA → LFA1` (Material → Vendor Info Record → Vendor)
- `MARA → MARC → T001W` (Material → Plant → Plant Master)
- `LFA1 → LFBK` (Vendor → Vendor Bank)
- `KNA1 → ADRC` (Customer → Address)
- `EINA → EINE` (Purchasing Info Record → Purchasing Org)
- `MSEG → MKPF` (Material Document → Material Document Header)
- `BSEG → BKPF` (Accounting Document → Document Header)
- `QALS → QAMV → QAVE → QAMR` (QM Inspection flow)

---

## 9. Implementation Phasing

### ✅ Phase 1: Isolated Master Data Foundations (Weeks 1-4)
- Schema RAG for BP, Material, Purchasing domains ✅
- SQL RAG with 68+ patterns across 18 domains ✅
- ChromaDB vector store (migrated from Qdrant) ✅
- Agentic orchestrator with IntentAnalyzer + SQLGenerator + SQLValidator ✅
- Mock SQL executor for dev/test ✅

### ✅ Phase 2: Cross-Module Relationships via Graph RAG (Weeks 5-8)
- Complete Graph RAG with 80+ nodes, 100+ edges ✅ (structural)
- NetworkX traversal for multi-hop joins ✅
- Stub domain schemas → real DDIC populated (Phase 2) ✅
- Node2Vec embeddings + text hybrid search ✅
- Meta-path library (14 patterns, FAST PATH) ✅

### ✅ Phase 4: Level 4→5 Bridge (Weeks 5-8)
- Self-critique loop (7-point validation) ✅
- Persistent memory layer (6-store) ✅
- Domain agents (7 specialists) + Supervisor routing ✅
- Self-healer (10-rule autonomous SQL repair) ✅

### ✅ Phase 5: Intelligence Layer (Weeks 9-12)
- DDIC auto-discovery (80+ tables, fires on RAG miss) ✅
- Eval dashboard (summary, by-domain/role/pattern, weekly trends) ✅
- Feedback agent (TABLE/COLUMN/FILTER/INTENT corrections) ✅
- Pattern ranking (boosted patterns from memory) ✅

### ✅ Phase 6: Autonomous Orchestration (Weeks 13-16)
- Multi-turn dialog manager (5 clarification types) ✅
- Autonomous recovery (self-heal at execution errors) ✅
- Closed self-improvement loop (promote/demote/ghost patterns) ✅
- Cross-module agent via Supervisor CROSS/FALLBACK routing ✅

### ✅ Phase 7: Temporal Engine (Apr 4, 2026)
- `temporal_engine.py` — 1,100+ lines, 5 sub-systems:
  - **FiscalYearEngine** — Multi-FY parsing, 4 calendar variants
  - **TimeSeriesAggregator** — MONTHLY/QUARTERLY/YEARLY + rolling averages
  - **SupplierPerformanceIndex** — delivery + quality + price composite (0-100)
  - **CustomerLifetimeValueEngine** — revenue + discounts + payment behavior + churn
  - **EconomicCycleTagger** — 8 macro events (2008 crisis → 2022 inflation)
- Wired into orchestrator Step 2c: fires on temporal/supplier/CLV/crisis keywords

### ✅ Phase 8: Intelligence Synthetics (Apr 5, 2026)
- **Negotiation Briefing Generator** (`negotiation_briefing.py` — 1,050+ lines)
  - PSI, churn risk, CLV tier, BATNA, payment score, top tactics, bottom line
  - 5 SAP SQL templates, 20-year mock data synthesis
  - Triggers on: negotiation/price/contract/vendor/customer keywords
- **QM Long-Text Semantic Search** (`qm_semantic_search.py` — 650+ lines)
  - ChromaDB embeddings for QMEL/VIQMEL/AFIH free-text (20yr history)
  - TF-IDF fallback if sentence-transformers unavailable
  - Triggered by QM inspection / quality / usage decision keywords
- **Step 1.75** (QM Semantic) fires after meta-path fast path
- **Step 2d** (Negotiation) fires after temporal analysis
- All 3 integration tests passing: QM fast-path ✅ QM dynamic ✅ vendor ✅

### 🚧 Phase 9: Frontend Modernization + Confidence Scoring (Apr 5, 2026)
- **API rewrite** — `/chat/master-data` now calls `run_agent_loop()` (1,290-line orchestrator)
  - All 8-phase fields exposed: critique, tool_trace, temporal, qm_semantic, negotiation_brief, self_heal
  - NegotiationBrief dataclass → dict conversion for JSON
  - New endpoints: `/domains` (18 domains), `/roles` (auth scopes)
- **Multi-signal confidence scoring** — 6 weighted signals:
  - SQL Critique (30%), Result Density (25%), Routing Path (15%),
    Autonomous Repair (10%), Temporal Precision (10%), Cross-Module Breadth (10%)
  - Composite + per-signal breakdown with colored bar visualization
- **Frontend v2** (`frontend/app.py` — 695 lines):
  - Confidence gauge + per-signal HTML table
  - Pillar activation map (8 badges showing which phases fired)
  - Phase 7 temporal analysis panel (SPI/CLV/FY/Economic Cycle JSON)
  - Negotiation intelligence dark card (CLV, PSI, tactics, BATNA)
  - QM semantic results with score chips
  - Routing path + pattern name badges
  - Numbered tool trace with phase labels
  - Self-heal amber banner
  - Backend health check on page load

### 📋 Phase 3: Real SAP HANA Connection (P0 — REMAINING)
- Wire real `hdbcli` connection to SAP HANA
- Replace mock executor with live queries
- Add MANDT/auth context to real connection pooling
- End-to-end test with real data
- Load test: 100 concurrent queries

---

## 10. Key Files

| File | Purpose |
|---|---|
| `app/agents/orchestrator.py` | **Main orchestrator** — 1,290 lines, 8-phase execution loop |
| `app/agents/orchestrator_tools.py` | Tool registry (18 tools), `call_tool`, `ToolResult`, `ToolStatus` |
| `app/api/endpoints/chat.py` | FastAPI endpoint — wires `run_agent_loop()` to frontend, full 8-phase response |
| `app/core/vector_store.py` | ChromaDB wrapper — `VectorStoreManager`, `search_schema`, `search_sql_patterns` |
| `app/core/graph_store.py` | Graph RAG — 80+ nodes, 100+ FK edges, `find_path`, `AllPathsExplorer`, `TemporalGraphRAG` |
| `app/core/graph_embedding_store.py` | Node2Vec + text hybrid embeddings in ChromaDB (87KB) |
| `app/core/meta_path_library.py` | 14 meta-paths, 22+ path variants, fast-path scoring (87KB) |
| `app/core/temporal_engine.py` | Phase 7 — FiscalYearEngine, TimeSeriesAggregator, SupplierPerformanceIndex, CLVEngine, EconomicCycleTagger (1,100+ lines) |
| `app/core/negotiation_briefing.py` | Phase 8 — NegotiationBrief dataclass, PSI, CLV, churn, BATNA, tactics (1,050+ lines) |
| `app/core/qm_semantic_search.py` | Phase 8 — QM semantic search, 20yr long-text embeddings (650+ lines) |
| `app/core/security.py` | SAPAuthContext — 4 roles, row-level scope, column masking |
| `app/core/memory_layer.py` | 6-store persistent memory — query history, pattern success/fail, gotchas |
| `app/core/self_healer.py` | 10-rule autonomous SQL repair on validation + execution errors |
| `app/core/dialog_manager.py` | Multi-turn clarification (5 types, session persistence) |
| `app/core/self_improver.py` | Closed self-improvement loop — promote/demote/ghost patterns |
| `app/core/schema_auto_discover.py` | DDIC mirror (80+ tables), fires on RAG miss |
| `app/core/eval_dashboard.py` | Eval reports — summary, by-domain/role/pattern, weekly trends |
| `app/core/sql_patterns/library.py` | 68+ SAP SQL patterns across 18 domains |
| `app/agents/domain_agents.py` | 7 domain specialists (BP, MM, PUR, SD, QM, WM, CROSS) |
| `app/agents/supervisor_agent.py` | Hermes 4-way decision tree (SINGLE/PARALLEL/CROSS/FALLBACK) |
| `app/agents/critique_agent.py` | 7-point SQL gatekeeper |
| `app/agents/feedback_agent.py` | 5 correction types — TABLE/COLUMN/FILTER/INTENT/DOMAIN |
| `frontend/app.py` | Streamlit frontend v2 — 695 lines, full 8-phase UI |
| `seed_all.py` | Seeds all ChromaDB collections with schemas + SQL patterns |

---

## 11. Environment & Dependencies

**Python venv:** `backend/.venv`
**Key packages:**
- `chromadb>=0.4.0` — Vector store
- `sentence-transformers>=2.2.0` — Embedding model
- `openai>=1.12.0` — Default LLM provider
- `anthropic>=0.20.0` — Alternate LLM provider
- `fastapi>=0.100.0` — API framework
- `uvicorn>=0.23.0` — ASGI server

**Start backend:**
```bash
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

**Seed vector stores:**
```bash
cd backend
.venv\Scripts\python.exe seed_all.py --force
```

---

*Last updated: 2026-04-04 — Phase 6 (Autonomous Orchestration) complete. Supervisor + 7 domain agents. Self-critique, self-heal, self-improve loop. Multi-turn dialog. DDIC auto-discovery. Eval dashboard. Feedback agent. CLAUDE.md is the authoritative agent guide.*
