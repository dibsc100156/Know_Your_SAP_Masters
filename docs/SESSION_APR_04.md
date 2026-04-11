# Session Summary — April 4, 2026

**User:** Sanjeev
**Session Lead:** Vishnu (AI Agent) ॐ
**Session Goal:** Build Phases 4, 5, and 6 of the SAP Masters roadmap

---

## What Was Built

### Phase 4: Level 4→5 Bridge

#### 1. `critique_agent.py` — NEW (Phase 4, ~3KB)
**Location:** `backend/app/agents/critique_agent.py`

7-point SQL validation gate that fires before every execution:
1. SELECT-only check (DML/DDL = CRITICAL FAIL)
2. MANDT client filter presence
3. AuthContext filters applied to all tables
4. JOIN sanity (no Cartesian products)
5. LIMIT/max_rows guard present
6. JOIN keys exist in both tables
7. Date filters have reasonable range

Score 0.0-1.0, threshold 0.7 to pass. Auto-heals with self_healer on failure.
Singleton: `critique_agent`

**Wired into orchestrator at Step [4.5/5].**

---

#### 2. `memory_layer.py` — NEW (Phase 4, ~18KB)
**Location:** `backend/app/core/memory_layer.py`

Persistent 6-store memory layer. Location: `~/.openclaw/workspace/memory/sap_sessions/`

| Store | File | Purpose |
|-------|------|---------|
| Query history | `query_history.jsonl` | Every query: timestamp, role, domain, SQL fingerprint, critique score, result |
| Pattern success | `pattern_success.json` | Patterns with success_count, avg_critique_score, SQL fingerprints |
| Pattern failures | `pattern_failures.json` | Failed patterns with error messages, failure counts |
| Schema discoveries | `schema_discoveries.json` | Runtime-discovered tables via DDIC/graph/user hints |
| Gotchas | `gotchas.json` | Known edge cases with severity + hit counts |
| User preferences | `user_preferences.json` | Per-role output format (table/json/csv), max_rows, language |

Key APIs:
- `sap_memory.get_boosted_patterns(domain, top_k)` — success-ratio-ranked patterns for Step [2/5]
- `sap_memory.log_query(...)` — every orchestrator run logged
- `sap_memory.get_eval_stats()` — success rate, avg time, per-domain breakdown
- `sap_memory.log_gotcha(...)` — edge cases with hit-count tracking

**Wired into orchestrator at Step [8b]: logs after every query execution.**

---

#### 3. `domain_agents.py` — NEW (Phase 4, ~23KB)
**Location:** `backend/app/agents/domain_agents.py`

7 domain specialist agents:

| Agent | Domain | Primary Tables |
|-------|--------|---------------|
| `bp_agent` | Business Partner | LFA1, KNA1, BUT000, ADRC |
| `mm_agent` | Material Master | MARA, MARC, MARD, MBEW, MSKA |
| `pur_agent` | Purchasing | EKKO, EKPO, EINA, EINE, EORD |
| `sd_agent` | Sales & Distribution | VBAK, VBAP, LIKP, KNVL, KONV |
| `qm_agent` | Quality Management | QALS, QMEL, MAPL, QAMV, QAVE |
| `wm_agent` | Warehouse Management | LAGP, LQUA, VEKP, MLGT |
| `cross_agent` | Cross-Module | Dynamically resolved via Graph RAG |

Each agent has:
- `can_handle(query, domain_hint)` → confidence 0.0-1.0 (keyword + signal scoring)
- `run(query, auth_context)` → full pipeline: schema lookup → SQL pattern → auth injection → execute → mask → synthesize
- `route_query(query, domain_hint, top_k)` → ranked agent list
- `run_agents_parallel([(q, agent, ctx)...])` → ThreadPoolExecutor for parallel execution

---

#### 4. `supervisor_agent.py` — NEW (Phase 4, ~14KB)
**Location:** `backend/app/agents/supervisor_agent.py`

Hermes — master orchestrator that decides HOW to route every query.

4-way decision tree (fires as Phase 0 gate in orchestrator):

| Decision | Trigger | Execution Path |
|----------|---------|---------------|
| `SINGLE` | One agent confidence ≥ 0.7 | That domain agent alone |
| `PARALLEL` | ≥2 domain signals + complexity keywords | All matched agents in parallel |
| `CROSS_MODULE` | Cross-module keywords or ≥2 entity types | Standard orchestrator + Graph RAG |
| `FALLBACK` | No agent ≥ 0.4 confidence | Standard orchestrator |

**Wired into orchestrator at Phase 0 gate** (use `use_supervisor=False` to bypass).

---

