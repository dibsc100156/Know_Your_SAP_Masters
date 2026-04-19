# KYSM — Agentic Engineering Video Series Summary
## AI Engineer Conf Talks — April 2026 Research Sprint

**Date:** April 19, 2026 | **Researcher:** Vishnu (OpenClaw) | **Context:** 5-video deep dive for Sanjeev / KYSM architecture review

---

## 🎬 Videos Covered

| # | Title | Speaker | Channel | Length | Views |
|---|---|---|---|---|---|
| 1 | Platforms for Humans and Machines | Juan Herreros | AI Engineer | 21m | ~2K |
| 2 | The 3 Pillars of Autonomy | Michele Catasta | AI Engineer | 24m | ~8K |
| 3 | Identity for AI Agents | Patrick Riley & Carlos Galan | AI Engineer | 1h 22m | ~7.3K |
| 4 | Shipping AI That Works (Eval Framework) | Aman Khan | AI Engineer | 1h 26m | ~12.8K |
| 5 | Effective Agent Design Patterns | Laurie Voss | AI Engineer | 15m | ~16.5K |

---

## 📌 Cross-Cutting Themes Across All 5 Videos

Before diving into each video, 4 themes emerged consistently across all 5 talks that should inform KYSM's next phase:

1. **Verification must be autonomous** — not human-reliant (Catasta, Aman, Laurie all independently arrive here)
2. **Agents are clients** — they need identity, delegation, and least-privilege access (Auth0)
3. **Context management is the unsolved problem** — global coherence + local focus simultaneously (Catasta)
4. **Eval maturity is the real competitive moat** — teams that measure get better faster (Aman, Laurie)

---

## Video 1 — Platforms for Humans and Machines (Juan Herreros, Banking Circle)

### Core Thesis
Human best practices for platform engineering == prerequisites for agent autonomy. Self-service, API-first, local-first, observability-as-API.

