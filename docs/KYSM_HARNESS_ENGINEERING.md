# Know Your SAP Masters (KYSM) - Harness Engineering & Agentic AI
## Session: April 12, 2026 | Status: LIVE (Updated April 14, 2026)

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

---

## ✅ New: Agent Harness Video — "What is an AI Agent Harness?" (April 14, 2026)
**Video:** https://youtu.be/GqA18fVWci0 | **Date:** April 14, 2026

### Video Core Thesis
An AI agent has two distinct parts often conflated:
- **Agent** = the LLM brain (reasoning, planning, deciding)
- **Harness** = the infrastructure around it (tool execution, permissions, sandboxing, context management, human-in-the-loop)

> *"The agent is the engine. It does the thinking. But an engine doesn't drive itself. You need the harness — the entire car, the steering, brakes, and dashboard."*

### KYSM Mapping — Every Concept Mapped to Our Architecture

| Video Concept | Video Definition | KYSM Equivalent |
|---|---|---|
| **Agent (LLM brain)** | Reasoning + planning + tool selection + decision-making | Our `orchestrator.py` logic + LLM calls |
| **Harness** | Tool execution + permissions + sandboxing + context + HITL | Our `orchestrator_tools.py` + `security_sentinel.py` |
| **REACT Loop** | Think → Act → Observe → repeat | Our orchestrator `while loop` with tool calls + observation parsing |
| **Claude Code Permission System** | 3 tiers: auto-approve / prompt user / classifier | Our `SAPAuthContext` with `denied_tables` + `masked_fields` + sentinel `ENFORCING` mode |
| **Claude Code Tool Layer** | ~40 tools: file ops, bash, web fetch, git | Our `TOOL_REGISTRY` (52 tools across 8 domains) |
| **Claude Code Context Engine** | ~46,000 lines: token caching, retries, context management | Our `graph_embedding_store.py` + ChromaDB + Qdrant context management |
| **MCP (Model Context Protocol)** | USB-C for AI — JSON-RPC over STDIO/HTTP | Our REST API (`/api/v1/chat/master-data`) acts as MCP-like protocol layer |
| **LangGraph** | Complex multi-step workflows, graph orchestration, 87% on SWE-bench | Our `planner_agent.py` + `synthesis_agent.py` multi-agent swarm |
| **CrewAI** | Agent teams with role-based collaboration | Our `DomainAgentContract` system with role-based agent outputs |
| **Agent-in-Workflow** | Embedding agents inside predefined steps | Our `swarm → planner → domain agent` embedded inside orchestrator |
| **Context Isolation (Sub-agent)** | Delegate token-heavy task to sub-agent, return result only | Our `DomainAgent` parallel execution via ThreadPoolExecutor |

### New Insights from Video (Not Yet in KYSM)

1. **Harness-as-car metaphor** — Agent = engine, Harness = entire car. Our KYSM architecture gets this right conceptually, but we should formalize the **harness boundary** — what lives inside `orchestrator.py` (agent) vs what lives in `orchestrator_tools.py` (harness) is worth explicit documentation.


2. **Claude Code's 46,000-line context engine** — This is the real production harness complexity. Our context management is spread across 3 files. Consider a formal `HarnessContext` class that encapsulates: token tracking, session persistence, retry logic, pruning decisions.

3. **MCP as USB-C for AI** — Our `/api/v1/chat/master-data` endpoint IS a protocol layer (JSON over HTTP). We could formally adopt MCP semantics: `mcp_servers/` directory, `mcp.json` registry, STDIO transport for local tools. This would make our tool bus cross-platform.


4. **3-tier permission model (Claude Code)** — Auto-approve / Prompt user / Classifier. Our sentinel has AUDIT + ENFORCING modes but lacks the auto-approve tier. For read-only queries (non-sensitive tables), we could add `PERMISSION_AUTO_APPROVE` flag that bypasses sentinel entirely.


5. **Agent SDK comparison chart** — Video ranks LangGraph (87% SWE-b), CrewAI (20 lines to start), AutoGen (async-first). We use vanilla ThreadPoolExecutor. Consider evaluating LangGraph for the planner/synthesis layer — it would replace our custom `planner_agent.py` orchestration with a graph-based workflow.


### Recommended KYSM Updates from This Video

