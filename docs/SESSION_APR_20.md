---
date: 2026-04-20
tags: [daily, memory, kysm, design-patterns, documentation]
---
# 2026-04-20

## 📝 Activity Log

### Phase L5 Completed Yesterday — Complexity Router LIVE ✅
All 8 patches applied to `orchestrator.py`. API wired to return `routing_tier` + `routing_score` in `ChatResponse`. Commits `fd038f1` + `f049558`.

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
| 20 | Resource-Aware Cost Router (per-tier routing cost tracking) | 🟡 P1 | Planned |
| 21 | Formal Revision Loop (`exit_conditions` + `max_iterations=3`) | 🟡 P1 | Planned |
| 22 | Dynamic Query Prioritization (Celery queue scoring) | 🟡 P1 | Planned |
| 23 | Safety Guardrails standalone layer | 🟢 P2 | Planned |
| 24 | Episodic Memory Store (Redis session scratchpad) | 🟢 P2 | Planned |

### Key Insights from Video Research
1. **Coordinator ≠ Router:** KYSM's Phase L5 router only skips steps — it doesn't do hierarchical task decomposition (Annie Wang, V3). Phase 18 needs to fix this.
2. **Agent-as-Tool vs. Coordinator:** Annie Wang (V3): sub-agents should be treated as stateless tools when Sentinel/CIBA enforce strict control. KYSM currently only has Coordinator mode.
3. **Exit condition design is the hard part:** Annie Wang's loop pattern emphasis — KYSM's self-healer has no max-iteration cap.
4. **TRIVIAL queries may be over-routed:** Pattern 15 (Resource-Aware) — router overhead for TRIVIAL could exceed query cost itself. Phase 20 should measure this.
5. **CoT reasoning traces missing:** Pattern 16 — for SAP audit/compliance, a formal reasoning trace is critical. Not implemented.

## ✅ Tasks & Follow-ups
- [x] Phase L5 Complexity Router — COMPLETE ✅ (Apr 20, committed)
- [x] Video research — 3 YouTube videos analyzed ✅
- [x] docs/AGENTIC_DESIGN_PATTERNS_KYSM.md — created ✅
- [x] LEVEL5_ROADMAP.md — updated with Phases 18–24 ✅
- [x] SESSION_APR_20.md — session log ✅
- [ ] Phase 18: Exploration & Discovery — next build
- [ ] Phase 19: Agent-as-Tool Dynamic Override
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
