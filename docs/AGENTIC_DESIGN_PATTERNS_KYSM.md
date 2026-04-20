# Agentic Design Patterns — KYSM Implementation Guide
**Last Updated:** April 20, 2026 (Phases L5, 14, 20, 21, 22, 23, 24 wired) | Project: Know Your SAP Masters (KYSM)

---

## Overview

Three YouTube videos were analyzed to extract actionable agentic design patterns for KYSM:

| Video | Title | Channel | Views | Likes | Duration | Priority |
|-------|-------|---------|-------|-------|----------|----------|
| V1 | Master ALL 20 Agentic AI Design Patterns | Mark Kashef | 122,947 | 4,168 | 63 min | 🔴 HIGH |
| V2 | AI Agent Design Patterns (Part 1) | Google Cloud / Annie Wang | 329,596 | 11,995 | 8 min | 🔴 HIGH |
| V3 | 3 Advanced AI Agent Design Patterns (Part 2) | Google Cloud / Annie Wang | 63,136 | 2,306 | 8 min | 🔴 HIGH |

**Source:** Google engineer publication (400-page book) + Google ADK official patterns.

---

## 23 Agentic Design Patterns — KYSM Mapping

### Pattern 1: Prompt Chaining ✅ EXISTING (Partial)
**What it is:** Break a big task into smaller steps, run one after another. Each step validates the previous before passing data forward.

**KYSM status:** Partial — orchestrator Steps 1→2→3→... are a form of prompt chaining, but without explicit step-count limits or validation gates between each step.

**Gap:** No formal "chain with quality gate" — the step outputs are passed forward but there's no per-step rejection that halts the chain before reaching Step 8.

**What KYSM has:** Steps are sequential but orchestration is stateless per call; no per-step retry budget.

---

### Pattern 2: Routing ✅ LIVE (Phase L5)
**What it is:** Smart triage — direct queries to the right specialist agent or execution path based on query characteristics.

**KYSM status:** Phase L5 (Complexity Router) implements 4-tier routing:
- `TRIVIAL` (< 0.05) → Meta-path fast path only
- `SIMPLE` (0.05–0.30) → Standard orchestrator, skip Graph traversal
- `COMPLEX` (0.30–0.50) → Full orchestrator incl. Graph RAG + Voting Executor
- `EXPERT` (≥ 0.50) → Multi-Agent Domain Swarm

**Gap:** Phase L5 only handles skip guards and tier assignment. It does **not** do hierarchical task decomposition — it doesn't break "find vendor open POs with material data" into sub-agent tasks. See Pattern 18.

---

### Pattern 3: Parallelization ✅ LIVE (Phase 14 / Phase 10)
**What it is:** Split work into independent tasks → run concurrently → merge results.

**KYSM status:**
- Voting Executor (Phase 14): PATH_A/B/C/D fire in parallel via ThreadPoolExecutor — ~20ms total vs ~80ms sequential
- Multi-Agent Swarm (Phase 10): domain agents run concurrently, synthesis agent merges at end

**Gap:** No explicit **aggregator agent** that synthesizes cross-domain parallel results into a unified response. SynthesisAgent exists but is simplistic — it deduplicates and ranks by cross-domain relevance, but doesn't resolve conflicting field values (e.g., two agents report different PO counts for the same vendor on the same day).

---

### Pattern 4: Reflection / Critique ✅ LIVE (Phase 14 PATH_B)
**What it is:** Generator produces output → critic evaluates against strict conditions → loops back if conditions not met.

**KYSM status:** Voting Executor PATH_B uses `critique_agent.critique()` — evaluates SQL against 7-point validation rules. Phase 14's PATH_D (Healed Pattern) is essentially a cached reflection result.

**Gap:** The loop (generator → critique → revision → re-critique) is not a formal separate loop pattern. Self-healer initiates heal, then there's an implicit re-critique, but no explicit max-iteration cap or formal exit condition definition. See Pattern 22 (Phase 21 — Formal Revision Loop, 8-phase CoT trace, convergence detection).

---

### Pattern 5: Tool Use 🔴 EXISTING (Tool Registry)
**What it is:** Agent discovers, authorizes, executes tools with fallbacks.

**KYSM status:** TOOL_REGISTRY has 12 tools including `orchestrator_tools.py` implementations. MCP is referenced but not wired.