**Immediate (could implement today):**
- [ ] Formalize `HarnessContext` class: wrap token tracking + session persistence + retry logic in one place
- [ ] Add `PERMISSION_AUTO_APPROVE` tier for safe read-only table queries (bypass sentinel overhead)
- [ ] Document MCP-like protocol spec for our `/api/v1/chat/master-data` JSON interface

**Medium term:**
- [ ] Evaluate LangGraph to replace custom planner/swarm orchestration (graph-based, tested at 87% SWE-bench)
- [ ] MCP server registry: `mcp_servers/sap_schema_server.py`, `mcp_servers/sql_pattern_server.py` with STDIO transport
- [ ] Session persistence to JSON files (Claude Code pattern) for long-running async queries

**Lower priority:**
- [ ] 46K-line context engine equivalent — would need significant refactor; not urgent while using mock executor

---

## ✅ New: Agent as a Graph — Cole (@stack) (April 14, 2026)
**Video:** https://youtu.be/92rj076mh6o | **Date:** April 14, 2026

### Video Core Problem
When an AI has **thousands of tools**, how does it find the exact right one without paralysis by analysis?

Two flawed historical approaches:
- **Agent-only search:** Knows the toolbox, misses individual tools inside poorly-named boxes
- **Tool-only search:** Finds the specific tool, loses all agent/container context

### The Solution: Agent as a Graph

Represent every agent (toolbox) and every tool (individual function) as **nodes in a knowledge graph**, connected by edges.
- **Tool nodes** = individual functions
- **Agent nodes** = containers/toolboxes
- **Edges** = "tool belongs to agent" relationship

**Result:** The AI sees both the specific tool AND its containing agent in one smooth graph traversal — no more lost-in-the-noise failures.

### The 3-Step Process

1. **Initial Scan** — Broad search for both tools AND agents that seem relevant
2. **Smart Re-Ranking** — Score each candidate: weighted combination of tool specificity + agent context
3. **Graph Traversal** — Follow edges from best tool → navigate to containing agent → pull full agent context

### The Secret Sauce: 1.5:1 Scoring Ratio

> **Agent (toolbox) : Tool = 1.5 : 1.0**

A modest extra emphasis on agent/container context in scoring keeps the big picture in mind while still zeroing in on niche specific tools. This is what makes the search **stable**.

### Results

| Metric | Result |
|---|---|
| Correct agent identification | ~15% improvement |
| Overall search quality | ~14% improvement |
| vs. previous best (MCP0) | **70% → 85%** success rate |
| Consistent across | 8 AI models (Google, Amazon, OpenAI) |

### KYSM Mapping — Tool Registry as a Graph

Our 52-tool `TOOL_REGISTRY` is currently a **flat dictionary** — agents and tools stored without graph structure. "Agent as a Graph" would restructure it:

| Concept | KYSM Application |
|---|---|
| Tool nodes | Each of 52 tools as graph nodes |
| Agent nodes | Domain agents (bp_agent, mm_agent, pur_agent, qm_agent, cross_agent) |
| Intra-domain edges | Tool belongs to agent edges |
| Cross-domain edges | Tools bridging domains (cross_module_agent) |
| Smart re-ranking (1.5:1) | Score = 1.5 × agent_context_relevance + 1.0 × tool_specificity |
| Graph traversal | From matched tool → containing agent → pull full agent context |

**Direct impact on `planner_agent.py`:**
- Current: complexity_score computed as flat weighted sum of 7 dimensions → no graph structure
- Improvement: restructure TOOL_REGISTRY as a graph; graph traversal scores agents and tools jointly; 1.5:1 weighting on agent context over tool specificity
- Benefit: When query matches multiple domain agents, graph structure lets planner navigate context across agent boundaries rather than flat ranking

**Also relevant to MCP (Model Context Protocol):** MCP is the transport layer connecting AI apps to tool servers. Agent-as-a-graph structures the **semantic layer** on top of MCP — MCP gives tools, the graph gives organizational intelligence.

### Recommended KYSM Updates from This Video

**Immediate:**
- [ ] Restructure `TOOL_REGISTRY` as a graph: `graph_tools = {agent: {tools: [], cross_domain_edges: []}}` — add agent-tool ownership edges
- [ ] Update `planner_agent.py` complexity scoring to use 1.5:1 agent:tool weighting — boost agent/container context score in routing decisions

