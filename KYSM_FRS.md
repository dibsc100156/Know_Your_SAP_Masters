# Functional Requirement Specification
## Know Your SAP Masters (KYSM) — Agentic RAG System for SAP S/4 HANA

**Document ID:** KYSM-FRS-001
**Version:** 1.0
**Date:** 2026-04-16
**Status:** Consolidated — supersedes ad-hoc content in 10 design documents listed in §1.4
**Owner:** KYSM Platform Team

> This FRS consolidates ten architecture / design / migration documents into one canonical
> specification. Where earlier docs disagreed (phase counts, edge counts, vocabulary,
> tool totals, ChromaDB status), this document records the authoritative value and
> lists the superseded claims in Appendix D.

---

## 1. Introduction

### 1.1 Purpose
KYSM is an agentic Retrieval-Augmented-Generation system that translates natural-language
business questions into safe, auditable, role-scoped SAP HANA SQL and executes them
against an SAP S/4 HANA backend. This FRS defines what the system **must do**, the
constraints it operates under, and the interfaces it exposes.

### 1.2 Scope
KYSM covers read-only master-data and transactional querying across 18 SAP modules
(BP, MM, PUR, SD, QM, WM, FI, CO, HR-read-only, Plant-Maint, PP, PS, etc.).
Out of scope for v1.0: write-back (BAPI), real-time streaming changes, non-HANA
backends, and end-user authentication (delegated to the upstream portal).

### 1.3 Definitions, Acronyms, Abbreviations
Full glossary in **Appendix A**. Key terms:

| Term | Meaning |
|------|---------|
| AuthContext | Role-scoped capability object (company codes, plants, denied tables, masked columns) |
| BATNA | Best Alternative To a Negotiated Agreement (agent negotiation fallback) |
| CLV | Capability Level Vector (used by Threat Sentinel to score role elevation) |
| DDIC | SAP Data Dictionary (table and field catalog) |
| FRS | Functional Requirement Specification (this document) |
| MANDT | SAP client identifier; mandatory WHERE filter (`MANDT = '100'`) |
| Meta-Path | Named JOIN template across SAP modules (e.g., `procure_to_pay`) |
| PhaseState | Canonical name for the orchestrator pipeline step (see §3.3) |
| PSI | Pattern Stability Index (Self-Improver metric for promote/demote decisions) |
| Sentinel | Behavioral anomaly detector; see §3.7 |
| Swarm | Multi-agent execution mode with Planner + Domain Agents + Synthesis |
| SwarmDecision | Supervisor routing output: SINGLE / PARALLEL / CROSS_MODULE / FALLBACK |

### 1.4 References (Consolidated Sources)
This FRS is derived from and supersedes:

1. `docs/LEVEL5_ROADMAP.md` — roadmap + M-phase status
2. `docs/GRAPH_RAG_SAP_HANA_TECHNIQUES.md` — graph traversal techniques
3. `docs/HARNESS_ENGINEERING_TRENDS.md` — industry trend mapping
4. `docs/SANDBOX_ARCHITECTURE.md` — 7-layer sandbox
5. `docs/WILLISON_VALIDATION.md` — Willison 14-pattern scorecard
6. `docs/MEMGRAPH_MIGRATION_GUIDE.md` — M1–M11 migration plan
7. `docs/HARNESS_DESIGN_PRINCIPLES.md` — 12 principles
8. `docs/INTER_AGENT_MESSAGE_BUS_DESIGN.md` — Phase 13 bus + negotiation
9. `docs/KYSM_HARNESS_ENGINEERING.md` — implementation summary
10. `docs/MULTI_AGENT_SWARM_ARCHITECTURE.md` — swarm architecture

### 1.5 Document Conventions
- **MUST / SHALL** = mandatory. **SHOULD** = recommended. **MAY** = optional.
- Phase numbering: the orchestrator's runtime phases use `Phase N`; the migration
  track uses `M-phase N`. They are independent numbering systems.
- Canonical phase count: **26 runtime phases** (Phase 0 Meta-Path → Phase 13b
  Negotiation-Commit). Earlier docs citing "8 phases" refer to the legacy v0.9
  pipeline and are deprecated.