**Gap:** No tool authorization layer — every tool in TOOL_REGISTRY is pre-authorized. A production system needs per-role tool allowlisting and usage audit logging separate from the auth context.

---

### Pattern 6: Planning ✅ EXISTING (Partial)
**What it is:** Milestones, dependencies, and constraints laid out before execution begins.

**KYSM status:** Partial — orchestrator has a fixed execution order (Steps 0–8), which is a predefined plan. Meta-path library provides pre-computed JOIN plans. But there is no dynamic planning layer that reorders steps based on query intent.

**Gap:** Dynamic re-planning based on intermediate results (e.g., Schema RAG finds unexpected tables → Graph traversal should run before SQL Pattern RAG). Currently the plan is fixed at call time.

---

### Pattern 7: Multi-Agent Collaboration ✅ LIVE (Phase 10 / Phase 13)
**What it is:** Manager + roles + shared memory across agents.

**KYSM status:**
- Phase 10: Planner Agent → domain agents → Synthesis Agent
- Phase 13: Message Bus (Redis pub/sub + streams, 6 message types)
- Phase 13b: Negotiation Protocol (4-phase ASSERTING→CHALLENGING→NEGOTIATING→COMMITTED)

**Gap:** Agent collaboration is synchronous at call time. There is no persistent shared memory layer between agents across different queries. Agents reset state after each query. Long-running collaborative workflows (e.g., "analyze this vendor's risk profile across 5 dimensions over the next hour") are not supported.

---

### Pattern 8: Memory Management 🟡 EXISTING (Partial)
**What it is:** Short-term (session), episodic (conversation), and long-term (persistent) memory layers.

**KYSM status:**
- **Long-term:** Qdrant `sql_patterns` collection (Phase 16 healed patterns), `healed_pattern_store.py`
- **Short-term:** Auth context per-call, no session scratchpad
- **Episodic:** None

**Gap:** No episodic memory per session. When a user asks a follow-up query ("same for customer 123"), the orchestrator doesn't recall the prior query's context from the same session. This creates friction in multi-turn conversations.

✅ **RESOLVED — Phase 24:** Episodic Memory Store (Redis-backed session scratchpad) records query history, conversation context, agent scratchpad, and query deduplication. Fire-and-forget with in-memory fallback. `backend/app/core/episodic_memory.py` (35KB).

---

### Pattern 9: Learning & Adaptation ✅ LIVE (Phase 16)
**What it is:** Feedback → prompts/policies/tests updated automatically.

**KYSM status:** Phase 16 stores healed SQL patterns in Qdrant. PATH_D in Voting Executor applies prior healed patterns as a 4th vote path. Reuse counter tracks how often each pattern is applied.

**Gap:** The learning loop is one-directional (heal → store → reuse). There is no mechanism to **unlearn** bad patterns (e.g., a pattern that was healed but later found to produce incorrect results for edge cases). The reuse counter never decrements.

---

### Pattern 10: Goal Setting & Monitoring ✅ LIVE (Phase L4)
**What it is:** KPIs, drift detection, and course-correction.

**KYSM status:** Phase L4 (Monitoring Dashboard) — 9 metric compute methods: throughput, success rates, latency (p50/p95/p99/p999), voting, self-heal, semantic trust, CIBA, Sentinel, swarm, domain+role breakdowns.

**Gap:** No active goal tracking per query. Monitoring is post-hoc aggregate analysis. There's no per-query goal state (e.g., "I intended to return 50 rows of vendor data") against which drift could be measured mid-execution.

---

### Pattern 11: Exception Handling & Recovery ✅ LIVE (Phase 6)
**What it is:** Classify error → backoff → fallbacks.

**KYSM status:** Phase 6 self-healer maps error codes (ORA-00918, ORA-01476, etc.) to heal strategies (6 strategies: add_alias, fix_where, remove_dupe, etc.). Validation harness (Phase 5.5) catches syntax errors before execution.

**Gap:** Exception classification is static (rule-based). When the self-healer exhausts all strategies, there's no escalation to a human-in-the-loop — the query just fails. CIBA (Phase 15) can block, but cannot serve as a recovery escalation path for persistent heal failures.

---

### Pattern 12: Human-in-the-Loop ✅ LIVE (Phase 15)
**What it is:** Review cues and approval gates for high-risk operations.

