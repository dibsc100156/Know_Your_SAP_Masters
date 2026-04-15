# CLAUDE.md - SAP Masters Agentic RAG System

**Project:** Know Your SAP Masters - Enterprise Master Data Chatbot
**Last Updated:** 2026-04-14
**Status:** Phases 0-10 ✅ | M1 (Memgraph schema) ✅ | M2 (native Cypher paths) ✅ | M4 (Qdrant cluster) ✅ | M5 (Celery async pool) ✅ | M3/M6/M7 Pending
**Simon Willison Alignment:** `docs/WILLISON_VALIDATION.md` - Score 11/14 ✅ | 3/14 ⚠️

---

## System Overview

This is an **agentic, multi-pillar RAG system** that translates natural language queries into safe,
executed SAP HANA SQL. It is not a chatbot - it is an autonomous SQL engineering system with
self-critique, self-healing, persistent memory, and multi-turn dialog capabilities.

The system sits between a user and SAP S/4 HANA. Every query goes through a layered pipeline:
security context → supervisor routing → schema discovery → SQL generation → self-critique →
validation → execution → masking → response.

---

## Architecture at a Glance

```
User Query
    │
    ├─ [Supervisor] ──► SINGLE ──► Domain Agent (bp/mm/pur/sd/qm/wm/cross)
    │                 ──► PARALLEL ──► Multiple agents (ThreadPoolExecutor)
    │                 ──► CROSS ──► Orchestrator (Graph RAG)
    │                 ──► FALLBACK ──► Standard Orchestrator
    │
    └─ [Orchestrator] ──► Meta-Path Match ──► Schema RAG ──► SQL RAG
                           ──► Graph RAG ──► DDIC Auto-Discover ──► SQL Assembly
                           ──► Self-Critique [4.5/5] ──► Validation ──► Execution
                           ──► Result Masking ──► Response
                           ──► Memory Log ──► Self-Improver
```

---

## Key Files

