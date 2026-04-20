---
date: 2026-04-20
tags: [daily, memory, kysm, design-patterns, documentation]
---
# 2026-04-20

## 📝 Activity Log

### Phase L5 Completed Yesterday — Complexity Router LIVE ✅
All 8 patches applied to `orchestrator.py`. API wired to return `routing_tier` + `routing_score` in `ChatResponse`. Commits `fd038f1` + `f049558`.

### Phase 18 Exploration & Discovery — Wired into Orchestrator ✅ (Apr 20 midday)
**ExplorationEngine** (`exploration_engine.py`) — Phase 18 entry point. 3-probe parallel search:
- **PROBE_A**: DDIC field → table mapping (tax IDs, dates, amounts, status codes)
- **PROBE_B**: Graph FK neighbor expansion from anchor tables (NetworkX 1-hop)
- **PROBE_C**: Semantic DDIC search via Qdrant + keyword fallback

**HierarchicalDecomposer** (`hierarchical_decomposer.py`) — Phase 18b. Decomposes cross-module queries into agent-assigned sub-tasks with JOIN keys.

**Bugs fixed during wiring:**
1. `_probe_graph_expansion`: `domain` not passed as parameter → added `domain: str`, updated call site
2. `_probe_ddic_field_match`: broken `any()` expression with mixed dict/dataclass DDICTable → rewritten with `_field_names()` + `_has_field()` helpers
3. `DecompositionPlan` dataclass: `cross_module_join` had no default, came after required `synthesis_instructions` → reordered to put all required fields first

**Trigger condition:** `not meta_path_used AND (no tables found OR schema_rag_confidence < 0.60)`
**Budget:** 3 probes/query max, cached per `(query, domain)` → `ExplorationBudget`
**Orchestrator:** Phase 18 block inserted before Step 1.5 (Graph Enhanced Schema Discovery)
**Result merged:** exploration candidates appended to `tables_involved` before Step 1.5

**Smoke test:** 7/7 PASS ✅

### Phase 19: Agent-as-Tool Dynamic Override — WIRED ✅ (Apr 20 afternoon)
**AgentToolMode** (`agent_tool_mode.py` — 21KB) — new standalone module.

**Trigger conditions (any one activates tool mode):**
1. Sentinel verdict `recommended_action` in `("tighten", "block")`
2. `SessionThreatProfile.tightness_level >= 3`
3. CIBA store has a PENDING request for this session

**What changes in tool mode:**
- `DomainAgent.run()` → skips `_synthesize()` — returns raw masked data only
- No self-critique / revision loops in planner or synthesis agent
- Swarm uses direct pass-through from sub-agents
- CIBA queries blocked until approval received
- 5-minute TTL auto-expiry per activation

**ToolModeSession:** tracks active/TTL/reason/depth per session.

**Wired into:**
- `orchestrator.py` — Phase 19 block evaluates triggers after Sentinel verdict, before SWARM GATE
- `swarm/__init__.py` — `run_swarm(agent_tool_mode)` parameter added, passes to `planner.execute()`
- `planner_agent.py` — `PlannerAgent.execute(agent_tool_mode)` parameter added, calls `agent_tool_mode.wrap_agent_execution()` instead of `agent.run()` directly

**execute_as_tool():** key Phase 19 primitive — calls 5-step direct execution (table resolve → SQL resolve → auth inject → execute → mask), SKIPS synthesis, returns raw data with `tool_mode=True` tag.

**Smoke test:** 10/10 PASS ✅ (sentinel verdict triggers ✅ | activate/deactivate ✅ | singleton ✅ | orchestrator/swarm/planner wiring ✅)

**Bug fixed during wiring:**
- orchestrator Phase 19 block indentation was inside the open `return {` dict literal → restructured to insert AFTER the `ciba_pending` return dict closes and BEFORE the SWARM GATE separator comment


### Phase 20: Resource-Aware Cost Router — WIRED (Apr 20 late afternoon)
**RouterCostTracker** (`router_cost_tracker.py` -- 19KB) -- new standalone module.

**Key insight (Pattern 15 -- Resource-Aware):** "Router overhead for TRIVIAL could exceed query cost itself." Phase 20 measures routing overhead and bypasses the complexity router when it exceeds per-tier budgets.

**Per-tier budgets (milliseconds):**
- TRIVIAL: 5ms -- near-instant, router overhead dominates
- SIMPLE: 15ms -- fast path, Schema RAG already skipped
- COMPLEX: 50ms -- full routing work
- EXPERT: never bypass -- swarm cost is 100ms+, cost justified