---

## 2. Overall Description

### 2.1 Product Perspective
KYSM is a backend service that sits between an upstream chat UI / API client and
SAP S/4 HANA. It is **not** a chatbot; it is an autonomous SQL engineering system.

```
┌──────────────┐   HTTP    ┌──────────┐   Bolt    ┌───────────┐
│  Chat UI /   │◄─────────►│   KYSM   │◄─────────►│ Memgraph  │
│  API client  │           │  FastAPI │           │  (graph)  │
└──────────────┘           │  backend │           └───────────┘
                           │          │   gRPC    ┌───────────┐
                           │          │◄─────────►│  Qdrant   │
                           │          │           │ (vectors) │
                           │          │   AMQP    ┌───────────┐
                           │          │◄─────────►│ RabbitMQ  │
                           │          │           └───────────┘
                           │          │   hdbcli  ┌───────────┐
                           │          │◄─────────►│ SAP HANA  │
                           └──────────┘           └───────────┘
```

### 2.2 Product Functions (High-Level)
F1. Translate natural-language questions into safe, role-scoped SAP HANA SQL.
F2. Validate SQL through a 7-layer sandbox before execution.
F3. Execute approved SQL and return masked, role-appropriate results.
F4. Maintain per-role conversational memory and multi-turn clarification.
F5. Self-critique and self-heal failing SQL autonomously.
F6. Learn from success/failure patterns and promote/demote them.
F7. Detect and block behavioral anomalies (schema enumeration, role escalation).
F8. Support multi-agent swarm execution for cross-module queries.

### 2.3 User Classes
Four built-in SAP roles (extensible via `SAPAuthContext`):

| Role | Scope | Denied Tables | Masked Columns |
|------|-------|---------------|----------------|
| AP_CLERK | US co. 1000/1010 | PA0008, MBEW | LFBK-BANKN, LFA1-STCD1 |
| PROCUREMENT_MANAGER_EU | EU co. 2000/2010 | PA0008 | LFBK-BANKN |
| CFO_GLOBAL | All companies | PA0008, PA0014 | (none — financial access) |
| HR_ADMIN | All companies | EKKO, EKPO, BSEG | (none — HR access) |

### 2.4 Operating Environment
- Python 3.11+ backend (FastAPI + Celery workers)
- Docker Compose for local dev; Kubernetes for production
- Memgraph 2.x (graph), Qdrant 1.7+ (vectors), Redis 7 (cache + pub/sub),
  RabbitMQ 3.12 (task queue), SAP HANA 2.0 SPS07+

### 2.5 Constraints
C1. **Read-only.** No INSERT/UPDATE/DELETE/DDL to HANA in v1.0.
C2. **MANDT mandatory.** Every SQL must include `MANDT = '<client>'`.
C3. **Network isolation.** Python worker processes have no outbound internet.
C4. **No credential in prompt.** LLM receives no HANA connection strings.
C5. **Default-deny security.** Unknown tables/columns are blocked, not allowed.
C6. **Multi-tenant isolation.** All per-tenant state scoped by `TENANT_ID`.

### 2.6 Assumptions and Dependencies
A1. SAP HANA schema is substantially DDIC-compliant.
A2. Upstream portal authenticates the user and forwards a role identifier.
A3. Role definitions are stable across a session (no mid-session role change).
A4. LLM provider (Anthropic Claude) is reachable with ≤ 2 s p50 latency.

---

## 3. Functional Requirements

### FR-1: Five-Pillar RAG Architecture
The system SHALL be structured as five concurrent retrieval pillars plus one hybrid:

| Pillar | Store | Purpose |
|--------|-------|---------|
| 1. Security | `SAPAuthContext` (in-memory + Redis) | Row/table/column scope |
| 2. Orchestrator | — (stateful controller) | Phase routing + memory wiring |
| 3. Schema RAG | Qdrant `sap_schema` | Table/field retrieval |
| 4. SQL Pattern RAG | Qdrant `sql_patterns` | 68+ proven SQL templates |
| 5. Graph RAG | Memgraph (primary) + NetworkX (mirror) | Path discovery, meta-paths |
| 5½. Graph Embeddings | Qdrant `graph_node_embeddings` + `graph_table_context` | Node2Vec + text hybrid |