**Medium term:**
- [ ] Build tool-agent graph visualization — expose the graph structure in debug UI so you can see which agents/tools are being considered for each query
- [ ] Add cross-domain edge detection: tools used by multiple agents get higher cross-domain bridging scores

---

## ✅ New: How to Know If Your AI Agents Actually Work — Cole (@stack) (April 14, 2026)
**Video:** https://youtu.be/Kleu3ROhpvY | **Date:** April 14, 2026

### Video Core Thesis
The hardest part of AI agents isn't making them work — it's **knowing whether they actually do**. Traditional testing (unit/integration/E2E) assumes determinism. Agents are probabilistic. Evals = **CI for probabilistic systems**: spectrum scoring, benchmark sets, trend tracking over time.

### Core Framework: Evals ≠ Tests

| Traditional Testing | Agent Evals |
|---|---|
| Binary pass/fail | Spectrum scoring (0.0 → 1.0) |
| Single input | Benchmark set (dozens to hundreds) |
| Snapshot | Trend tracking over time |
| Deterministic | Probabilistic |

> *"Think manufacturing QA — you sample the batch and measure the defect rate over time."*

### 3 Things Evals Need: Benchmark Set + Scoring Functions + Trend Tracking

### The 4 Layers (Outside-In Measurement Order)

1. **Outcome** — Final answer correct, helpful, grounded, complete? Hardest. Subjective → use **LLM as Judge**.
2. **Trajectory** — Right steps, right tools, right parameters, reasonable reasoning chain? An agent getting the right answer in 25 tool calls when 3 would do = trajectory problem.
3. **Component** — Tools/functions deterministic → standard unit tests work fine.
4. **System Monitoring** — Patterns across production usage, not individual failures. Evals + observability overlap here.

### 4 Quality Dimensions

| Dimension | Question | KYSM |
|---|---|---|
| **Effectiveness** | Did it achieve what the user wanted? | 🔴 No formal eval dataset |
| **Efficiency** | Right steps/tokens? (25 calls vs 3 = big difference) | 🟡 `tool_trace` + `execution_time_ms` exist |
| **Robustness** | Holds up under malformed input, API failures, edge cases? | 🟡 Sentinel handles security |
| **Safety & Alignment** | Stays within bounds, refuses appropriately? | 🟢 Sentinel ENFORCING mode |

### Compounding Flywheel

```
Production failure surfaces
  → Annotate as eval case
  → Eval set grows
  → Agent improves
  → New edge cases surface
  → Repeat
```

> *"The eval set becomes a living record of everything your agent has struggled with."*

### KYSM Mapping — Evals Layers

| Eval Layer | What to score | KYSM Implementation | Gap |
|---|---|---|---|
| **Outcome (Layer 1)** | Correct + helpful + grounded + complete | `validation_summary` (swarm agents pass/fail) | 🟡 Partial — no LLM-as-judge on final answer |
| **Trajectory (Layer 2)** | Right tools, right params, right step count | `tool_trace` (which tools, how many) | 🟡 Basic — no structured trajectory scoring against optimal path |
| **Component (Layer 3)** | Deterministic tools (JSON parse, SQL validation) | `sql_executor.py` dry-run validation | ✅ Done — unit-testable |
| **System Monitoring (Layer 4)** | Patterns across production usage | `sentinel_stats` + `execution_time_ms` | 🟡 Partial — no production trend tracking |
| **LLM as Judge** | Human defines criteria, model applies at scale | `critique_gate()` (7-point SQL gate) | 🟡 Implemented as SQL critic — not general answer judge |
| **Eval set compounding** | Production failures → annotated → regression tests | Not implemented | 🔴 No regression test pipeline from production failures |

### Critical Insight: Quality Must Be Designed In

> *"You can only measure what you can see. You can't measure effectiveness if you only see the final answer. You can't measure efficiency if you don't count the steps. You can't diagnose robustness failures if you don't know which API call failed."*

**Most teams:** Build agent → ship it → then ask "how do we test?" ❌
**Right approach:** Design traces + measurement from day one — same as observability and security.

### Recommended KYSM Updates from This Video

**Immediate:**
- [ ] Formalize the 50-query benchmark as a **curated eval dataset with reference outputs** — every query should have a known correct SQL + expected table result
- [ ] Add **trajectory scoring** to `tool_trace`: compare actual steps vs optimal path (optimal = meta-path fast path hit = single step; worst = full orchestrator loop)