**Default fallback decisions:** When router is bypassed, pre-computed DEFAULT_DECISIONS for each tier skip graph, schema, critique steps. TRIVIAL gets enabled_tools=["sql_pattern_lookup", "sql_execute"] only.

**RouterCostTracker** wraps ComplexityRouter with:
1. **Fast tier pre-estimation** -- _fast_estimate_tier() uses keyword counting (~0.1ms), estimates tier BEFORE spending budget on full routing
2. **Adaptive budgeting** -- auto-adjusts per-tier budget based on p75 of recent latencies (machine speed adaptive)
3. **Budget enforcement** -- if routing > budget, returns default decision (bypassed) instead of real routing
4. **LRU decision cache** -- 60-second TTL, query-key deduplication to avoid redundant routing

**Wired into:** `orchestrator.py` -- route_with_cost() replaces get_routing_decision(), returns cost_stats in response dict.

**Smoke test:** 12/12 PASS (import | budgets | defaults | fast estimation | budget enforcement | adaptive budget | cache | orchestrator wiring)

**Files created:**
- `app/core/router_cost_tracker.py` -- 19KB, full implementation

**Files modified:**
- `app/agents/orchestrator.py` -- route_with_cost import + call site + cost_stats in response
- `docs/LEVEL5_ROADMAP.md` -- Phase 20 status updated to WIRED
- `docs/SESSION_APR_20.md` -- this entry


### Agentic Design Patterns Video Research 🆕
Analyzed 3 YouTube videos. Created comprehensive `docs/AGENTIC_DESIGN_PATTERNS_KYSM.md` (22,559 bytes).

**Videos covered:**
| Video | Title | Channel | Views | Key Patterns |
|---|---|---|---|---|
| V1 | 20 Agentic AI Design Patterns | Mark Kashef | 122K | All 20 (Google engineer book) |
| V2 | AI Agent Design Patterns Part 1 | Google Cloud / Annie Wang | 329K | Single/Sequential/Parallel Agent |
| V3 | 3 Advanced AI Agent Design Patterns Part 2 | Google Cloud / Annie Wang | 63K | Loop/Review&Critique, Coordinator, Agent-as-Tool |

**KYSM Coverage Scorecard:**
- ✅ LIVE: 9/23 patterns (Routing, Parallelization, Multi-Agent, HITL, RAG, Comms, etc.)
- 🟡 Partial: 8/23 patterns (Prompt Chaining, Memory, Tool Use, Planning, etc.)
- 🔴 MISSING: 6/23 patterns (Resource-Aware P15, CoT/ToT P16, Prioritization P19, Exploration P20, Agent-as-Tool A3)

### Documentation Updated ✅
**`LEVEL5_ROADMAP.md`** updated:
- Added April 20 commit entry (`VIDEO20`)
- Phases 18–24 added to execution roadmap table
- Priority build order restructured: Phase 18 (Exploration) moved to P0 next
- Added reference entry for `AGENTIC_DESIGN_PATTERNS_KYSM.md`
- Phase 17 re-added to table (was accidentally replaced)

**`docs/AGENTIC_DESIGN_PATTERNS_KYSM.md`** created (22,559 bytes):
- Full 23-pattern breakdown with KYSM status per pattern
- 3 ADK advanced patterns (Annie Wang) analyzed separately
- Quote highlights from Annie Wang + Mark Kashef embedded
- 7-phase roadmap: Phases 18–24 with source, priority, files, acceptance criteria
- Coverage scorecard table

### Priority Build Order (Updated)
| Phase | Item | Priority | Status |
|-------|------|----------|--------|
| 18 | Exploration & Discovery (dynamic FK probing + hierarchical decomposer) | 🔴 P0 | 🆕 Next |
| 19 | Agent-as-Tool Dynamic Override (suppress autonomy on Sentinel/CIBA) | 🔴 P0 | Planned |
| 20 | Resource-Aware Cost Router (per-tier routing cost tracking) | 🟡 P1 | ✅ WIRED — Apr 20 |
| 21 | Formal Revision Loop (`exit_conditions` + `max_iterations=3`) | 🟡 P1 | ✅ WIRED — Apr 20 |
| 22 | Dynamic Query Prioritization (Celery queue scoring) | 🟡 P1 | ✅ WIRED — Apr 20 |
| 23 | Safety Guardrails standalone layer | 🟢 P2 | ✅ WIRED — Apr 20 |
| 24 | Episodic Memory Store (Redis session scratchpad) | 🟢 P2 | ✅ WIRED — Apr 20 |