| File                                        | Purpose                                                                                                                                                                                                                                                  |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/app/agents/orchestrator.py`        | Main orchestrator - 7-step pipeline, all pillars wired                                                                                                                                                                                                   |
| `backend/app/agents/domain_agents.py`       | 7 domain specialists (BP, MM, PUR, SD, QM, WM, CROSS)                                                                                                                                                                                                    |
| `backend/app/agents/supervisor_agent.py`    | Hermes - routes to correct agent/execution path                                                                                                                                                                                                          |
| `backend/app/agents/critique_agent.py`      | 7-point SQL gatekeeper (DML check, MANDT, AuthContext, JOIN sanity, LIMIT guard)                                                                                                                                                                         |
| `backend/app/agents/feedback_agent.py`      | Parses user corrections → updates patterns + gotchas                                                                                                                                                                                                     |
| `backend/app/core/memory_layer.py`          | Persistent 6-store memory (query_history, patterns, failures, discoveries, gotchas, prefs)                                                                                                                                                               |
| `backend/app/core/self_healer.py`           | 10-rule autonomous SQL repair (ORA-00942, MANDT_MISS, etc.)                                                                                                                                                                                              |
| `backend/app/core/self_improver.py`         | Closed loop: promote/demote patterns, ghost injection, health reports                                                                                                                                                                                    |
| `backend/app/core/schema_auto_discover.py`  | DDIC fallback search (80+ tables, 18 domains) when RAG misses                                                                                                                                                                                            |
| `backend/app/core/dialog_manager.py`        | Multi-turn clarification (5 types: scope, entity, time, metric, domain)                                                                                                                                                                                  |
| `backend/app/core/eval_dashboard.py`        | Eval reports: summary, by-domain, by-role, weekly trends, recommendations                                                                                                                                                                                |
| `backend/app/core/security.py`              | SAPAuthContext - role-based table/column access + masking                                                                                                                                                                                                |
| `backend/app/core/graph_store.py`           | NetworkX graph - 80+ nodes, FK edges, meta-paths, temporal RAG                                                                                                                                                                                           |
| `backend/app/core/memgraph_adapter.py`      | **MEMGRAPH ACTIVE** - MemgraphGraphRAGManager wraps NetworkX + Memgraph in dual mode. Parses `init_schema.cql` directly, builds Memgraph + NX mirror in one pass, 114 tables, 137 edges, 97 cross-module bridges. See `docs/MEMGRAPH_MIGRATION_GUIDE.md` |
| `backend/app/core/graph_embedding_store.py` | Node2Vec + text embeddings in Qdrant (`graph_node_embeddings`, `graph_table_context` collections). `VECTOR_STORE_BACKEND=qdrant` env var.                                                                                                                                                                                                   |
| `backend/app/core/meta_path_library.py`     | 14 meta-path templates (procure-to-pay, order-to-cash, etc.)                                                                                                                                                                                             |
| `backend/app/core/sql_patterns/library.py`  | 68+ proven SQL patterns across 18 domains                                                                                                                                                                                                                |
| `backend/app/core/vector_store.py`          | Qdrant-backed schema + SQL pattern retrieval. ChromaDB retained as local-dev fallback. `VECTOR_STORE_BACKEND=qdrant` env var.
| `backend/app/workers/celery_app.py`         | Celery app singleton (`celery_app_instance`). **All `.conf.*` settings MUST be set before any `import app.workers.*` statement** to avoid circular import deadlock. Final `app = celery_app_instance` at module bottom for `-A` loader compatibility.    |
| `backend/app/workers/orchestrator_tasks.py` | 4 Celery tasks using `@shared_task` decorator (not `@app.task`). Lazy import of `celery_app_instance` inside `get_task_result()` only - no module-level Celery imports.                                                                                  |
| `backend/app/main.py`                       | FastAPI server - startup initializes vector store, Memgraph connection, dialog manager. All service inits run before the server accepts requests.                                                                                                        |
| `docker-compose.memgraph.yml`               | **NEW** - Memgraph + Qdrant + Redis + RabbitMQ horizontal scale stack                                                                                                                                                                                    |
| `docker/memgraph/init_schema.cql`           | **NEW** - Memgraph CQL init script - loads all 80+ nodes + 100+ edges                                                                                                                                                                                    |
| `k8s/`                                      | Kubernetes deployment: Helm-style templates, Kustomize overlays, HPA, KEDA queue autoscaling, StatefulSets for all data layers, NetworkPolicy, RBAC, PDBs                                                                                                |
| `docs/MEMGRAPH_MIGRATION_GUIDE.md`          | Phase-by-phase migration playbook: M1=init_schema.cql, M2=parse+load, M3=wiring, M4=validation, M5=query routing, M6=teardown NetworkX                                                                                                                   |
| `docs/GRAPH_RAG_SAP_HANA_TECHNIQUES.md`     | Deep-dive: BFS, all-simple-paths, meta-paths, temporal RAG, Node2Vec embeddings, community detection, CDS views                                                                                                                                          |

---

## Execution Flow (orchestrator.py)

```
run_agent_loop(query, auth_context, domain, verbose, use_supervisor)

Phase 0: Supervisor Gate
  → SupervisorAgent.decide() - SINGLE / PARALLEL / CROSS / FALLBACK
  → If SINGLE/PARALLEL/CROSS: delegate to supervisor.execute()
  → If FALLBACK: continue to standard orchestrator