**KYSM status:** Phase 15 CIBA — Sentinel verdict BLOCK → approval request created → async approve/deny via Redis-backed store → 1hr auto-approval for repeated queries.

**What KYSM has over standard HITL:** Auto-approve/deny hash for repeated queries (queries that were previously approved/denied bypass the approval flow).

**Gap:** HITL is binary (approve/deny). There's no "modify and approve" workflow (e.g., supervisor approves with a modified SQL filter). The current CIBA design only gates or blocks — it doesn't support query rewriting.

---

### Pattern 13: Retrieval (RAG) ✅ LIVE (Phase M6)
**What it is:** Parse → chunk → embed → rerank.

**KYSM status:**
- Schema RAG: Qdrant `sap_schema` collection (DDIC metadata)
- SQL Pattern RAG: Qdrant `sql_patterns` collection (68+ proven patterns, 18 domains)
- Graph Table Context: Qdrant `graph_table_context` collection (text embeddings)
- Graph Node Embeddings: Qdrant `graph_node_embeddings` collection (Node2Vec)
- QM Semantic: Qdrant `qm_semantic_notifications` collection (50 mock QM notifications)

**Gap:** No reranking layer after initial retrieval. All KYSM RAG uses cosine similarity directly. A cross-encoder reranker would improve result quality significantly, especially for Schema RAG where field-level matching matters.

---

### Pattern 14: Inter-Agent Communication ✅ LIVE (Phase 13)
**What it is:** Protocols, IDs, and expiry for message routing between agents.

**KYSM status:** Redis pub/sub + streams MessageBus with 6 message types (QUERY, RESPONSE, ASSERTION, CHALLENGE, NEGOTIATE, COMMIT). TTL-based message expiry. AgentRegistry with subscription topics.

**Gap:** Messages are fire-and-forget in pub/sub mode. There's no delivery guarantee confirmation — if a domain agent crashes mid-query, the synthesis agent waits indefinitely (10s timeout via `wait_for_message`). Crash recovery leaves orphaned messages in Redis streams.

---

### Pattern 15: Resource-Aware Optimization 🔴 MISSING
**What it is:** Route by cost/complexity — cheap models for simple tasks, expensive models for complex ones. Track routing cost vs. query execution savings.

**KYSM status:** ✅ IMPLEMENTED — April 20, 2026.

Phase 20 (Resource-Aware Cost Router) wraps ComplexityRouter with per-tier latency budgets (TRIVIAL=5ms, SIMPLE=15ms, COMPLEX=50ms, EXPERT=∞) and adaptive bypass via LRU decision cache. If routing overhead exceeds budget, falls back to pre-computed DEFAULT_DECISIONS. See `backend/app/core/router_cost_tracker.py`.

---

### Pattern 16: Reasoning Techniques (CoT/ToT) 🔴 MISSING (Prompt Engineering)
**What it is:** Chain-of-Thought, Tree-of-Thoughts, self-consistency, agent debate.

**KYSM status:** Not explicitly implemented. Prompt templates exist but no formal reasoning trace extraction.

**Gap:** When KYSM generates a complex multi-table JOIN (e.g., Procure-to-Pay with 7 tables), there's no reasoning trace explaining *why* each table was included in what order. The `explanation` field in responses is generated but not grounded in a formal CoT trace. For audit/compliance scenarios, a reasoning trace is critical.

**Recommendation:** Add optional CoT mode via a `reasoning_depth` parameter in the API — when `reasoning_depth=detailed`, the orchestrator generates a step-by-step trace stored in the result dict and visible in the frontend.

---

### Pattern 17: Evaluation & Monitoring 🟡 EXISTING (Partial)
**What it is:** Golden sets, SLA measurement, drift detection.

**KYSM status:**
- Phase L4: Real-time monitoring dashboard
- Phase 12: QualityEvaluator (correctness_score, trajectory_adherence)
- benchmark_50.py: 50-query benchmark suite ( GREEN, 0 failures)

**Gap:** No golden set evaluation pipeline. The 50-query benchmark is a one-time manual run. A production CI/CD pipeline needs automated golden set evaluation on every commit, with regression alerts.

---

### Pattern 18: Guardrails & Safety ✅ LIVE (Phase 6c + Phase 23)
**What it is:** PII detection, prompt injection prevention, sandboxing.