**FR-1.1** Schema and SQL Pattern collections SHALL be served exclusively by Qdrant.
ChromaDB is deprecated for these paths as of M9. `graph_node_embeddings` and
`graph_table_context` SHALL also reside in Qdrant. (Reconciles conflicting claims
across prior docs — Appendix D.1.)

**FR-1.2** The Graph RAG layer SHALL run in dual mode: Memgraph is authoritative; a
NetworkX mirror is loaded at startup for fast in-process traversal and transparent
fallback when Memgraph is unreachable.

### FR-2: Multi-Agent Swarm
**FR-2.1** The system SHALL provide seven domain agents: `bp`, `mm`, `pur`, `sd`,
`qm`, `wm`, `cross`. Earlier references to "8 domains" are incorrect (Appendix D.2).

**FR-2.2** A Supervisor (`supervisor_agent.py`) SHALL classify every query into one
of four SwarmDecisions:

| SwarmDecision | Trigger | Execution |
|---------------|---------|-----------|
| SINGLE | one agent `confidence ≥ 0.7` | that agent only |
| PARALLEL | ≥2 domain signals + complexity keywords | agents via `ThreadPoolExecutor` |
| CROSS_MODULE | ≥2 entity types or bridge keywords | standard orchestrator + full Graph RAG |
| FALLBACK | no agent `≥ 0.4` | standard orchestrator |

`ESCALATE` is **not** a valid SwarmDecision (Appendix D.3).

**FR-2.3** A Planner agent SHALL decompose CROSS_MODULE queries into a DAG of
sub-queries; a Synthesis agent SHALL merge sub-query results into a single answer.

**FR-2.4** Tool specificity SHALL follow the 1.5 : 1 ratio (1.5× context
allocation for agent state, 1.0× for tool registry) per the Agent-as-a-Graph
principle.

### FR-3: Orchestration Pipeline (Canonical 26 Phases)
Every query SHALL flow through these phases in order. Phases may short-circuit on
fast-path match but SHALL NOT be skipped selectively by the LLM.

| Phase | Name | Purpose |
|-------|------|---------|
| 0 | Meta-Path Match | Fast-path template lookup |
| 1 | Schema RAG | Qdrant table retrieval |
| 1b | DDIC Auto-Discover | Fallback when Phase 1 empty |
| 1.5 | Graph Embedding Search | Node2Vec + text hybrid |
| 1.75 | QM Semantic Search | QM-specific semantic path |
| 2 | SQL Pattern RAG | Proven template retrieval |
| 2b | Temporal Detection | Date / fiscal-Q detection |
| 2c | Temporal Analysis Engine | Filter construction |
| 2d | Negotiation Briefing | Pre-swarm context pack |
| 3 | Graph RAG | AllPathsExplorer / Steiner tree |
| 4 | SQL Assembly | Inject AuthContext + filters |
| 4.5 | Self-Critique | 7-point gate (score ≥ 0.7) |
| 5 | SQL Validation | DML/MANDT/AuthContext gate |
| 5.5 | Dry-Run Harness | `SELECT COUNT(*) FROM (…)` trial |
| 6 | Execution | Route to HANA via proxy |
| 6a | Self-Heal Retry | 10-rule repair loop |
| 6b | Result Fetch | Stream or page rows |
| 7 | Result Masking | AuthContext column redaction |
| 8 | Synthesis | Natural-language answer |
| 8b | Memory Log | Query + pattern + gotcha persistence |
| 9 | Self-Improver Review | Promote / demote / ghost-inject |
| 10 | File-Based Handoff | Context isolation for next turn |
| 11 | Trajectory Log | Per-query replay record |
| 12 | Quality Metrics Eval | Critique + masking + heal stats |
| 12b | Meta-Harness Loop | Offline retraining hooks |
| 13 | Agent Bus Publish | Broadcast to swarm bus (if swarm) |
| 13b | Negotiation-Commit | Final commit after agent negotiation |