**Medium term:**
- [ ] Build **LLM-as-judge** for outcome layer: define rubric for "good SAP master data answer" → run against eval dataset automatically
- [ ] Implement **eval set compounding**: production failures → annotated as eval cases → regression tests grow over time
- [ ] Add **production trend tracking**: token usage, error rates, latency distribution over time (LangSmith or `langfuse`/`phoenix`)
- [ ] Formalize outside-in measurement order: always evaluate Outcome first → drill into Trajectory only when Outcome passes

---

## ✅ New: Langchain, LangGraph, LangSmith Explained — Cole (@stack) (April 14, 2026)
**Video:** https://youtu.be/e-GR3PlEOVU | **Date:** April 14, 2026

### Video Core Thesis
The full Langchain ecosystem = 3 distinct layers solving 3 distinct problems:

```
Langchain  = vocabulary  (building blocks: prompts, chains, tools, RAG)
LangGraph  = control flow (graph structure + shared state)
LangSmith  = visibility  (traces, evaluation, production monitoring)
```

Together they cover the full surface of **production AI systems** — not just API calls.

### KYSM Mapping — All 3 Layers

| Langchain Ecosystem | What it solves | KYSM Implementation | Gap |
|---|---|---|---|
| **Prompt Templates** | Reusable, testable, maintainable prompts injecting context at runtime | `meta_path_library.py` — structured SQL JOIN templates | Not templated at prompt level |
| **Chains** | Linear sequences: output of one step → input of next | Orchestrator phases 0→5 (Schema RAG → SQL Pattern → Graph → Assembly → Critique → Execute) | Linear only |
| **Tools** | Functions LLM can invoke to act in the world | `TOOL_REGISTRY` — 52 tools, 8 domains | OAuth not needed (internal SAP) |
| **RAG** | Vector DB retrieval → inject relevant chunks into context | Schema RAG + SQL Pattern RAG (Qdrant dual-collection) | ✅ Working |
| **LangGraph** | Graph-based orchestration: loops, branching, shared state | `planner_agent` → `domain_agent` → `synthesis_agent` (manual graph) | 🔴 Using custom code — not formal LangGraph |
| **REACT Loop** | Reason → Act → Observe → Repeat | Orchestrator `while loop` + tool execution + observation parsing | ✅ Working |
| **LangSmith Traces** | Every step recorded: prompt, response, tools, docs, reasoning | `tool_trace` + `validation_summary` + `sentinel_stats` (manual) | 🔴 Homebrew — no automatic trace UI |
| **Eval Datasets** | Run system against ground truth, measure accuracy, latency, token usage | Not implemented | 🔴 No eval pipeline |
| **A/B Prompt Comparison** | Measure prompt variant impact on same dataset | Not implemented | 🔴 No framework |

### Critical Insight: We're Building LangGraph + LangSmith From Scratch

LangGraph's core value:
- **Graph structure** makes control flow explicit and auditable
- **Shared state object** — each node reads/writes same state dict
- **Conditional edges** — branching logic is first-class, not buried in if/else
- LangGraph scored **87% on SWE-bench** (software engineering benchmark)

LangSmith's core value:
- **Automatic trace capture** — every step, no manual instrumentation
- **Evaluation pipelines** — run against datasets, measure degradation
- **Production monitoring** — latency, error rates, token burn under real traffic

**Our current approach:** All of this is implemented manually in `orchestrator.py` + `synthesis_agent.py`. It works but is custom, fragile, and not reusable.

### Architecture Decision: Evaluate LangGraph for Planner/Synthesis Layer

**LangGraph vs Custom Planner/Synthesis (current state):**

| Criteria | Custom (today) | LangGraph |
|---|---|---|
| Control flow visibility | ✅ Traceable in orchestrator.py | ✅ Graph visualization |
| Conditional branching | if/else chains | First-class conditional edges |
| State management | Manual dict passing | Built-in shared state object |
| Evaluation harness | Homebrew `validation_summary` | LangSmith automatic |
| SWE-bench score | N/A | 87% (tested at scale) |
| Learning curve | We wrote it — no new learning | New framework to learn |
| Debugging | Breakpoints + print | LangSmith trace replay |