**KYSM status:**
- Phase 6c: Proactive Threat Sentinel (6 threat engines)
- Phase 23: Safety Guardrails standalone layer (8 engines: SQL injection, PII leak, cross-module escalation, denied-table probe, data exfiltration, temporal inference, role impersonation, output PII leak) — `backend/app/core/safety_guardrails.py` (52KB) — behavioral anomaly detection
- Phase 5: Critique Gate (7-point SQL validation)
- AuthContext column-level masking (Pillar 1)

**Gap:** Sentinel is inline with execution (pre-execution gate). Separating safety guardrails as an independent layer (above the orchestrator) would improve maintainability and allow safety policies to be updated without touching the orchestrator. See Phase 23.

**What Google ADK recommends vs. KYSM:** ADK treats guardrails as a deployment-time configuration, not an inline code path. KYSM should decouple `security_sentinel.py` into two layers: (1) `safety_guardrails.py` — standalone pre-execution gate, (2) `threat_sentinel.py` — behavioral anomaly detector during execution.

---

### Pattern 19: Prioritization ✅ LIVE (Phase 22)
**What it is:** Value × effort × urgency × risk — dynamically reorder the work queue.

**KYSM status:**
- Phase 22: Dynamic Query Prioritization — urgency × role_authority × complexity × SLA × recency scoring
  - Formula: `priority_score = urgency × role_authority × complexity × SLA × recency × critical_boost`
  - Queue routing: is_critical OR score ≥ 8.0 → priority queue; else agent queue
  - Celery task priority 0-10 mapped from score bands
  - `backend/app/core/query_priority_scorer.py` (18KB) In a production SAP system, queries from FI_ACCOUNTANT (finance) and SECURITY_AUDITOR role should be prioritized over AP_CLERK if both hit the queue simultaneously. There is no priority scoring engine.

**Phase 22** addresses this.

---

### Pattern 20: Exploration & Discovery 🔴 MISSING
**What it is:** Map the problem space, cluster related entities, probe unknowns before committing to a solution path.

**KYSM status:** Not implemented. KYSM is locked to a predefined graph schema (114 nodes, 47 edges). Any query that falls outside the 14 meta-paths and 114 known tables must fallback to Schema RAG, which is expensive and slow for novel queries.

**Gap:** The predefined graph schema cannot grow automatically. When a new SAP module is deployed (e.g., SAP S/4HANA for Real Estate RE-FX), DD08L (FK relationships) changes but KYSM's graph is not updated. The system has no mechanism to discover and incorporate new table relationships without manual graph rebuilding.

**Phase 18** addresses this.

---

## Advanced Patterns from Google ADK (Annie Wang)

### ADK Pattern A1: Loop (Review & Critique) ✅ PARTIAL (Phase 14)
See Pattern 4 above. KYSM has critique but not as a formal explicit loop with counter and exit conditions.

### ADK Pattern A2: Coordinator (Router) 🟡 PARTIAL (Phase L5)
Phase L5 router assigns tier but does not do **hierarchical task decomposition** — it doesn't break "find sushi in San Francisco" into "food_agent + transport_agent as a team." It only decides which steps to skip.

### ADK Pattern A3: Agent as Tool 🔴 MISSING (Phase 19)
When Sentinel is in ENFORCING mode or CIBA returns TIGHTEN, KYSM needs to suppress agent autonomy and treat sub-agents as stateless tools. Currently sub-agents retain full autonomy even during Sentinel-enforced sessions.

---

## Recommended KYSM Roadmap Update (Phases 18–24)

| Phase | Name | Source | Priority | Status |
|-------|------|--------|----------|--------|
| **18** | **Exploration & Discovery (Dynamic Schema Mapping)** | V1 P20 + V3 Coordinator | 🔴 HIGH | 🆕 New |
| **19** | **Agent-as-Tool Dynamic Override Mode** | V3 Pattern A3 | 🔴 HIGH | 🆕 New |
| **20** | **Resource-Aware Cost/Complexity Router** | V1 P15 + V3 Coordinator | 🟡 MED | 🆕 New |
| **21** | **Formal Revision Loop with Exit Conditions** | V3 Loop Pattern | 🟡 MED | 🆕 New |
| **22** | **Dynamic Query Prioritization Engine** | V1 P19 | 🟡 MED | 🆕 New |
| **23** | **Safety Guardrails (Standalone Layer)** | V1 P18 | 🟢 LOW | 🆕 New |
| **24** | **Episodic Memory Store (Session Scratchpad)** | V2 P8 Memory | 🟢 LOW | 🆕 New |