**FR-3.1** Phase 4.5 Self-Critique SHALL apply the 7-point checklist:
(1) SELECT-only, (2) MANDT present, (3) AuthContext filters applied, (4) no
Cartesian product, (5) LIMIT/max_rows guard, (6) JOIN keys exist in both tables,
(7) date filter range is reasonable.

**FR-3.2** Phase 6a Self-Healer SHALL handle 10 error codes with 6 heal
strategies: `MANDT_MISSING`, `CARTESIAN_PRODUCT`, `DIVISION_BY_ZERO`,
`TABLE_NOT_FOUND`, `INVALID_COLUMN`, `SYNTAX_ERROR`, `SUBQUERY_JOIN_ERROR`,
`SAP_AUTH_BLOCK`, `EMPTY_RESULT`, `ADD_NVL`.

### FR-4: Self-Critique / Self-Heal / Self-Improve
**FR-4.1** Every generated SQL SHALL be scored by `critique_agent.critique()`
before validation. Score < 0.7 triggers `self_healer.heal()`; re-score required.

**FR-4.2** `self_improver` SHALL run after every query and:
- Promote patterns with ≥5 consecutive successes
- Demote patterns with ≥3 failures and success ratio < 0.4
- Ghost-inject ad-hoc SQLs seen ≥3 times with good critique scores
- Log heal-dependent patterns as gotchas

**FR-4.3** Self-Reflective RAG (re-query after failed critique) is distinct from
Self-Healing SQL (rule-based repair). Both SHALL be available; docs conflating
them are incorrect (Appendix D.4).

### FR-5: Security & AuthContext
**FR-5.1** `SAPAuthContext` SHALL govern every SQL execution with:
- `allowed_company_codes`, `allowed_plants`, `allowed_purchasing_orgs` (row scope)
- `denied_tables` (table denial, default-deny)
- `masked_fields` (column redaction, post-execution)
- `get_where_clauses()` (per-table WHERE injection)

**FR-5.2** Role escalation mid-session is forbidden. A new role SHALL require a
new session.

**FR-5.3** The AuthContext gate is a **hard block** at Layer 4 (§FR-6). MANDT
presence is a **hard block** at Layer 3 — not a soft warning (reconciles
SANDBOX_ARCHITECTURE vs CLAUDE.md; Appendix D.5).

### FR-6: 7-Layer Sandbox
Every SQL SHALL traverse all seven layers. Execution order is **bottom-up**
(1 → 7); the diagram presents them top-down for readability.

| Layer | Name | Gate Type | Action on Fail |
|-------|------|-----------|----------------|
| 1 | Proxy Pattern (credential isolation) | structural | request rejected before HANA |
| 2 | Dry-Run Harness | validation trial | Self-Healer invoked |
| 3 | SQL Permission Guard (read-only + MANDT) | hard block | PermissionError |
| 4 | Table-Level AuthContext | hard block | AuthorizationError + Sentinel flag |
| 5 | Result Masking | post-exec filter | columns rewritten to `***RESTRICTED***` |
| 6 | Threat Sentinel | behavioral | AuthContext dynamically tightened |
| 7 | Network Isolation | environmental (no egress) | TCP-level reject |

**FR-6.1** Layer 7 enforcement SHALL be Kubernetes `NetworkPolicy` (production)
or Docker `--network=none` equivalent (dev). Application-level egress blocking
is insufficient.

### FR-7: Threat Sentinel
**FR-7.1** Sentinel SHALL run six behavioral engines:
`CROSS_MODULE_ESCALATION`, `SCHEMA_ENUMERATION`, `TEMPORAL_INFERENCE`,
`DENIED_TABLE_PROBE`, `DATA_EXFILTRATION`, `ROLE_IMPERSONATION`.

**FR-7.2** Sentinel SHALL support three modes: `DISABLED`, `AUDIT`, `ENFORCING`.
In `ENFORCING`, the Sentinel MAY dynamically add tables to `denied_tables` and
fields to `masked_fields` mid-session without restart.

### FR-8: Inter-Agent Message Bus & Negotiation (Phase 13)
**FR-8.1** The message bus SHALL use Redis pub/sub for low-latency signals and
Redis streams for durable, replayable messages.