**Recommended evaluation:**
- Build one domain agent (e.g., `BP_AGENT`) in LangGraph as a pilot
- Compare code clarity + debuggability vs current `planner_agent.py`
- If positive: migrate full swarm orchestration to LangGraph
- Use LangSmith for evaluation dataset runs on the 50-query benchmark

### Recommended KYSM Updates from This Video

**Immediate:**
- [ ] Evaluate LangGraph: port `planner_agent.py` routing logic to LangGraph — pilot with single domain agent, assess clarity + debuggability

**Medium term:**
- [ ] Add LangSmith (or open-source alternative: `langfuse` or `phoenix`) for automatic trace capture replacing manual `tool_trace`
- [ ] Build 50-query evaluation dataset formally — run benchmark with measurement: accuracy + latency + token usage
- [ ] A/B prompt comparison: test meta-path SQL templates vs LLM-generated SQL on same queries

---

## ✅ New: RAG vs Long Context — Cole (@stack) (April 14, 2026)
**Video:** https://youtu.be/UabBYexBD4k | **Date:** April 14, 2026

### Video Core Thesis
Context injection for LLMs has two competing paradigms — **RAG** (engineering approach) vs **Long Context** (model-native). Neither is dead. The choice depends on dataset size and reasoning complexity.

| Approach | Mechanism | Best for |
|---|---|---|
| **RAG** | Chunk → embed → vector DB → semantic search → inject top-K | Infinite enterprise data lakes |
| **Long Context** | Dump all docs → attention mechanism finds answer | Bounded datasets, complex global reasoning |

### KYSM Mapping

| Concept | Definition | KYSM Relevance |
|---|---|---|
| **Retrieval Lottery** | Silent failure — relevant doc exists but vector search doesn't retrieve it | Our dual retrieval (Qdrant + Graph) reduces this risk |
| **No-Stack Stack** | Long context's minimal architecture — no DB, no embeddings | If SAP schema fit in context window → RAG overhead disappears |
| **Needle in Haystack** | Model attention degrades in >500K token context; specific facts get lost | Our Schema RAG top-K retrieval is a feature, not a bug |
| **Whole Book Problem** ⚡ | RAG retrieves snippets only — cannot surface gaps *between* documents | **Critical for KYSM** — cross-module absences (vendor in LFA1 but no PO in EKKO) |
| **Re-reading Tax** | Long context re-processes full doc on every query; RAG pays once at index | Prompt caching partially mitigates for static data |

### Critical Insight: Whole Book Problem → KYSM Cross-Module Gap Queries

This is the most important KYSM connection from the video:

**The "Whole Book Problem" in SAP terms:**
- A user asks: *"Which vendors exist in LFA1 but have NEVER created a PO in EKKO?"*
- Pure Schema RAG (Qdrant chunk retrieval): searches for chunks mentioning "vendor" + "purchase order" → retrieves snippets from LFA1 + EKKO tables
- **RAG CANNOT retrieve the absence of a relationship** — it can't surface the gap between LFA1 and EKKO
- Only a full SQL `LEFT JOIN ... WHERE EKKO.LIFNR IS NULL` sees that gap

**This is exactly why our Pillar 3 (Graph RAG) + Pillar 5 (Meta-Path) exist** — they operate at the **JOIN level**, not the document/chunk level. Our Meta-Path library encodes 14 pre-assembled JOIN templates (vendor → PO, material → inspection lot, etc.) that can detect relational *absences*, not just semantic co-occurrence.

### Architecture Decision: RAG + Graph > Pure RAG or Pure Long Context

For SAP enterprise data, pure Long Context fails immediately because:
- SAP S/4 HANA has **thousands of tables** — far exceeding any context window
- Cross-module reasoning requires JOINs, not document similarity
- Relational absence (vendor with no PO) = structural gap RAG cannot surface

**Our hybrid is correct:**
```
Long Context (fine for single-table semantic lookup)
    ↓ fallback when needed
RAG (Schema RAG — table metadata retrieval)
    ↓ cross-module / multi-hop
Graph RAG (AllPathsExplorer — ranked JOIN paths)
    ↓ pre-assembled JOIN template
Meta-Path Library (14 fast-path templates, detects relational absences)
```

### Recommended KYSM Updates from This Video