Standard Orchestrator:
  Step 0:  Meta-Path Match - fast-path templates (procure-to-pay, order-to-cash, etc.)
  Step 1:  Schema RAG - schema_lookup() via Qdrant
  Step 1b:  DDIC Auto-Discover - fires if schema RAG returns empty (Phase 5)
  Step 1.5: Graph Embedding Search - Node2Vec + text hybrid (Pillar 51⁄2)
  Step 2:   SQL Pattern RAG - sql_pattern_lookup() + boosted patterns from memory
  Step 2b:  Temporal Detection - detect date/fiscal/Q# → temporal filters
  Step 3:   Graph RAG - all_paths_explore(), temporal_graph_search()
  Step 4:   SQL Assembly + AuthContext + Temporal filter injection
  Step 4.5: Self-Critique - critique_agent.critique() score ≥ 0.7 to pass
             → If FAIL: self_healer.heal() → re-score
  Step 5:   SQL Validation - sql_validate() (DML check, MANDT, AuthContext)
             → If FAIL: self_healer.heal() → retry validation → retry execution
  Step 6:   Execution - sql_execute() (mock)
             → If FAIL: self_healer.heal() → retry execution
  Step 7:   Result Masking - apply column redaction from AuthContext
  Step 8:   Synthesis - natural language answer
  Step 8b:  Memory Log - log_query(), log_pattern_success/failure()
             + self_improver.review_and_improve() - autonomous promotion/demotion
  Step 9:   API Response & Quality Evaluation - `QualityEvaluator` grades trajectory adherence via Redis trace