**FR-8.2** Six message types SHALL be supported:
`QUERY`, `RESPONSE`, `ASSERTION`, `CHALLENGE`, `NEGOTIATE`, `COMMIT`.

**FR-8.3** NegotiationState canonical names are
`ASSERTING → CHALLENGING → NEGOTIATING → COMMITTED`. The
`PROPOSING/COUNTERING/ACCEPTING` vocabulary from INTER_AGENT_MESSAGE_BUS_DESIGN
is deprecated (Appendix D.6).

**FR-8.4** Six resolution strategies SHALL be available:
`AVERAGE`, `MAJORITY_VOTE`, `HIGHEST_AUTHORITY`, `DOMAIN_SPECIFIC_OVERRIDE`,
`BATNA_FALLBACK`, `PLANNER_ARBITRATION`. `AVERAGE` is **not** the default;
`DOMAIN_SPECIFIC_OVERRIDE` is the default for numeric cross-module conflicts.

**FR-8.5** Agent authority weights: Planner = 8, Synthesis = 6, Domain
Specialists = 7, `cross_agent` = 5. `cross_agent` SHALL NOT outrank specialists
on specialist-owned data.

### FR-9: Graph RAG Techniques
**FR-9.1** The system SHALL implement:
- BFS shortest-path
- All-simple-paths (max depth 5, scored for 1:N / bridge bonuses)
- Meta-path templates (14 templates: `procure_to_pay`, `order_to_cash`, etc.)
- Steiner-tree minimum-connection across ≥3 entity tables
- TemporalGraphRAG with fiscal-year / fiscal-period / key-date filters
- Node2Vec 64-dim embeddings + structural role classification
  (hub / bridge / authority / spoke)

**FR-9.2** CQL / SQLScript code samples in any doc SHALL be executable as-is;
stubs returning constant `True` are disallowed in reference material.

**FR-9.3** Temporal validity SHALL be computed from real DDIC fields (e.g.
`BEGDA/ENDDA`, `DATAB/DATBI`) per table — not from a fabricated `LFA1.DATAB`.

### FR-10: Memgraph + NetworkX Dual-Mode
**FR-10.1** Authoritative graph state: **114 tables, 137 directed edges** (151
with bidirectional expansion), **97 cross-module bridges**. Earlier docs citing
47 / 104 edges are stale (Appendix D.7).

**FR-10.2** `init_schema.cql` is the single source of truth; the adapter SHALL
parse it at startup and build both the Memgraph store and the NetworkX mirror
in a single pass.

**FR-10.3** If Memgraph is unreachable, the system SHALL log a `[STARTUP]`
warning and fall back to NetworkX transparently. Queries MUST NOT fail.

### FR-11: Qdrant Vector Store
**FR-11.1** Four collections SHALL be maintained:
`sap_schema`, `sql_patterns`, `graph_node_embeddings`, `graph_table_context`.

**FR-11.2** Embedding dimensions: 384 (schema/patterns via
`all-MiniLM-L6-v2`), 64 (Node2Vec), 768 (graph_table_context via
`all-mpnet-base-v2`).

### FR-12: Persistent Memory (Six Stores)
Location: `~/.openclaw/workspace/memory/sap_sessions/`

| Store | File | Purpose |
|-------|------|---------|
| query_history | `query_history.jsonl` | per-query audit trail |
| pattern_success | `pattern_success.json` | promoted patterns |
| pattern_failures | `pattern_failures.json` | demoted patterns |
| schema_discoveries | `schema_discoveries.json` | DDIC fallback hits |
| gotchas | `gotchas.json` | edge-case ledger |
| user_preferences | `user_preferences.json` | per-role format / max_rows / language |

**FR-12.1** All memory writes SHALL be tenant-scoped: `{tenant_id}/{role}/...`.

### FR-13: Dialog Manager
**FR-13.1** Five clarification types SHALL be supported: `SCOPE`, `ENTITY`,
`TIME_RANGE`, `METRIC`, `DOMAIN`.

**FR-13.2** Session state SHALL persist to
`dialog_sessions/<session_id>.json` and carry over time, entity, and domain
decisions across turns.

### FR-14: Observability
**FR-14.1** Every query SHALL produce a Trajectory Log entry capturing:
query text, role, SwarmDecision, phases entered, critique score, heal count,
validation verdict, rows returned, latency per phase.