**Immediate:**
- [ ] Document in architecture docs that Graph RAG / Meta-Path explicitly solves the "Whole Book Problem" — relational absence queries (LEFT JOIN ... IS NULL) cannot be solved by RAG alone
- [ ] Add a "RAG vs Long Context" decision note in CLAUDE.md — when query detects absence/completeness intent, skip Schema RAG and go directly to Meta-Path/Graph RAG

**Medium term:**
- [ ] Implement "absence detection" meta-path: if query pattern = "vendor with no PO" / "material never purchased" / "customer never billed" → trigger `LEFT JOIN ... IS NULL` path in Meta-Path library (not semantic search)
- [ ] Long Context evaluation: if SAP schema can be represented as structured markdown in <200K tokens, consider a "full schema dump" for bounded single-domain queries (绕过 RAG retrieval lottery for simple cases)

---

## ✅ New: 11 RAG Strategies Video — Cole (@stack) (April 14, 2026)
**Video:** https://youtu.be/tLMViADvSNE | **Date:** April 14, 2026

### Video Core Thesis
Optimal RAG systems combine **3–5 strategies** — not just one. Pure semantic search is insufficient for production accuracy.

**Cole's recommended tactical stack:** `reranking + agentic RAG + context-aware chunking (dockling)`

### KYSM Mapping — All 11 RAG Strategies → Our 5-Pillar Architecture

| # | Strategy | What it is | KYSM Equivalent | Implementation |
|---|---|---|---|---|
| 1 | **Reranking** | Pull large candidate pool → cross-encoder reranker → top-K to LLM | Pillar 1.5 (Graph Embedding Search) + Pillar 2 (Schema RAG) | We do dual-retrieval: Qdrant schema hit → Graph structural scoring → re-ranked by composite score |
| 2 | **Agentic RAG** | Agent chooses search strategy per query (semantic vs full doc) | Phase 0 Meta-Path Match + Orchestrator routing | `meta_path_library.match()` = fast-path (structured JOIN) vs orchestrator full search |
| 3 | **Knowledge Graphs** | Vector + graph DB for entity relationship traversal | Pillar 3 (Graph RAG) + Pillar 5 (Meta-Path) | `AllPathsExplorer` + `TemporalGraphRAG` + Memgraph (Phase M1 complete) |
| 4 | **Contextual Retrieval** | LLM prepends document-fit context to every chunk | Pillar 1 (Schema RAG) — chunk enrichment | Not yet implemented — chunk prepending in Qdrant indexing |
| 5 | **Query Expansion** | LLM rewrites query before search for precision | Phase 0 Meta-Path | `meta_path_library.match()` expands keywords → structured SQL patterns |
| 6 | **Multi-Query RAG** | LLM generates query variants → parallel search → merge | Pillar 1.5 (Graph Embedding Search) | Graph search runs structural + text in parallel; results fused |
| 7 | **Context-Aware Chunking** | Embedding detects natural document boundaries | Schema RAG chunking in Qdrant | NOT YET — current chunking is naive (every N chars); should use `dockling` |
| 8 | **Late Chunking** | Embed full doc → chunk token embeddings (preserves context) | Not implemented | Most complex; low priority |
| 9 | **Hierarchical RAG** | Small chunk search → parent doc retrieval via metadata | Pillar 5 (Meta-Path) — parent/child table relationships | `graph_store.py` table hierarchy: LFA1 → LFB1 → LFBK → ADRC (parent→child→grandchild) |
| 10 | **Self-Reflective RAG** | Grade retrieved chunks → retry with refined query if score low | Phase 6 (Self-Healer) + Phase 5.5 (Validation Harness) | `critique_gate()` grades SQL → dry-run → heal if fails → re-test; `validation_summary` tracks retry |
| 11 | **Fine-Tuned Embeddings** | Domain-specific embedding model (legal, medical, sentiment) | Schema RAG embeddings | Currently using `all-MiniLM-L6-v2`; NOT fine-tuned for SAP DDIC terminology |

### Gaps Identified (Not Yet in KYSM)

1. **Contextual Retrieval not implemented** — chunk enrichment would improve Schema RAG accuracy significantly. Anthropic has strong evidence here. Would require a post-processing step after Qdrant upsert: prepend LLM-generated document context.


2. **Context-Aware Chunking not implemented** — current Qdrant indexing uses naive character-split chunks. `dockling` library would find natural SAP DDIC boundaries (segment fields, table groups, domain groupings).