```

---

## SAP AuthContext (security.py)

Four pre-defined roles in `SAP_ROLES`:
- `AP_CLERK` - US companies 1000/1010, can see vendor + purchasing data
- `PROCUREMENT_MANAGER_EU` - EU companies 2000/2010, full procurement view
- `CFO_GLOBAL` - All company codes, full financials, no HR
- `HR_ADMIN` - All data except PO/BSEG

AuthContext controls:
- **Row scope**: allowed_company_codes, allowed_plants, allowed_purchasing_orgs
- **Table denial**: denied_tables list (e.g., AP_CLERK cannot see PA0008/MBEW)
- **Column masking**: masked_fields dict (e.g., LFBK-BANKN → "REDACTED")
- **WHERE injection**: get_where_clauses() returns per-table filter dicts

**Rule**: Every SQL MUST have `MANDT = '100'` or `MANDT = '<client>'`.
Never generate INSERT, UPDATE, DELETE, DROP, TRUNCATE, GRANT, or REVOKE.

---

## Domain Agents (domain_agents.py)

Seven specialists, each with:
- `can_handle(query, domain_hint)` → confidence 0.0-1.0
- `run(query, auth_context)` → full pipeline: schema → SQL → auth injection → execute → mask → synthesize

| Agent         | Domain               | Trigger Keywords (sample)                                            |
| ------------- | -------------------- | -------------------------------------------------------------------- |
| `bp_agent`    | Business Partner     | vendor, customer, credit limit, payment terms, blocked, DUNS         |
| `mm_agent`    | Material Master      | material, stock, valuation, MRP, ABC, BOM, routing                   |
| `pur_agent`   | Purchasing           | purchase order, RFQ, info record, scheduling agreement               |
| `sd_agent`    | Sales & Distribution | sales order, delivery, billing, pricing, incoterm                    |
| `qm_agent`    | Quality Management   | inspection, nonconformance, usage decision, QM lot                   |
| `wm_agent`    | Warehouse Management | storage bin, handling unit, transfer order, FIFO                     |
| `cross_agent` | Cross-Module         | spend analysis, procure-to-pay, order-to-cash, material traceability |

Use `route_query(query, domain_hint, top_k)` to get ranked agents.
Use `run_agents_parallel([(q, agent, ctx), ...])` for parallel execution.

---

## Supervisor Decision Types (supervisor_agent.py)

| Decision       | Trigger                                                          | Execution                                              |
| -------------- | ---------------------------------------------------------------- | ------------------------------------------------------ |
| `SINGLE`       | One agent confidence ≥ 0.7                                       | That domain agent alone                                |
| `PARALLEL`     | ≥2 domain signals + complexity keywords                          | All matched agents concurrently via ThreadPoolExecutor |
| `CROSS_MODULE` | Cross-module keywords (spend, procure-to-pay) OR ≥2 entity types | Standard orchestrator with full Graph RAG              |
| `FALLBACK`     | No agent ≥ 0.4 confidence                                        | Standard orchestrator                                  |

---

## Self-Critique (critique_agent.py) - 7-point checklist

Every generated SQL is scored before execution:

1. SELECT-only (no DML/DDL) - CRITICAL
2. MANDT filter present - CRITICAL
3. AuthContext filters applied - HIGH
4. No Cartesian product (JOIN without ON) - HIGH
5. LIMIT/max_rows guard present - MEDIUM
6. JOIN keys exist in both tables - HIGH
7. Date filters have reasonable range - MEDIUM

Score < 0.7 → self_healer attempts auto-correction → re-score.

---

## Self-Healer (self_healer.py) - 10 error rules

Fires at three points: critique failure, validation error, execution error.

| Rule                  | Trigger                 | Fix Strategy                                   |
| --------------------- | ----------------------- | ---------------------------------------------- |
| `MANDT_MISSING`       | MANDT not in SQL        | Inject `MANDT = '100'`                         |
| `CARTESIAN_PRODUCT`   | Cross join detected     | Simplify: reduce to single table               |
| `DIVISION_BY_ZERO`    | ORA-01476               | Wrap with `CASE WHEN denom=0`                  |
| `TABLE_NOT_FOUND`     | ORA-00942 / not in DDIC | Strip JOIN to missing table                    |
| `INVALID_COLUMN`      | 42S22 / unknown column  | Remove offending column or SELECT *            |
| `SYNTAX_ERROR`        | 37000 / parse error     | Strip ORDER BY, complex WHERE, trailing commas |
| `SUBQUERY_JOIN_ERROR` | ORA-01799               | Simplify to direct JOIN                        |
| `SAP_AUTH_BLOCK`      | Auth block              | Add MANDT filter + escalate                    |
| `EMPTY_RESULT`        | No rows returned        | Relax WHERE, expand date range, increase LIMIT |
| `ADD_NVL`             | Division/density calc   | Wrap with NVL/IFNULL                           |

---

## Persistent Memory (memory_layer.py)

Location: `~/.openclaw/workspace/memory/sap_sessions/`

| Store | File | Purpose |
|-------|------|---------|
| Query history | `query_history.jsonl` | Every query: timestamp, role, domain, SQL fingerprint, critique score, result |
| Pattern success | `pattern_success.json` | Patterns with success_count, avg_critique_score, SQL fingerprints |
| Pattern failures | `pattern_failures.json` | Patterns with failure_count, error messages |
| Schema discoveries | `schema_discoveries.json` | Tables discovered at runtime via DDIC/graph |
| Gotchas | `gotchas.json` | Known edge cases with hit counts |
| User preferences | `user_preferences.json` | Per-role output format, max_rows, language |
| Feedback log | `feedback_log.jsonl` | User corrections: original SQL, corrected SQL, type |
| Dialog sessions | `dialog_sessions/*.json` | Multi-turn conversation state |

Key APIs:
- `sap_memory.get_boosted_patterns(domain, top_k)` - patterns ranked by success ratio
- `sap_memory.get_eval_stats()` - success rate, avg time, per-domain breakdown
- `sap_memory.log_gotcha(pattern, severity)` - log edge case for future hits

---

## Self-Improver (self_improver.py) - Closed Feedback Loop

Runs automatically after every orchestrator query:

1. **Promotion**: patterns with ≥5 consecutive successes → rank boost
2. **Demotion**: patterns with ≥3 failures and ratio <0.4 → buried
3. **Ghost injection**: ad-hoc SQLs seen ≥3 times with good critique scores → named ghost pattern
4. **Heal tracking**: patterns requiring self-heal → logged as gotcha
5. **Feedback integration**: `record_feedback_correction()` called by feedback_agent

`self_improver.get_pattern_health_report()` → healthy/degraded/buried/ghost breakdown.
`self_improver.run_autonomous_review()` → callable by cron on startup.

---

## Dialog Manager (dialog_manager.py)

Multi-turn clarification. 5 types:
- `SCOPE` - "all vendors or specific?"
- `ENTITY` - "which vendor/material/customer? provide ID"
- `TIME_RANGE` - "which period? this month/quarter/year/last 12 months"
- `METRIC` - "what aspect? payment history / open invoices / spend analysis"
- `DOMAIN` - "which domain did you mean? cross-module or specific area?"

Context carry-over: time_range, entity scope, domain decisions from prior turns persist.
Session persistence: `DialogManager` saves state to `dialog_sessions/<session_id>.json`.

---

## Schema Auto-Discovery (schema_auto_discover.py)

80+ tables embedded in DDIC mirror across 18 domains.
Fires ONLY when both Schema RAG AND SQL Pattern RAG return nothing.
Logs discoveries to `schema_discoveries.json` when confidence ≥ 0.6.

`schema_auto_discoverer.search(query, auth_context, domain_hint)` → top 5 tables with scores.
`schema_auto_discoverer.build_select_sql(table, fields, auth_context)` → safe SELECT with MANDT + AuthContext filters.

---

## Graph Store - Dual Mode (graph_store.py + memgraph_adapter.py)

- **114 tables**, **137 FK relationships**, **97 cross-module bridges** across 18 domains
- **Dual-mode**: NetworkX mirror always in sync with Memgraph. If Memgraph is unavailable, falls back to NX transparently.
- **Memgraph** holds the authoritative persistent graph; **NetworkX** provides fast in-process traversal
- **init_schema.cql** loaded at startup from `docker/memgraph/init_schema.cql` - parsed directly by MemgraphGraphRAGManager
- **Schema loading**: `_parse_node_statement()` and `_parse_edge_statement()` parse CQL into node/edge metadata, then bulk-load into Memgraph via Bolt + build NX mirror locally in one pass

### NetworkX Mirror (graph_store.py) - Key Capabilities

- **Nodes**: 114 tables, 21 SAP modules
- **`find_path(start, end)`** - BFS shortest path
- **`all_simple_paths(start, end, max_depth=5)`** - enumerate all JOIN paths (path scoring penalizes 1:N cardinality and huge table transits, rewards cross-module bridges)
- **`get_subgraph_context(path)`** - returns tables, joins, cross-module bridges for a given path
- **`get_structural_role(table)`** - returns hub / bridge / authority / spoke based on degree + betweenness centrality
- **`get_connected_tables(table, depth=2)`** - neighborhood
- **Meta-paths**: 14 pre-defined JOIN templates (vendor_master_basic, procure_to_pay, order_to_cash, etc.)
- **`generate_temporal_sql_filters(table, as_of_date)`** - key-date / fiscal year / fiscal period filters

**Node2Vec embeddings** (`graph_embedding_store.py`):
- Qdrant collections: `graph_node_embeddings` (Node2Vec 64-dim), `graph_table_context` (text semantic). Path: `~/.openclaw/workspace/chroma_graph_db/` for local dev.
- Collections: `graph_node_embeddings` (Node2Vec 64-dim), `graph_table_context` (text semantic)
- Structural score: 35% degree centrality + 25% betweenness + 25% bridge bonus + 15% cross-module

---

## SQL Patterns (sql_patterns/library.py)

68+ proven SAP SQL patterns across 18 domains.
Format: `{intent, business_use_case, tables, sql, select_columns, example_queries, row_count_warnings}`

Patterns have `domain`, `tags[]`, `description` - matched by keyword, tag, description, table coverage.
Score > 5.0 from `meta_path_library.match()` = strong hit → FAST PATH (skip Schema + SQL RAG).

---

## Memgraph Architecture - Critical Implementation Notes

> **IMPORTANT - Read before debugging Memgraph:**
>
> The `memgraph_adapter.py` uses regex parsing on `init_schema.cql`. Two bugs to watch for:
>
> 1. `_parse_node_statement()` regex has **6 capture groups** - code accesses `m.group(6)` for bridge flag (NOT 7). The old code called `m.group(7)` which caused `IndexError: no such group`.
> 2. `_parse_edge_statement()` regex parses the `condition:"...", cardinality:"..."` block from `edge_match.group(3)` (the full MATCH line), NOT from `edge_match.group(0)`. This is intentional - avoids the `[^}]*` in group 0 swallowing the internal quotes.
>
> **Startup verification:** Check `main.py` startup logs for `[STARTUP] Memgraph Graph RAG:` - if Memgraph fails to connect or parse, it falls back to NetworkX silently. Set `MEMGRAPH_URI=bolt://localhost:7687` env var.
>
> **Direct test:**
> ```python
> from app.core import use_memgraph
> mg = use_memgraph(uri='bolt://localhost:7687')
> print(mg.stats())  # should show 114 tables, 137 edges
> ```

---

## Critically Important Rules

### SQL Safety
- **NEVER** generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, GRANT, REVOKE
- **ALWAYS** include `MANDT = '100'` or `MANDT = '<client>'` in WHERE clause
- **ALWAYS** apply AuthContext filters (company codes, plants, purchasing orgs)
- **ALWAYS** include LIMIT/max_rows guard (default 100)
- **NEVER** expose PA0008 (HR payroll), PAYR, or denied_tables
- **NEVER** expose masked columns (LFBK-BANKN, LFA1-STCD1 for AP_CLERK role)

### SAP Conventions
- Date format: `YYYYMMDD` (e.g., `'20240315'`)
- Client: `MANDT = '100'` (development)
- CHAR vs NUMC: never compare CHAR to NUMC directly - use `TRIM()` or type-cast
- Currency amounts: always with `CUKY` (currency key) column alongside
- Quantity amounts: always with `MEINS` (unit of measure) alongside

### Multi-Language Support
- UI language: user-facing responses follow user query language
- SQL: always English/Latin-character identifiers
- Supported user languages: English, Hindi, Tamil, Telugu (greetings and responses)

---

## Testing

Run orchestrator directly:
```bash
cd backend
python -c "from app.agents.orchestrator import run_agent_loop; from app.core.security import security_mesh
auth = security_mesh.get_context('AP_CLERK')
result = run_agent_loop('vendor payment terms for company 1000', auth, 'business_partner', verbose=True)"
```

Check Memgraph status and graph stats:
```bash
python -c "from app.core import use_memgraph; mg = use_memgraph(uri='bolt://localhost:7687'); print(mg.stats())"
```

Check eval dashboard:
```bash
python -c "from app.core.eval_dashboard import EvalDashboard; d = EvalDashboard(); print(d.format_text(d.generate_report('all')))"
```

Check pattern health:
```bash
python -c "from app.core.self_improver import self_improver; print(self_improver.get_pattern_health_report())"
```

---

## Quick Reference

| Component | Import Path |
|-----------|-----------|
| Orchestrator | `from app.agents.orchestrator import run_agent_loop` |
| Supervisor | `from app.agents.supervisor_agent import SupervisorAgent` |
| Domain Agents | `from app.agents.domain_agents import get_domain_agent, route_query, run_agents_parallel` |
| Critique Agent | `from app.agents.critique_agent import critique_agent` |
| Feedback Agent | `from app.agents.feedback_agent import feedback_agent` |
| Memory | `from app.core.memory_layer import sap_memory` |
| Self-Healer | `from app.core.self_healer import self_healer` |
| Self-Improver | `from app.core.self_improver import self_improver` |
| Dialog Manager | `from app.core.dialog_manager import DialogManager` |
| Eval Dashboard | `from app.core.eval_dashboard import EvalDashboard` |
| DDIC Auto-Discover | `from app.core.schema_auto_discover import schema_auto_discoverer` |
| Security/Auth | `from app.core.security import security_mesh, SAPAuthContext` |
| Graph Store | `from app.core.graph_store import graph_store` |
| Memgraph | `from app.core import use_memgraph` then `mg = use_memgraph(uri='bolt://localhost:7687')` |
| Graph Embeddings | `from app.core.graph_embedding_store import graph_embedding_store` |
| Meta-Paths | `from app.core.meta_path_library import meta_path_library` |
| SQL Patterns | `from app.core.vector_store import vector_store_manager` |
| Steiner Tree Math | `from app.core.graph_store import SteinerTreeExplorer` |
| CDS Equivalents | `from app.core.cds_mapping import format_cds_join, get_cds_view` |

---

*This file is the authoritative guide for any AI agent working on this codebase.*
*Last major update: 2026-04-08 - Memgraph Migration Phase M1-M4 & M6 completed.*