#### 5. `self_healer.py` — NEW (Phase 4, ~18KB)
**Location:** `backend/app/core/self_healer.py`

Autonomous SQL repair engine. 10 rules:

| Rule | Trigger | Fix |
|------|---------|-----|
| `MANDT_MISSING` | MANDT not in SQL | Inject `MANDT = '100'` |
| `CARTESIAN_PRODUCT` | Cross join detected | Simplify to single table |
| `DIVISION_BY_ZERO` | ORA-01476 | Wrap with `CASE WHEN denom=0` |
| `TABLE_NOT_FOUND` | ORA-00942 / DDIC miss | Strip JOIN to missing table |
| `INVALID_COLUMN` | 42S22 / unknown column | Remove column or SELECT * |
| `SYNTAX_ERROR` | 37000 / parse error | Strip ORDER BY, commas, duplicate WHERE |
| `SUBQUERY_JOIN_ERROR` | ORA-01799 | Simplify to direct JOIN |
| `SAP_AUTH_BLOCK` | Auth block | Add MANDT + escalate |
| `EMPTY_RESULT` | No rows | Relax WHERE, expand date range |
| `ADD_NVL` | Division expression | Wrap with NVL/IFNULL |

**Wired into orchestrator at THREE points:**
- Critique failure → self-heal → re-score
- Validation error → self-heal → re-validate → retry execution
- Execution error → self-heal → re-validate → retry execution

Singleton: `self_healer`

---

### Phase 5: Intelligence Layer

#### 6. `schema_auto_discover.py` — NEW (Phase 5, ~51KB)
**Location:** `backend/app/core/schema_auto_discover.py`

80+ tables embedded in DDIC mirror across 18 domains (LFA1 → VTTK, QALS → PA0008).
Fires ONLY when Schema RAG AND SQL Pattern RAG both return empty — last resort before SELECT *.

Search scoring:
- Table name exact/prefix match: +0.8
- Table description word overlap: +0.3 × overlap_ratio
- Domain hint match: +0.3
- Field name match (exact): +0.5 per field
- Field description keyword match: +0.2 × overlap
- Cross-module bridge bonus: +0.15 (hub tables with LIFNR/KUNNR/MATNR/EBELN/VBELN)
- Penalty for domain mismatch: 0.7×

Auto-logs discoveries to `schema_discoveries.json` when confidence ≥ 0.6.
`build_select_sql()` generates safe SELECT with MANDT + AuthContext filters automatically.

**Wired into orchestrator at Step [1b/5]: fires when schema RAG returns empty.**

---

#### 7. `eval_dashboard.py` — NEW (Phase 5, ~17KB)
**Location:** `backend/app/core/eval_dashboard.py`

Eval report generator from memory/sap_sessions/ data:

Sections:
- **Summary**: total queries, success/error/empty rates, avg/p95 execution time, avg critique score
- **By Domain**: success rate per domain with ASCII bar chart
- **By Role**: query count and success rate per role
- **By Pattern**: top patterns ranked by success ratio + total uses
- **Gotchas**: top triggered edge cases with hit counts
- **Slowest Queries**: top-N queries by execution time
- **Weekly Trend**: 7-day rolling trend with daily breakdown
- **Recommendations**: HIGH/MEDIUM/INFO actionable recommendations

`EvalDashboard.format_text(report)` → ASCII dashboard for console/email.
`generate_report(period)` → "last_24h" | "last_7d" | "last_30d" | "all"

---

#### 8. `feedback_agent.py` — NEW (Phase 5, ~20KB)
**Location:** `backend/app/agents/feedback_agent.py`

Parses user corrections and applies them to patterns + SQL.

5 correction types via regex:
- `TABLE_REPLACEMENT`: "use KNA1 instead of LFA1" → swap JOIN tables
- `COLUMN_REPLACEMENT`: "use STCD2 not STCD1" → swap SELECT columns
- `FILTER_ADDITION`: "add company code filter" → inject WHERE clause
- `FILTER_REMOVAL`: "remove plant filter" → strip WHERE condition
- `INTENT_CORRECTION`: "I meant sales not purchasing" → mark as intent mismatch

Applies: SQL correction + pattern update + gotcha log + feedback_log.jsonl persistence.

Singleton: `feedback_agent`

---

### Phase 6: Autonomous Orchestration

#### 9. `dialog_manager.py` — NEW (Phase 6, ~28KB)
**Location:** `backend/app/core/dialog_manager.py`

Multi-turn clarification manager. Sessions persisted to `memory/sap_sessions/dialog_sessions/`.