3. **Fine-Tuned Embeddings not implemented** — `all-MiniLM-L6-v2` is generic. A SAP DDIC-specific embedding model fine-tuned on SAP terminology would boost schema lookup accuracy by 5–10%.

4. **Hierarchical RAG metadata in Qdrant** — currently storing table metadata but not parent-document references. Could store at document level (e.g., module-level umbrella) and link to child table chunks.

### Recommended KYSM Updates from This Video
**Immediate:**
- [ ] Switch Qdrant chunking from naive char-split to `dockling` context-aware chunking for Schema RAG
- [ ] Add `Contextual Retrieval` post-processing step: prepend LLM-generated context to each chunk before Qdrant upsert

**Medium term:**
- [ ] Fine-tune `all-MiniLM-L6-v2` on SAP DDIC terminology (STCD1, LFA1, EKPO, etc.) — or explore `mxbai-embed-large` which is stronger for code/technical domains
- [ ] Add Hierarchical RAG metadata linking: module-level parent doc → child table chunks in Qdrant
- [ ] Implement Self-Reflective RAG retry loop with configurable threshold (currently auto-retries on any failure; should grade and decide)

---

## ✅ New: Why 89% of AI Agents Never Reach Production (April 15, 2026)
**Video:** https://youtu.be/axF-X3nC0OA | **Date:** April 15, 2026

### Video Core Thesis
Teams that ship agents focus on **architecture**, not models or prompts. The biggest trap is betting on a single monolithic vendor (AWS, Azure, OpenAI). A monolith becomes a single point of failure and guarantees obsolescence. The solution is an **open, 4-layer interoperable stack**.

### The 4-Layer Enterprise Agent Stack & KYSM Mapping
1. **Context Layer:** Data connectors, vector indexes, knowledge graphs. *Lock-in Danger:* Context is the biggest lock-in point. Separate context from models.
   - **KYSM Mapping:** Qdrant (Schema/SQL), Memgraph (Graph RAG) — fully decoupled from LLM.
2. **Model Layer:** Shared infrastructure. Multi-model routing is standard. Match model to specific micro-task.
   - **KYSM Mapping:** OpenClaw handles multi-model routing (Opus for synthesis, Haiku for fast routing).
3. **Orchestration Layer:** Coordinates across systems. Orchestration and Context must be tightly coupled.
   - **KYSM Mapping:** Our `planner_agent.py` + `synthesis_agent.py` horizontal swarm orchestration.
4. **Security Layer:** Data isolation, encryption, SSO. Cannot tolerate fragmentation. Built-in by default.
   - **KYSM Mapping:** `security_sentinel.py` + `SAPAuthContext` enforces centralized, granular RBA masking across domains.

**Vertical Experiences:** Sit on top of the 4 layers (e.g., support copilots, engineering tools). Adoption is highest when embedded directly into existing tools (IDE, Slack, SAP).

---

## ✅ New: Agent Orchestration — Copilot & VS Code (April 15, 2026)
**Video:** https://youtu.be/-BhfcPseWFQ | **Date:** April 15, 2026

### Video Core Thesis
Shifting from humans orchestrating chats to **AI agents orchestrating AI agents**. Define an "Orchestrator Agent" that breaks down tasks and delegates to specialized "Sub-Agents" (Planner, Coder, Designer) powered by specific LLMs.

### Crucial Architectural Insights
- **Adversarial Prompting:** Agents want to do everything. You must explicitly tell the Orchestrator: *"Never implement anything yourself. Just delegate."* And tell Sub-Agents: *"Do not let the orchestrator tell you how to do your job. Make your own decisions."*
- **Context Window Isolation (The Hidden Superpower):** A complex task can generate 2,770 lines of code but only consume 10.8K tokens in the main orchestrator. How? Sub-agents operate in isolated context windows and pass only the final output/summary back to the main thread. This prevents "Context Rot".
- **File-based Handoffs:** Passing large plans via chat causes data loss. Planners should save plans to a Markdown/JSON file and pass the file path to child agents.
- **Parallel Execution:** Sub-agents should be sliced and launched simultaneously.