### Key Insights from Video Research
1. **Coordinator ≠ Router:** KYSM's Phase L5 router only skips steps — it doesn't do hierarchical task decomposition (Annie Wang, V3). Phase 18 needs to fix this.
2. **Agent-as-Tool vs. Coordinator:** Annie Wang (V3): sub-agents should be treated as stateless tools when Sentinel/CIBA enforce strict control. KYSM currently only has Coordinator mode.
3. **Exit condition design is the hard part:** Annie Wang's loop pattern emphasis — KYSM's self-healer has no max-iteration cap.
4. **TRIVIAL queries may be over-routed:** Pattern 15 (Resource-Aware) — router overhead for TRIVIAL could exceed query cost itself. Phase 20 should measure this.
5. **CoT reasoning traces missing:** Pattern 16 — for SAP audit/compliance, a formal reasoning trace is critical. Not implemented.

## ✅ Tasks & Follow-ups
- [x] Phase L5 Complexity Router — COMPLETE ✅ (Apr 20, committed)
- [x] Phase 18: Exploration & Discovery — COMPLETE ✅ (Apr 20, committed)
- [x] Phase 19: Agent-as-Tool Dynamic Override — COMPLETE ✅ (Apr 20, committed)
- [x] Phase 20: Resource-Aware Cost Router — COMPLETE ✅ (Apr 20, committed)
- [ ] Phase 21: Self-Healer Phase 2 (production failure injection + rule learning)
- [ ] Phase 22: Monitoring Dashboard (Prometheus + Grafana panels)
- [ ] Phase 23: Graph Embedding Phase 3 (vector DB failover chain)
- [ ] Phase 24: Memgraph Phase M3 (use_memgraph wiring)
- [ ] Real SAP HANA connection (hdbcli) — M8, P0 pending

## ✅ AI Engineer Talks Improvements — 10 Priorities Complete
Following the research summarized in `AI_ENGINEER_TALKS_IMPROVEMENTS.md`, implemented the top 10 recommended architecture changes derived from LangChain, Neo4j, Exa, and Mastra.ai speakers:

**P1: Complexity Router (TRIVIAL over-trigger fixed)**
- Tuned `COMPLEXITY_INDICATORS` for cross-module, temporal, aggregation, and negotiation.
- `TRIVIAL_THRESHOLD` lowered to 0.00 to prevent false-positives. (27/27 tests pass).

**P2: BM25 Hybrid Retrieval**
- Implemented Layered RAG in `schema_lookup` using `bm25_hybrid_search()`.
- Added exact keyword-matching before falling back to vector similarity.

**P3: Per-Tier Quality Metrics Dashboard**
- `HarnessRun` dataclass extended with `routing_tier`, `schema_rag_used`, `skip_steps`.
- Added `/api/v1/eval/monitoring/metrics` output for tier_distribution and schema_rag_hit_rate.

**P4: Graph Provenance Recorder**
- Added `GraphProvenanceRecorder` to trace table discovery step-by-step.
- Every response now includes an auditable `graph_provenance` chain explaining *why* tables were included.

**P5: CIBA Tier Configuration**
- Enforced varying autonomy gates based on tier (TRIVIAL: bypass block, SIMPLE: warn, COMPLEX: use Sentinel block, EXPERT: hard block pending human approval before Swarm execution).

**P6: MCP Server for KYSM**
- Built `mcp_server.py` using `fastmcp` to expose `search_sap_schema`, `match_sql_patterns`, and `traverse_graph` to any external Model Context Protocol client.

**P7: BM25 Schema Scoring (3-Signal RRF)**
- Overhauled ranking with: `α×RRF(vec,bm25) + β×BM25_norm + γ×centrality_percentile`.
- Hub tables (e.g. `MARA`, `LFA1`) receive a structural centrality boost via `graph_store.G.degree()`.

**P8: SAP Note Knowledge Graph**
- Built `sap_notes_kg.py` to extract operational knowledge (Error Codes, Solutions, Affected TCodes) and store it as a subgraph in Memgraph.
- Registered the `search_sap_notes` tool for the orchestrator.

**P9: Dynamic Tool Injection**
- Eliminated tool overload by limiting agent tools by tier (`TOOL_GATES`). TRIVIAL gets 2 tools, EXPERT gets 13.

**P10: Fluent Orchestrator Builder**
- Refactored `run_agent_loop` with a builder syntax (`OrchestratorBuilder().step("schema_discovery", if_tier_not("trivial"))`) to make the execution flow immediately readable, addressing workflow composability.

**All 10 priorities from the AI Engineer World's Fair are fully implemented and integrated!**