**FR-14.2** The Eval Dashboard SHALL expose: overall success rate,
per-domain / per-role breakdown, weekly trends, heal-frequency, and
pattern-health histogram.

**FR-14.3** The Meta-Harness Loop (Phase 12b) SHALL run nightly to regenerate
pattern rankings and schedule offline retraining datasets.

---

## 4. Non-Functional Requirements

### 4.1 Performance
| Metric | Target |
|--------|--------|
| p50 end-to-end latency (cached pattern) | ≤ 180 ms |
| p95 end-to-end latency (full pipeline) | ≤ 300 ms @ concurrency 10 |
| Memgraph path query (depth ≤ 3) | ≤ 40 ms |
| Qdrant top-K (K=5) | ≤ 25 ms |
| Self-heal retry budget | ≤ 2 retries per query |

### 4.2 Scalability
- KEDA HPA SHALL scale Celery workers based on RabbitMQ queue depth
  (min = 2, max = 20 replicas, cooldown = 120 s).
- Horizontal scale of FastAPI frontend behind a load-balanced K8s Service.
- Memgraph and Qdrant run as StatefulSets with PDBs (`minAvailable = 1`).

### 4.3 Availability
- Target 99.5 % monthly (excluding SAP HANA downtime).
- Graceful degradation: if Memgraph down → NetworkX mirror serves; if Qdrant
  down → DDIC auto-discover serves Schema RAG path.

### 4.4 Security
- Default-deny AuthContext (§FR-5, §FR-6).
- No outbound internet from worker pods (§FR-6 Layer 7).
- Secrets via Kubernetes `Secret` + `ExternalSecrets` operator.
- Threat Sentinel in `ENFORCING` mode in production.

### 4.5 Multi-Tenancy
- Every object (memory, dialog session, vector namespace, graph property)
  tagged with `TENANT_ID`.
- Cross-tenant reads SHALL fail closed.

### 4.6 Auditability
- 100 % of executed SQL SHALL be logged with user role, AuthContext snapshot,
  masked-column list, and row count.
- Trajectory Log retention ≥ 90 days.

---

## 5. External Interface Requirements

### 5.1 API
**Endpoint:** `POST /api/v1/chat/master-data`

**Request:**
```json
{
  "tenant_id": "string",
  "role": "AP_CLERK | PROCUREMENT_MANAGER_EU | CFO_GLOBAL | HR_ADMIN",
  "session_id": "uuid",
  "query": "string",
  "domain_hint": "business_partner | material | purchasing | ... | null",
  "verbose": false
}
```

**Response:**
```json
{
  "answer": "string",
  "sql_executed": "string",
  "critique_score": 0.0,
  "rows": 0,
  "columns_masked": ["LFBK-BANKN", "..."],
  "trajectory_id": "uuid",
  "latency_ms": 0
}
```

### 5.2 Internal Interfaces
- **Memgraph:** Bolt protocol on `bolt://memgraph:7687`
- **Qdrant:** gRPC on `qdrant:6334` (REST on `:6333` for admin)
- **Redis:** `redis://redis:6379/0` (cache), `/1` (pub/sub), `/2` (streams)
- **RabbitMQ:** `amqp://rabbitmq:5672`
- **SAP HANA:** `hdbcli` Python driver, TLS required

### 5.3 Worker Interface
Celery tasks (from `app.workers.orchestrator_tasks`):
`run_agent_loop_task`, `self_improver_review_task`,
`dialog_session_cleanup_task`, `memgraph_health_check_task`.
All use `@shared_task`; `celery_app_instance` imported lazily inside
`get_task_result()` to avoid circular imports.

---

## 6. Infrastructure Requirements

### 6.1 Local / Dev
`docker-compose.memgraph.yml` SHALL bring up the full stack:
FastAPI + 2 Celery workers + Memgraph + Qdrant + Redis + RabbitMQ.