### Recommended KYSM Updates
**Immediate:**
- [ ] Implement **Context Isolation**: Ensure domain agents run in isolated threads (via `ThreadPoolExecutor`) so they don't pollute the main orchestrator's prompt history.
- [ ] Shift from message-based to **File-based State**: When `planner_agent` creates a cross-module execution plan, drop it into a temporary JSON/MD state file rather than passing the raw string into the context window of domain agents.
- [ ] Configure explicit **Multi-Model Routing**: `planner_agent` = Opus/Sonnet for reasoning; `sql_executor` = Codex/Haiku for strict syntax generation.

---

## ✅ New: Harness Engineering: The New Science of AI Agents (April 15, 2026)
**Video:** https://youtu.be/Xxuxg8PcBvc | **Date:** April 15, 2026

### Video Core Thesis
**Same model, same benchmark, 6x performance difference.** Research proves that the orchestration code wrapping an LLM (the harness) now drives more performance variation than the model itself.
> *"Agent = model + harness. If you're not the model, you're the harness."*

We've evolved: Prompt Engineering → Context Engineering → **Harness Engineering**.

### The Operating System Analogy
- **CPU:** Raw LLM (powerful but inert)
- **RAM:** Context window (fast but limited)
- **Disk:** External vector/SQL databases
- **Device Drivers:** Tool integrations (search, bash, APIs)
- **Operating System:** The **Harness** (coordinating what the CPU sees and when)

The harness is everything that isn't model weights: system prompts, tool definitions, orchestration logic, memory management, verification loops, safety guardrails.

### The Breakthrough: Natural Language Harnesses (NLH)
A new framework called **Tingua** separates the harness into 3 explicit layers:
1. **Backend Infrastructure:** Tools runtime.
2. **Charter (Universal Physics):** State persistence, child agent management.
3. **NLH (Natural Language Harness):** Task-specific control logic, failure taxonomies, roles written in structured natural language.

**Why this matters:** Allows for **controlled ablation experiments**. Migrating a native Python harness into an NLH representation jumped performance from 30.4% to 47.2%, dropped runtime by 60%, and collapsed LLM calls from 1,200 to 34. *The representation itself drove the gain.*

### Meta-Harness: AI Optimizing Its Own Harness
Stanford researchers introduced **Meta Harness**. An "agentic proposer" reads raw execution traces of failed runs, diagnoses what broke, and writes a completely new harness topology.
- It was the **only automatically optimized system** on Terminal Bench 2 leaderboards, beating hand-engineered entries.
- **Golden finding:** A harness optimized on one model successfully transferred to five other models, improving all of them. *The reusable asset isn't the model, it's the harness.*

### The Craft of Subtraction
**More structure is not always better.** In ablation studies, adding verifiers and multi-candidate search actively *hurt* performance. The only module that consistently helped was one that narrowed the agent's attempt loop.
> *"Mature harness work looks less like building structure up and more like pruning it down. A craft of subtraction as much as addition."*

### KYSM Parallel — How This Applies to Our Architecture

This video is the **defining theoretical foundation** for what we've been building in KYSM.

1. **The Reusable Asset:** Our 5-Pillar RAG and multi-agent swarm *is* our OS. Even if we swap from Gemini to Claude to MiniMax, our orchestration logic (the harness) is our actual enterprise IP.
2. **File-Backed State:** The video emphasizes moving memory out of the context window and into "path-addressable files." This confirms our plan to prevent context pollution in our `planner_agent` by saving execution plans to files instead of passing them in chat.
3. **Craft of Subtraction:** Our `TOOL_REGISTRY` has 52 tools. We should review if pruning tools could yield better routing accuracy, especially paired with the 1.5:1 Agent-as-a-Graph scoring.
4. **Trace Analysis:** "Meta Harness" relies heavily on reading *raw execution traces* of failures. This proves that our `tool_trace` and `validation_summary` logs are our most valuable assets for future automated optimization.

### Recommended KYSM Updates from This Video

**Immediate:**
- [ ] Review `TOOL_REGISTRY` to see if tools can be pruned or consolidated ("Craft of Subtraction") to improve agent routing accuracy.
- [ ] Shift `planner_agent` state passing from chat history to file-backed state (save execution plans to a temporary file/JSON and pass the path to child agents).

**Medium term:**
- [ ] Build an automated trace-analysis loop: have an LLM periodically review failed `tool_trace` logs to suggest modifications to our orchestration prompts or meta-paths (a basic version of Meta-Harness).