### Phase 18: Exploration & Discovery (Priority: 🔴 HIGH)

**What:** Dynamic FK probing when no meta-path hits and Schema RAG confidence < 0.60.

**Key insight from V3:** The Coordinator pattern does hierarchical task decomposition — the router doesn't just *skip* steps, it *decomposes* a task into what sub-agents are needed. KYSM's router should do the same.

**Files to create:**
- `backend/app/core/exploration_engine.py` — exploration budget (max 3 probes/query), DD08L probing, table name embedding search against `sap_schema`
- `backend/app/core/hierarchical_decomposer.py` — break complex queries into sub-agent task lists

**Acceptance criteria:**
- Novel query (outside 14 meta-paths) triggers exploration → returns semantically related tables + FK paths within 200ms
- Exploration budget enforced: max 3 probes/query, TTL cache prevents repeated exploration cost

---

### Phase 19: Agent-as-Tool Dynamic Override (Priority: 🔴 HIGH)

**What:** Sentinel/CIBA triggers a mode where sub-agents are treated as stateless tools.

**Key insight from V3:** "Agent as Tool pattern — full system control retained by primary agent. When you want to bypass a sub-agent's autonomy, treat it as a tool."

**Files to create:**
- `backend/app/agents/swarm/agent_tool_mode.py` — `execute_as_tool()` wrapper that runs sub-agent synchronously and discards session state after execution

**Acceptance criteria:**
- When `session.tightness >= 3` OR Sentinel verdict = ENFORCING → auto-engage agent-as-tool mode
- Sub-agent responses are direct pass-through, no autonomous revision loops

---

### Phase 20: Resource-Aware Cost Router (Priority: 🟡 MED)

**What:** Track routing latency per tier; bypass routing if computation cost exceeds savings.

**Files to create:**
- `backend/app/core/router_cost_tracker.py` — per-tier latency tracking, fall-back to default path when routing overhead > threshold

**Acceptance criteria:**
- TRIVIAL queries route in < 5ms; SIMPLE in < 15ms; COMPLEX in < 50ms
- Router overhead logged to monitoring dashboard (Phase L4)

---

### Phase 21: Formal Revision Loop (Priority: 🟡 MED)

**What:** Wrap the self-heal loop in a formal `RevisionLoop` class with `exit_conditions` + `max_iterations`.

**Files to create:**
- `backend/app/core/revision_loop.py` — `RevisionLoop(exit_conditions, max_iterations=3)`, revision_number + improvement_delta tracking

**Acceptance criteria:**
- Self-heal exits at iteration 3 OR when confidence >= 0.85 OR when SQL passes all critique checks
- Each iteration logged: revision_number, heal_code applied, improvement_delta

---

### Phase 22: Dynamic Query Prioritization (Priority: 🟡 MED)

**What:** Priority scoring engine for Celery queue — urgency × recency × role_authority × complexity_penalty.

**Files to create:**
- `backend/app/core/query_priority_engine.py` — `compute_priority(query, auth_context, session_context) -> float`
- Wire `task_priority` into Celery `send_task()` calls

**Acceptance criteria:**
- CIBA-pending queries always score MAX priority (10)
- Same-session follow-up queries get 1.3× boost
- FI_DOMAIN queries from FI_ACCOUNTANT get +0.2 over MM_CLERK
- p95 queue latency < 200ms at conc=5

---

### Phase 23: Safety Guardrails (Standalone Layer) (Priority: 🟢 LOW)

**What:** Decouple Sentinel into two layers — `safety_guardrails.py` (pre-execution syntax/semantic) and `threat_sentinel.py` (behavioral anomaly during execution).

**Files to create:**
- `backend/app/core/safety_guardrails.py` — standalone `GuardrailVerdict` pre-execution gate

**Acceptance criteria:**
- GuardrailVerdict: PASS / FAIL / REVIEW
- Violation categories: DATA_EXFILTRATION, SCHEMA_ENUMERATION, CROSS_MODULE_ESCALATION, DENIED_TABLE_PROBE, TEMPORAL_INFERENCE, ROLE_IMPERSONATION