### 6.2 Production (Kubernetes)
Directory `k8s/` SHALL contain:
- Helm-style templates for every service
- Kustomize overlays: `dev`, `staging`, `prod`
- `HorizontalPodAutoscaler` for FastAPI (CPU-based)
- `KEDA ScaledObject` for Celery workers (queue-depth-based)
- `NetworkPolicy` implementing §FR-6 Layer 7
- `PodDisruptionBudget` for all StatefulSets
- `RBAC` roles scoped to namespace

### 6.3 CI/CD
- Pre-merge: unit tests + critique-agent golden set + schema parse check
- Pre-deploy: `init_schema.cql` parse dry-run, Qdrant collection diff

---

## 7. Compliance Alignment

### 7.1 Simon Willison 14-Pattern Scorecard
Current: **11 / 14 ✅, 3 / 14 ⚠️**. (The earlier 12/14 scorecard was based on
optimistic interpretation of Pattern 6 — see Appendix D.8.)

| # | Pattern | Status |
|---|---------|--------|
| 1 | Validate untrusted input | ✅ |
| 2 | Allow-lists over deny-lists | ✅ |
| 3 | Sandbox dangerous operations | ✅ |
| 4 | Least privilege | ✅ |
| 5 | Defense in depth | ✅ |
| 6 | Red/Green TDD for prompts | ⚠️ (golden set exists, not gated in CI) |
| 7 | Observability | ✅ |
| 8 | Rate limiting | ⚠️ (per-tenant limits pending) |
| 9 | Secrets out of prompts | ✅ |
| 10 | Audit logs | ✅ |
| 11 | Deterministic replays | ✅ (Trajectory Log) |
| 12 | Human-in-the-loop escalation | ⚠️ (alerting wired, UI handoff pending) |
| 13 | Capability-based tool access | ✅ |
| 14 | Memory isolation | ✅ |

### 7.2 Harness Engineering Principles (12)
Covered by §FR-2 through §FR-4: Generator/Evaluator/Planner separation (FR-2,
FR-4), phase gates (FR-3), context budgeting (FR-2.4), scoped tool sets
(FR-2.2), Karpathy March-of-Nines reliability target (FR-4.2).

---

## 8. Pending / Future Requirements

| ID | Priority | Description | Target |
|----|----------|-------------|--------|
| P0-HANA | P0 | Switch Phase 6 executor from mock to real hdbcli pool | 2026-05 |
| P1-BAPI | P1 | Write-back via BAPI for select masters (LFA1, MARA) | 2026-Q3 |
| P2-BENCH | P2 | Wire eval benchmark into nightly CI | 2026-05 |
| P3-LOAD | P3 | 500 QPS load test sign-off with KEDA autoscale | 2026-06 |
| M7-POOL | P1 | hdbcli connection-pool sizing study (currently 10) | 2026-05 |
| W-CI-GATE | P1 | Willison Pattern 6 golden set as merge gate | 2026-05 |
| W-HITL | P2 | Human-in-the-loop escalation UI (Willison Pattern 12) | 2026-Q3 |
| R-RATELIMIT | P1 | Per-tenant rate limiting (Willison Pattern 8) | 2026-05 |

---

## 9. Appendices

### Appendix A — Glossary
*(See §1.3 for primary terms. Extended entries below.)*

- **AllPathsExplorer** — `graph_store` helper enumerating all simple paths
  between two tables up to a max depth, with path scoring.
- **Ghost Pattern** — an ad-hoc SQL that the Self-Improver has seen ≥3 times
  with good critique scores and has promoted to a named (but unpublished)
  pattern.
- **Meta-Harness Loop** — Phase 12b offline retraining hook.
- **Steiner Tree** — minimum-connection subtree across ≥3 entity tables; used
  when a query references three or more modules.

### Appendix B — Canonical DDIC Table Catalog
114 tables across 18 modules. Full list maintained in
`docker/memgraph/init_schema.cql` (the single source of truth). Notable entries:

| Module | Key tables |
|--------|-----------|
| BP / Vendor | LFA1, LFB1, LFBK, LFM1, KNA1, KNB1 |
| Material | MARA, MARC, MARD, MBEW, MVKE |
| Purchasing | EKKO, EKPO, EKBE, EKET, EINA, EINE |
| Sales | VBAK, VBAP, VBRK, VBRP, LIKP, LIPS |
| Finance | BSEG, BSIK, BSAK, BKPF, SKAT |
| HR (read-only) | PA0001, PA0002 |
| QM | QALS, QMEL, QPAM |
| WM | LAGP, LTAK, LTAP |