### Key Principles
| Principle | Description |
|---|---|
| **Self-Service** | Human OR agent gets resource without talking to a person |
| **API-First** | API is primary interface; CLI/portal/MCP are wrappers |
| **Local-First** | Fail fast locally; shift left (don't wait for CI) |
| **Observability-as-API** | Logs, metrics, traces all queryable via API — not dashboards |

### Agent-Specific Insights
- Agent hit platform wall → entire dev loop **halts**. Human hit same wall → asks colleague → iterates. Agents can't do this.
- Context files (CLAUDE.md) are platform documentation that agents can read.
- MCP servers = platform API exposure pattern for agents.

### Quotes
> *"If it's technically self-service but requires fetching from 5 different places — it's not self-service. Remove people from the process."*

> *"How does observability look if the primary user is an AI agent? Make logs, metrics, traces available via API or CLI."*

---

## Video 2 — The 3 Pillars of Autonomy (Michele Catasta, Replit)

### Core Thesis
Non-technical users can't supervise software creation. Full autonomy is essential. Autonomy ≠ long runtimes — narrow scope = autonomous AND fast.

### The 3 Pillars

**Pillar 1 — Frontier Models** (baseline capability, left as exercise to the reader)

**Pillar 2 — Verification (The Core Innovation)**
- Problem: >30% of agent-built features are broken on first run ("painted doors")
- Compounding errors accumulate when there's no verification at each step
- Verification spectrum: Code Analysis → Execution → Unit Tests → API Testing → **Browser Automation**

**Pillar 3 — Context Management**
- Global coherence (aligned with user intent) vs. local focus (working on immediate task) — these pull in opposite directions
- Agents need to reason about what they DON'T know (epistemic uncertainty)

### Autonomy ≠ Long Runtimes
> *"Maximize the reducible runtime — the span of time where the user makes zero technical decisions."*

### Parallelization for UX
- Sequential: user waits 45 min → sees result
- Parallel: user sees progress in minutes (independent features running simultaneously)

---

## Video 3 — Identity for AI Agents (Patrick Riley & Carlos Galan, Auth0)

### Core Thesis
Agents bring structurally new identity challenges (OWASP LLM Top 10 has new categories). Agents need their own identity layer AND user delegation layer.

### The 4 Pillars of Agent Identity

| Pillar | Description | KYSM Status |
|---|---|---|
| **1. Know who I am** | Agent needs verified user identity before applying permissions | ✅ SAPAuthContext (role_id) |
| **2. Call APIs on my behalf** | Agent uses user's OAuth token to access external services | ⚠️ Mock only |
| **3. Request my confirmation** | CIBA protocol — agent reaches user for high-risk approval | ❌ Not implemented |
| **4. Fine-grained access** | Least-privilege down to column/row/action level | ✅ masked_fields + denied_tables |

### Auth0 Product Updates Announced
- **CIBA (Client Initiated Backchannel Auth)** — async approval for high-risk agent actions
- **Token Vault** — persist and manage upstream refresh tokens; agent stays online without waking user
- **MCP server as OAuth client** — MCP server is a client, not just a server

### Key Architecture Insight
```
Agent (modeled as OAuth client)
  → MCP Server (also modeled as OAuth client)
    → Upstream APIs (resource servers)
```
Both layers need identity — audit logs trace through both.

### Security Threats Unique to Agents
- Scope escalation (agent gradually expanding its own permissions)
- Stateless agent token theft (long-running agents = high-value token targets)
- Cross-agent identity confusion (Agent A impersonating Agent B)

---

## Video 4 — Shipping AI That Works (Aman Khan, Arize)

### Core Thesis
Eval is the skill that separates shipping teams from stuck teams. Gut-feel "vibe checks" don't scale — PMs need repeatable, concrete evaluation strategies.

### The PM Confidence Curve
```
Stage 1: "Let me prototype with AI tools" → feels good
Stage 2: "How do I get this into production?" → confidence slump hits
Stage 3: Realize lack of tooling + education for reliable systems
```

### Why LLMs Are Harder to Test Than Software
| Property | Traditional Software | LLM/Agent |
|---|---|---|
| Determinism | 1+1=2 always | Can be convinced 1+1=3 |
| Correctness | Well-defined binary | Spectrum of quality |
| Paths | Finite + known | Unforeseen multi-paths |
| "Hallucination" | N/A | Sometimes a feature |

### The Eval Structure (4 Parts)
```
ROLE + {CONTEXT} + GOAL + LABELS
```
- **Role:** What persona/function the agent performs
- **Context:** The data being evaluated
- **Goal:** What determination to make
- **Labels:** Taxonomy of acceptable outputs (NOT numerical scores)

> *"Even PhD-level LLMs are still really bad at numbers. Use text labels, then map to scores programmatically."*

### 3 Types of Evals
| Type | Best For | Scalable? |
|---|---|---|
| Human Annotation | Ground truth datasets | ❌ Expensive/slow |
| Code-Based | Structural correctness (is valid JSON?) | ✅ |
| LLM-as-Judge | Subjective, multi-dimensional quality | ✅ |

### The Eval Maturity Model
| Level | Description |
|---|---|
| **L0** | No eval — "looked fine in demo" |
| **L1** | Spot checks — PM manually tests a few inputs |
| **L2** | Static test suite — run before each release |
| **L3** | Continuous eval — runs in CI/CD, blocks bad deployments |
| **L4** | Production monitoring — real-time eval, drift detection, A/B model comparison |

### What Good Production Eval Includes
- **Smoke tests** — agent fails fast when structurally broken
- **Golden dataset** — curated known inputs with expected outputs
- **Regression suite** — every production failure becomes an eval case
- **LLM-judge for quality** — scalable subjective assessment
- **Code-based checks** — schema, type, range validation

---

## Video 5 — Effective Agent Design Patterns (Laurie Voss, LlamaIndex)

### Core Thesis
The best agent use case: **turn a large body of text into a smaller body of text** — summarize, classify, extract, decide. Not generate long-form content reliably.

### Anthropic's 5 Agent Patterns (Mapped to KYSM)

**Pattern 1 — Chain**
- Sequential LLM steps, output feeds next step
- KYSM: `orchestrator.run_agent_loop()` steps 0→1→2→3→4→5 ✅

**Pattern 2 — Routing**
- LLM decides which processing path to follow
- KYSM: `PlannerAgent` routes to domain agents ✅

**Pattern 3 — Parallelization (2 flavors)**
- **Sectioning:** Same input processed differently in parallel (e.g., guardrails + main process)
  - KYSM: `sentinel.evaluate()` runs parallel to SQL generation ✅
- **Voting:** Same query → 3 tracks → majority vote (reduces hallucination because LLMs hallucinate differently)
  - KYSM: ❌ Not implemented

**Pattern 4 — Orchestrator Workers**
- Central LLM breaks task into sub-tasks → parallel workers → synthesis
- KYSM: `planner_agent` + parallel domain agents + synthesis ✅ (Deep Research pattern)

**Pattern 5 — Evaluator Optimizer**
- Generate → evaluate → if fail, retry with feedback → loop until pass
- KYSM: `critique_agent` → `self_healer.heal()` → re-critique ✅

### Why Voting Reduces Hallucination
> *"LLMs hallucinate, but they hallucinate in different ways. Three LLMs seldom hallucinate to the same wrong answer."*

### Key Quote on RAG
> *"RAG will never die. It's always going to be cheaper and faster to send less data. Always better answers if the context is more specific."*

---

## 🏗️ KYSM Current State — What's Already Implemented

### Fully Implemented (per MEMORY.md + codebase)
| Pattern/Feature | Source |
|---|---|
| Chain (sequential orchestrator) | orchestrator.py steps 0-5 |
| Routing (domain agent routing) | planner_agent.py |
| Parallelization - Sectioning (sentinel + SQL gen) | orchestrator_tools.py |
| Orchestrator Workers (multi-agent swarm) | swarm/planner_agent.py + synthesis |
| Evaluator Optimizer (critique → self-heal) | critique_agent + self_healer.py |
| RAG (Qdrant Schema + SQL Pattern) | qdrant_schema_store.py + sql_vector_store.py |
| Graph RAG (NetworkX + Memgraph) | graph_store.py + memgraph_adapter.py |
| Token Vault (mock) | mock executor — real OAuth not wired |
| Fine-grained access (masked_fields, denied_tables) | security_sentinel.py |
| Eval continuous pipeline | harness_runs.py + celery async |
| Golden dataset (50-query benchmark) | benchmark_results.json |
| Regression suite (trajectory_log) | harness_runs.py |
| CLAUDE.md context files | workspace root |
| Observability-as-API | eval_dashboard.py + Redis |
| Self-improvement loop (SelfImprover + MetaHarnessLoop) | self_improver.py + meta_harness_loop.py |

### Not Yet Implemented
| Gap | Priority | Complexity |
|---|---|---|
| Voting (multi-model consensus on critical SQL) | Medium | Low |
| CIBA async approval (high-risk SQL → user confirm) | High | Medium |
| Token Vault (real OAuth for SAP HANA) | High | High |
| L4 production monitoring (drift detection, batch eval) | Medium | Medium |
| Evaluator depth — semantic answer validation | Medium | Medium |
| Context management — explicit coherence checks | Low | High |
| Complexity-based routing (fast-path vs full orchestrator) | Low | Medium |

---

## 💡 New Ideas for KYSM — Generated from Video Research

### Priority 1 — High Impact, Manageable Complexity

#### 1. **Voting Executor for Critical Queries**
Laurie Voss's voting pattern: run the same SQL generation through 2-3 different paths (graph traversal vs. SQL pattern RAG vs. meta-path match), take majority/consensus vote.

**Why:** Three LLMs seldom hallucinate to the same wrong answer. Current KYSM picks one path. Voting could catch edge cases where graph path and SQL pattern RAG disagree significantly.

**Implementation:**
- Add a `VotingSQLGenerator` wrapping `run_agent_loop()` × 3 with different pillar weights
- Trigger when: `confidence_score < 0.7` OR query flagged as `compliance_critical`
- Threshold: 2/3 agreement = pass; disagreement = escalate to human review

#### 2. **CIBA-Style Async Approval for High-Risk SQL**
Auth0's CIBA pattern: when sentinel blocks a query, instead of just returning `BLOCKED`, trigger an async approval flow where the user's phone/app gets a notification.

**Why:** Currently `sentinel.evaluate()` returns a hard block with no recovery path. The user sees "blocked" with no way to approve. CIBA would allow them to say "actually yes this once — approve this specific query."

**Implementation:**
- Add `sentinel.request_approval(query, reason, user_id)` → queues approval request
- New `POST /api/v1/approvals/pending` endpoint → user approves via dashboard
- On approval: re-run with `approval_token` in context → executor accepts it

#### 3. **L4 Production Monitoring — Drift Detection + Batch Eval**
Aman's L4 eval: run a batch eval every N requests (e.g., every 100), comparing quality metrics to baseline. Alert if:
- Error rate on a specific domain increases
- Average confidence score drops
- Latency spikes

**Why:** Currently harness runs are per-request but there's no aggregate trending. A query that works today might degrade as the model drifts or data changes.

**Implementation:**
- Add `BatchEvalScheduler` (cron job every 1h)
- Run golden dataset subset (50 queries) against current state
- Store `batch_eval_results` in Redis with timestamps
- Expose `GET /api/v1/eval/drift` — returns trending metrics

---

### Priority 2 — Medium Complexity, High Strategic Value

#### 4. **Complexity-Based Routing (Fast-Path vs Full Orchestrator)**
Laurie Voss's routing pattern + Michele Catasta's "autonomy ≠ long runtimes": simple queries (single-table lookups, common patterns) should bypass full orchestrator and go through a fast-path.

**Why:** Currently ALL queries — even "show me vendors" — go through full 5-step orchestrator with graph traversal, meta-path matching, etc. This is expensive for simple cases.

**Implementation:**
- Add complexity classifier (LLM or rule-based) in `PlannerAgent`
- **Simple:** Single domain, no temporal, no cross-module → meta-path fast path only (skip orchestrator)
- **Complex:** Cross-module, temporal, multi-hop → full orchestrator
- **Analytical:** Aggregation, joins → specialized analytical path

#### 5. **Evaluator Optimizer — Semantic Answer Validation**
Current `critique_agent` validates: "does SQL execute?" Missing: "does the result actually answer the user's question?"

**Why:** SQL can execute perfectly and return wrong data (wrong table, wrong filters). The critique agent needs to check answer quality, not just SQL syntax.

**Implementation:**
- After `execute()` returns results, run a second LLM check: *"Given the user's question '{query}', does the result '{result_data}' actually answer it?"*
- If fail → trigger self-heal with semantic context
- Add to trajectory_log: `semantic_valid: bool`

#### 6. **Token Vault for Real SAP HANA OAuth**
Auth0's Token Vault + token exchange pattern for real SAP HANA connections.

**Why:** When wiring real hdbcli connection (Phase: Wire real SAP HANA), OAuth/OIDC token management will be needed for enterprise SSO. The mock executor doesn't need this, but production will.

**Implementation:**
- `TokenVaultManager` class: stores refresh tokens for SAP connection
- On query execution: exchange refresh token → short-lived HANA access token
- Handle token expiry → auto-refresh → retry query
- Map to SAP's own OAuth/OIDC server (SAP Identity Authentication Service)

---

### Priority 3 — High Complexity, Exploratory

#### 7. **Context Coherence Engine**
Michele Catasta's Pillar 3 (context management): explicit check that the current agent state is still coherent with the original user intent.

**Why:** In long multi-step conversations, the orchestrator can drift from the original intent. There's no explicit "are we still answering the right question?" check.

**Implementation:**
- On each orchestrator step: compare `current_goal` against `original_user_query`
- If divergence detected → log warning + optionally re-route
- Store `original_intent` in session context for coherence checks

#### 8. **Agent-as-Client MCP Modeling**
Auth0's insight: the agent IS an OAuth client, not just a user interface. KYSM's TOOL_REGISTRY could be formalized as MCP servers with OAuth client registration.

**Why:** As KYSM scales to more tools and external integrations, explicit client registration + dynamic scope negotiation prevents scope drift.

**Implementation:**
- Each domain agent = MCP server with OAuth client credentials
- External tools (SAP APIs, third-party) = resource servers
- Auth0/FGA-style fine-grained authorization policy per tool invocation

---

## 📊 Summary Scorecard — KYSM vs. Video Recommendations

| Recommendation | Covered? | Implementation Quality |
|---|---|---|
| Autonomous verification at each step | ✅ | Good (mock_executor + sentinel) |
| Self-healing retry loop | ✅ | Good (self_healer + HEALING_RULES) |
| Evaluator Optimizer pattern | ✅ | Good (critique → heal) |
| Orchestrator Workers (parallel dispatch) | ✅ | Good (ThreadPoolExecutor) |
| RAG (context-specific retrieval) | ✅ | Good (Qdrant Schema + SQL Pattern) |
| Routing (domain-based) | ✅ | Good (planner_agent) |
| Chain (sequential steps) | ✅ | Good (orchestrator steps) |
| Fine-grained access (column/row masking) | ✅ | Good (security_sentinel) |
| Context files for agent understanding | ✅ | Good (CLAUDE.md) |
| Observability-as-API | ✅ | Good (eval_dashboard + Redis) |
| Human-in-the-loop for high-risk actions | ❌ | Not implemented (just hard block) |
| Voting (multi-model consensus) | ❌ | Not implemented |
| L4 production monitoring (drift detection) | ❌ | Per-request, no batch trending |
| Token Vault (real OAuth lifecycle) | ❌ | Mock only |
| Semantic answer validation | ❌ | SQL validation only |
| Complexity-based routing | ❌ | All queries go full orchestrator |
| Context coherence checks | ❌ | Not implemented |

---

## 🚀 Recommended Next Actions (Ordered by Priority)

### This Week
1. **Voting Executor** — Add 2-path voting for confidence < 0.7 queries (low complexity, high impact)
2. **CIBA Approval Flow** — Implement async approval for sentinel blocks (medium complexity, high UX impact)

### Next Sprint
3. **L4 Monitoring** — Batch eval scheduler + drift detection endpoint
4. **Semantic Answer Validation** — Extend critique_agent to validate result quality

### Phase Roadmap
5. **Token Vault** — OAuth lifecycle for real SAP HANA (high complexity, blocks production)
6. **Complexity Routing** — Fast-path for simple queries (medium complexity, performance impact)
7. **Context Coherence Engine** — Explicit intent-alignment checks (high complexity, exploratory)

---

*Document generated: April 19, 2026 | Source: 5-video AI Engineer conf research sprint | Editor: Vishnu*