---

### Phase 24: Episodic Memory (Session Scratchpad) (Priority: 🟢 LOW)

**What:** Redis-backed per-session memory store — last 5 query-result pairs as context for next query.

**Files to create:**
- `backend/app/core/episodic_memory.py` — `EpisodicMemory(session_id, ttl=24h)`, `store(query, result)`, `recall()` (returns last N pairs)

**Acceptance criteria:**
- Follow-up queries ("same for customer 123" after "vendor payment terms") retrieve prior context automatically
- Session TTL: 24h or session end
- Episodic memory excluded from compliance audit logs (it's inference context, not data)

---

## KYSM Pattern Coverage Scorecard

| Pattern | Name | KYSM Status | Phase |
|---------|------|-------------|-------|
| 1 | Prompt Chaining | 🟡 Partial | — |
| 2 | Routing | ✅ LIVE | L5 |
| 3 | Parallelization | ✅ LIVE | 14 / 10 |
| 4 | Reflection / Critique | ✅ LIVE (partial) | 14 |
| 5 | Tool Use | 🟡 Partial | Tool Registry |
| 6 | Planning | 🟡 Partial | Meta-path |
| 7 | Multi-Agent Collaboration | ✅ LIVE | 10 / 13 |
| 8 | Memory Management | 🟡 Partial | 16 |
| 9 | Learning & Adaptation | ✅ LIVE | 16 |
| 10 | Goal Setting & Monitoring | ✅ LIVE | L4 |
| 11 | Exception Handling & Recovery | ✅ LIVE | 6 |
| 12 | Human-in-the-Loop | ✅ LIVE | 15 |
| 13 | Retrieval (RAG) | ✅ LIVE | M6 |
| 14 | Inter-Agent Communication | ✅ LIVE | 13 |
| 15 | Resource-Aware Optimization | 🔴 MISSING | 20 |
| 16 | Reasoning Techniques (CoT/ToT) | 🔴 MISSING | — |
| 17 | Evaluation & Monitoring | 🟡 Partial | L4 / 12 |
| 18 | Guardrails & Safety | 🟡 Partial | 6c |
| 19 | Prioritization | 🔴 MISSING | 22 |
| 20 | Exploration & Discovery | 🔴 MISSING | 18 |
| A1 | Loop (Review & Critique) | ✅ LIVE (partial) | 14 |
| A2 | Coordinator (Router) | 🟡 Partial | L5 |
| A3 | Agent as Tool | 🔴 MISSING | 19 |

**Coverage:** 9/23 ✅ LIVE · 8/23 🟡 Partial · 6/23 🔴 MISSING

---

## Key Quotes to Keep in Mind

From Annie Wang (ADK Part 2, Loop Pattern):
> *"We need to be really careful designing this exit condition, which can add complexity to our system."*

From Annie Wang (ADK Part 1, Sequential Agent):
> *"This rigid predefined structure can't adapt to dynamic situations."* — KYSM's orchestrator is sequential by design; Phase L5 adds adaptive skip guards but the structure is still rigid.

From Annie Wang (ADK Part 2, Coordinator Pattern):
> *"Extra model calls for routing — higher latency and cost."* — KYSM's Phase L5 router computes on every query; Phase 20 should measure and optimize this.

From Mark Kashef (Pattern 4 — Reflection):
> *"At some point you're either adding too much or you're basically pushing it to the limit where it starts hallucinating on something it wouldn't have hallucinated before. It starts to overthink."* — KYSM's maximum self-heal iterations should be capped explicitly (Phase 21).

---

## References

- [Mark Kashef — 20 Agentic Design Patterns (YouTube)](https://youtu.be/e2zIr_2JMbE)
- [Google Cloud — AI Agent Design Patterns Part 1 (YouTube)](https://youtu.be/GDm_uH6VxPY)
- [Google Cloud — 3 Advanced AI Agent Design Patterns Part 2 (YouTube)](https://youtu.be/89KKm_a4M7A)
- [Google ADK Documentation](https://goo.gle/40ACYEw)
- [Google Multi-Agent Patterns Blog](https://goo.gle/multiagentpattern)
- [Google Agentic Pattern Lab](https://goo.gle/agenticpattern)