Tables referenced in prior docs that **do not exist** in DDIC: `IHO6`, `IHK6`.
These references are superseded (Appendix D.9).

### Appendix C — Phase Numbering Map
Prior docs used overlapping numbering. Canonical mapping:

| Prior label | Canonical |
|-------------|-----------|
| "Phase 7" (real HANA) | P0-HANA (§8) |
| "M8" (real HANA) | P0-HANA (§8) |
| "Phase 8" legacy | §FR-3 Phase 6 Execution |
| "M7" | P1 hdbcli pool sizing |
| "M9" (HPA) in MEMGRAPH line 29 | M8 KEDA HPA |
| "v0.9 8-phase pipeline" | deprecated |
| v1.0 26-phase pipeline | §FR-3 canonical |

### Appendix D — Reconciled Inconsistencies (from 10-doc review)

| # | Topic | Prior conflict | FRS resolution |
|---|-------|----------------|----------------|
| D.1 | ChromaDB status | "retired" vs "active" | Deprecated for schema/patterns as of M9. Not used in v1.0. |
| D.2 | Domain count | "8 domains" (KYSM_HARNESS) vs 7 (CLAUDE.md) | **7 domains** (FR-2.1). |
| D.3 | SwarmDecision vocab | ESCALATE vs FALLBACK | **FALLBACK** (FR-2.2). |
| D.4 | Self-Heal vs Self-Reflective RAG | conflated in KYSM_HARNESS | Distinct subsystems (FR-4.3). |
| D.5 | MANDT gate severity | soft warning (SANDBOX) vs hard block (CLAUDE) | **Hard block** (FR-5.3). |
| D.6 | NegotiationState names | PROPOSING/COUNTERING/ACCEPTING vs ASSERTING/CHALLENGING/NEGOTIATING | **ASSERTING → CHALLENGING → NEGOTIATING → COMMITTED** (FR-8.3). |
| D.7 | Graph edge count | 47 / 104 / 137 / 151 | **137 directed (151 with bidirectional), 114 nodes, 97 bridges** (FR-10.1). |
| D.8 | Willison score | 12/14 vs 11/14 | **11/14 ✅, 3/14 ⚠️** (§7.1). |
| D.9 | Fictitious tables | IHO6, IHK6 | Removed; Appendix B. |
| D.10 | Tool count | "52 tools per domain" vs "52 tools total" | **52 tools total** across all agents. |
| D.11 | `cross_agent` authority | =10 (outranking specialists) | **=5** (FR-8.5), specialists outrank on their data. |
| D.12 | Phase count | 8 vs 25 vs 26 | **26 runtime phases** (§FR-3). |
| D.13 | Validation blocking | "phase-gated" vs "never blocks" | **Phase-gated hard block** at Layer 3/4 (FR-5.3, FR-6). |
| D.14 | Sentinel modes | missing DISABLED | **DISABLED / AUDIT / ENFORCING** (FR-7.2). |
| D.15 | Default negotiation strategy | AVERAGE | **DOMAIN_SPECIFIC_OVERRIDE** (FR-8.4). |

### Appendix E — Authoring Hygiene Rules (applied here)
- ASCII only; no stray `ॐ`, `谈判`, `绕过`, BOM characters.
- Em-dashes normalized (`—`).
- Video summaries moved to `docs/external_inputs/` (planned).
- Duplicate sections flagged in prior docs SHALL be removed in next edit pass:
  - `MEMGRAPH_MIGRATION_GUIDE.md` — duplicate Qdrant block (lines 295–339 & 404–427)
  - `MULTI_AGENT_SWARM_ARCHITECTURE.md` — duplicate Swarm-vs-Monolith table
  - `MEMGRAPH_MIGRATION_GUIDE.md` — duplicate Rollback Plan

---

*End of FRS v1.0 — supersedes the 10 source documents listed in §1.4 for
purposes of requirements definition. Those documents remain valid as
historical / deep-dive references.*