5 clarification types:
- `SCOPE`: "all vendors or specific?"
- `ENTITY`: "which vendor/material/customer? provide ID"
- `TIME_RANGE`: "which period? this month/quarter/year/last 12 months"
- `METRIC`: "what aspect? payment history / open invoices / spend analysis"
- `DOMAIN`: "which domain? cross-module or specific area?"

Context carry-over: time_range, entity scope, domain decisions persist across turns.
Tested: "show me vendor performance" → detected ambiguity → asked "What aspect of vendor performance?" with options.

`DialogManager.handle_turn(state, query, orchestrator_fn, clarification_reply)`:
- `clarification_reply=False` → analyze for ambiguity, ask question if needed
- `clarification_reply=True` → apply user's answer, re-execute with clarified context

---

#### 10. `self_improver.py` — NEW (Phase 6, ~21KB)
**Location:** `backend/app/core/self_improver.py`

Closed feedback-to-pattern loop. Runs after every orchestrator query.

5 autonomous actions:
1. **Promotion**: patterns with ≥5 consecutive successes → rank boost
2. **Demotion**: patterns with ≥3 failures, ratio <0.4 → buried
3. **Ghost injection**: ad-hoc SQLs seen ≥3 times with good critique scores → named ghost pattern
4. **Heal tracking**: patterns requiring self-heal → logged as gotcha
5. **Feedback integration**: `record_feedback_correction()` from feedback_agent

`get_pattern_health_report()` → healthy/degraded/buried/ghost breakdown per domain.
`run_autonomous_review()` → callable by cron on startup — scans all patterns, auto-buries degraded.

Singleton: `self_improver`

---

## Orchestrator Changes (orchestrator.py)

**Phase 0**: Supervisor gate added — `use_supervisor=True` (default)
**Step 1b**: DDIC auto-discovery fires when schema RAG is empty
**Step 4.5**: Self-critique → self-healer on failure
**Step 5**: Validation error → self-healer → retry
**Step 6**: Execution error → self-healer → retry
**Step 8b**: Memory log → self_improver review_and_improve()

New orchestrator parameters:
- `use_supervisor=True` — disable with False to bypass supervisor gate

---

## Files Created/Modified Today

| File | Change |
|------|--------|
| `backend/app/agents/critique_agent.py` | **NEW** — 7-point SQL validator |
| `backend/app/agents/domain_agents.py` | **NEW** — 7 domain specialists |
| `backend/app/agents/supervisor_agent.py` | **NEW** — 4-way routing decision tree |
| `backend/app/agents/feedback_agent.py` | **NEW** — 5-type correction parser |
| `backend/app/core/memory_layer.py` | **NEW** — 6-store persistent memory |
| `backend/app/core/self_healer.py` | **NEW** — 10-rule SQL repair |
| `backend/app/core/self_improver.py` | **NEW** — closed improvement loop |
| `backend/app/core/schema_auto_discover.py` | **NEW** — 80+ table DDIC mirror |
| `backend/app/core/dialog_manager.py` | **NEW** — multi-turn clarification |
| `backend/app/core/eval_dashboard.py` | **NEW** — eval report generator |
| `backend/app/core/security.py` | UPDATED — `get_where_clauses()` added to SAPAuthContext |
| `backend/app/agents/orchestrator.py` | UPDATED — Phase 0 gate + Steps 1b/4.5/6/8b wired |
| `CLAUDE.md` | **NEW** — comprehensive agent guide (16KB) |
| `Master_Architecture_Overview.md` | UPDATED — Phase status, 9-12 updated |
| `docs/SESSION_APR_04.md` | **NEW** — this session log |

---

## What's Complete

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Schema RAG, SQL RAG, Orchestrator, Mock executor | ✅ Complete |
| Phase 2 | Graph RAG (80+ nodes, AllPaths, Temporal, Meta-Paths, Node2Vec) | ✅ Complete |
| Phase 3 | Real SAP HANA Connection | ⏳ **PENDING (P0)** |
| Phase 4 | Critique Agent, Memory Layer, Domain Agents, Supervisor, Self-Healer | ✅ Complete |
| Phase 5 | DDIC Auto-Discovery, Eval Dashboard, Feedback Agent, Pattern Ranking | ✅ Complete |
| Phase 6 | Dialog Manager, Self-Improver, Autonomous Recovery | ✅ Complete |

---

## Outstanding Items

1. **Phase 3 P0**: Wire real SAP HANA via `hdbcli` — everything else is theater without this
2. CDS view equivalents for S/4HANA Cloud
3. DDIC auto-population script (auto-build graph from DD08L)
4. Steiner tree for multi-terminal queries (4+ table joins)
5. Real exec testing of Node2Vec embedding search in API context

---

*Session log created by Vishnu (AI Agent) ॐ — April 4, 2026*
