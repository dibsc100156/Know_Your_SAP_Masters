# Harness Engineering in AI Agents  --  Top 10 Trends & Production Use Cases

_Crafted: April 13, 2026 | Based on: Karpathy (AI Automators), Solo Swift Crafter, Cyril Imhof (This is the Year E44 & E45), KYSM Implementation_

---

## Top 10 Trends in Harness Engineering

### Trend 1: Generator / Evaluator / Planner Architecture

**What it is:** Three distinct agents with explicit role separation, each with their own scoped tool harness.

- **Planner**  --  augments sparse user intent into a complete specification
- **Generator**  --  executes the build in one shot based on the spec
- **Evaluator / QA**  --  independently validates output, triggers feedback loops back to Planner + Generator

**Why it wins:** A single model that generates *and* evaluates its own work has a structural self-evaluation bias  --  it overestimates its own output quality. Role separation is not optional; it is the architecture.

**Source:** Anthropic's V2 harness design (Cyril Imhof, E45)

---

### Trend 2: Phase-Gated Execution with Validation Loops

**What it is:** Each workflow step is a gated phase. The agent must produce a validated output before the next phase unlocks. Failures don't propagate  --  they are caught and either self-healed or escalated at the gate.

```
Phase 1 → [Validator Gate] → Phase 2 → [Validator Gate] → Phase 3 → ...
  fail → Self-heal loop (fixed retries)
  pass → Next phase
```

**Why it wins:** The March of Nines math (Karpathy): a 10-step workflow at 90% per step = only 34.9% end-to-end success. Phase gates with validation close this gap deterministically rather than probabilistically.

**KYSM implementation:** 8-phase orchestrator  --  Phase 0 (Meta-Path) → 1 (Schema RAG) → 2 (SQL Pattern RAG) → 3 (Graph Traversal) → 4 (SQL Assembly) → 5 (Validation Harness) → 6 (Self-Heal) → 7 (Execution) → 8 (Response). Each phase tracked in Redis.

---

### Trend 3: Context Budgeting  --  Curing "Context Anxiety"

**What it is:** Active management of what enters the LLM's context window, not a passive accumulation of everything. Only the current task, domain knowledge from external files, and the validated output of the previous phase are injected.

**The problem:** As context fills, models degrade  --  they get "anxious" and start wrapping up tasks prematurely, dropping important context. Even 1M token windows (Claude Opus 4.6) have this problem past a threshold.

**KYSM implementation:** Graph embedding search surfaces only top-K tables per phase, not the entire schema. The orchestrator passes a curated context window per phase, not the full conversation history.

---

### Trend 4: Scoped Tool Sets  --  Cutting the Attack Surface

**What it is:** Giving the agent only the tools it needs for the current phase, not a comprehensive list of everything available.

**The proof:** Vercel cut 80% of their agent's tools → accuracy jumped from 80% to 100%. Every extra tool is a new failure pathway. More tools does not equal more capability; more tools equals more failure surface.

**The principle:** Scoped tool sets > comprehensive tool lists. Audit every tool: *If this fails, does the whole workflow fail?* If no  --  it is optional for this phase.

---

### Trend 5: Typed Sub-Agent Output Contracts

**What it is:** Every sub-agent in a multi-agent swarm returns a typed contract  --  a structured schema with domain-specific field validation. The synthesis agent validates each contract before merging.

**Why it wins:** Without typed contracts, synthesis has no reliable way to know if a domain agent's output is structurally sound. Contract validation catches: missing entity IDs, wrong field names, result set mismatches, SQL injection attempts in results.

**KYSM implementation:** `contracts.py`  --  7 domain contracts (BPAgentContract, PURAgentContract, MMAgentContract, SDAgentContract, QMAgentContract, WMAgentContract, CROSSAgentContract) each with domain-specific `validate_output()`. Synthesis runs `validate_contract()` before merge  --  failures flag but never block.

**Design rule:** validation failures set `validation_passed=False` but NEVER block synthesis. The merge always proceeds.

---

### Trend 6: Self-Healing SQL with Validation Harnesses

**What it is:** A dry-run validation step between SQL assembly and real execution. The harness runs `SELECT COUNT(*) FROM (...)` against a mock/dry-run schema first. If it fails, the SQL Self-Healer is triggered  --  a targeted LLM call that fixes the specific syntax error and re-validates before real execution.

**Why it wins:** Zero human intervention for syntax recovery. The harness catches SQL errors before they touch production data.

**KYSM implementation:** Phase 5.5  --  Validation Harness. `sql_executor.py` runs dry-run before real execution. `orchestrator.py` has a self-heal loop that retries with fixed SQL up to a configured threshold before escalating.

---

### Trend 7: Distributed Harness Runs Tables

**What it is:** Every agentic query produces a structured audit record in a shared state store (Redis, Supabase). Each record contains: run_id, role, timestamps per phase, validator outcomes, error details, artifacts passed between phases.

**Why it wins:** Production systems need observability. You cannot debug a production failure without knowing exactly which phase failed, what the validator said, and what artifacts were produced. The Harness Runs Table is the flight recorder for every query.

**KYSM Redis key structure:**
```
harness_run:{run_id}          → Hash (role, phases, timestamps)
harness_runs:by_role:{role}   → Sorted Set (score=timestamp)
harness_runs:active            → Set of in-progress run_ids
TTL: 30 days on all keys
```

---

### Trend 8: Proactive Threat Sentinel  --  Security as a Harness Gate

**What it is:** A real-time behavioral anomaly detection engine that evaluates every query before execution. Six detection engines run pre-execution:

1. **CROSS_MODULE_ESCALATION**  --  multi-hop graph traversal to out-of-scope tables
2. **SCHEMA_ENUMERATION**  --  bulk table discovery probes (>5 new tables per query)
3. **DENIED_TABLE_PROBE**  --  repeated attempts to access blocked tables
4. **DATA_EXFILTRATION**  --  unusually large result sets (>5,000 rows)
5. **TEMPORAL_INFERENCE**  --  restricted historical period access by HR/AP roles
6. **ROLE_IMPERSONATION**  --  sudden cross-domain shift mid-session

**Why it wins:** Security cannot be a post-execution check. It must be a pre-execution gate inside the harness with modes from AUDIT (log only) to ENFORCING (block + dynamite-tight session).

**KYSM implementation:** `security_sentinel.py`  --  runs before orchestrator execution. `sentinel` verdict + `sentinel_stats` in API response.

---

### Trend 9: Multi-Agent Swarms with Synthesis / Merge Layer

**What it is:** For cross-domain queries, a Planner Agent routes to multiple parallel Domain Agents (e.g., PUR + BP + QM simultaneously). Results are collected and passed to a Synthesis Agent that deduplicates, ranks by relevance, resolves conflicts, and merges into a single coherent response.

**Why it wins:** No single agent can cover all SAP domains deeply. The swarm pattern  --  parallel dispatch + synthesis merge  --  scales to arbitrarily complex queries without the orchestrator becoming a monolith.

**KYSM implementation:** Phase 10  --  `swarm/planner_agent.py` (7-domain complexity analyzer), `swarm/synthesis_agent.py` (merge + rank + conflict resolution). `use_swarm=True` flag on API. ThreadPoolExecutor for parallel dispatch.

**Swarm routing types:** SINGLE | PARALLEL | CROSS_MODULE | NEGOTIATION | ESCALATE

---

### Trend 10: Continuous Harness Co-Optimization with Model Upgrades

**What it is:** Harnesses and models must be co-optimized continuously. As models improve (e.g., Claude 4.5 to 4.6), previously necessary harness scaffolding can be stripped  --  the model handles more general-purpose reasoning without explicit tool instructions.

**The re-evaluation rule:** Every new model release → re-evaluate: *Which parts of the harness can we remove? Which parts are still structurally necessary?*

**What never gets stripped:** The Generator/Evaluator separation. The self-evaluation bias problem is structural  --  better models do not fix it.

**What can be stripped over time:** Explicit context compaction instructions, detailed tool selection scaffolding, iterative loops that newer models handle in one shot.

---

## Production Use Cases

### Use Case 1: Enterprise Master Data Chatbots (KYSM Pattern)

**What it is:** A RAG-powered chatbot on top of SAP S/4HANA that answers questions about vendors, customers, materials, POs, inventory, quality inspections, and project costs.

**Harnesses in production:**
- 5-Pillar RAG harness (Schema + SQL Pattern + Graph + Meta-Path + Security Mesh)
- Phase-gated orchestrator with 8 steps
- Multi-agent swarm for cross-domain queries
- Typed output contracts per domain agent
- Redis Harness Runs Table for every query

**Business value:** Non-technical SAP users query complex cross-module data in natural language. No SQL knowledge required. Row-level and column-level security enforced via AuthContext.

---

### Use Case 2: Autonomous Coding Agents (Stripe Minions Pattern)

**What it is:** AI coding agents that handle production on-call autonomously  --  writing PRs, deploying code, rolling back faulty changes.

**Harnesses in production:**
- Narrow but deeply integrated tool set (runbooks, deployment systems, rollback procedures, alerting dashboards)
- Sandbox code execution environment
- Generator / Evaluator loop for code quality
- Phase gates: plan → implement → test → deploy

**Real-world example:** Stripe Minions  --  1,300 production PRs/week, zero human code review for routine changes.

---

### Use Case 3: Financial Analysis Agents (M&A Due Diligence)

**What it is:** Agents that conduct M&A due diligence, financial modeling, and market research by querying multiple data sources simultaneously.

**Harnesses in production:**
- Planner (expands "analyze this acquisition" into full spec with financial metrics, risk factors, comparable analysis)
- Parallel data agents (financial data, legal data, market data)
- Synthesis agent (merges + deduplicates + flags conflicts)
- Domain skills (tacit knowledge from financial advisors encoded as structured prompts)
- HITL gate for final recommendation sign-off

**Business model shift:** In the physical world, you go to McKinsey for tacit knowledge. In the agentic world, you buy McKinsey's skill to run inside your AI agent.

---

### Use Case 4: Agentic ERP Operations (Procure-to-Pay, Order-to-Cash)

**What it is:** AI agents embedded inside ERP systems that handle procure-to-pay, order-to-cash, inventory reconciliation, and financial close autonomously.

**Harnesses in production:**
- Context-budgeted schema RAG (only relevant tables per phase)
- SQL validation harness (SELECT only, dry-run validated  --  no DML ever)
- Threat sentinel (blocks cross-module data exfiltration)
- Self-healing SQL (fixes syntax errors before re-run)
- Phase-gated workflow: intake → validate → execute → reconcile → report

---

### Use Case 5: Customer Service / CRM Agents

**What it is:** Agents that handle customer inquiries by querying CRM systems (Salesforce, SAP CRM), cross-referencing with ERP data, and producing a synthesized response or action.

**Harnesses in production:**
- Domain agent per product line (parallel query execution)
- Synthesis agent merges customer profile + order history + support tickets
- Role-based masking (different data visible to external vs internal customers)
- Threat sentinel (blocks querying competitor data or historical PII beyond retention policy)

---

### Use Case 6: Regulatory Compliance Monitoring

**What it is:** Agents that monitor transactions against regulatory rules (GTS  --  Global Trade Services, tax compliance, export controls) and flag violations before they become audit findings.

**Harnesses in production:**
- Meta-path library for compliance-relevant table graphs
- Temporal Graph RAG (queries historical data at specific key dates)
- Threat sentinel (detects temporal inference attempts for restricted periods)
- Validation harness (SQL is read-only, dry-run validated)
- Phase-gated: monitor → flag → evaluate → report → escalate

---

### Use Case 7: IT Service Management (ITSM) Agents

**What it is:** Agents that handle IT tickets  --  diagnosing issues, routing to correct teams, creating change records, closing resolved tickets.

**Harnesses in production:**
- Short-term memory (session context)
- Long-term memory (prior tickets for same user/system)
- Tool harness (ServiceNow / Jira / monitoring tools)
- Generator/Evaluator (ticket response drafted by Generator, quality-graded by Evaluator)
- Human-in-the-loop gates (major incidents require manual approval before action)

---

## Summary Table

| Trend | Core Problem It Solves | KYSM Status |
|---|---|---|
| Generator/Evaluator/Planner Architecture | Self-evaluation bias in single-model systems | Synthesis Agent = Evaluator |
| Phase-Gated Execution with Validation Loops | March of Nines failure cascade | 8-phase orchestrator tracked in Redis |
| Context Budgeting | Context anxiety, performance degradation at high occupancy | Graph embedding → top-K tables per phase |
| Scoped Tool Sets | Tool bloat → failure proliferation across tools | 52 tools, 8 domains, scoped per agent |
| Typed Sub-Agent Output Contracts | Unstructured agent output → synthesis failures | contracts.py  --  7 domain contracts wired |
| Self-Healing SQL with Validation Harness | Syntax errors hard-fail production queries | Phase 5.5  --  dry-run before real execution |
| Distributed Harness Runs Table | No observability in production runs | Redis  --  harness_runs.py |
| Proactive Threat Sentinel | Security as post-execution check instead of gate | Phase 6c  --  6 detection engines |
| Multi-Agent Swarms + Synthesis | Single agent cannot cover all domains deeply | Phase 10  --  planner + synthesis agents |
| Co-optimization with Model Upgrades | Over-engineered harnesses add cost on newer models | Ongoing discipline |

---

## Key Quotes to Remember

> *"The model is not the bottleneck. The harness is. More tools does not mean more capability  --  it means more failure surface."*
>  --  Solo Swift Crafter, Harness Engineering 2026

> *"A single model that generates and evaluates its own work overestimates its own output. You need role separation."*
>  --  Cyril Imhof, This is the Year E45

> *"In the physical world, you go to McKinsey for tacit knowledge. In the agentic world, you buy McKinsey's skill to run inside your AI agent."*
>  --  Cyril Imhof, This is the Year E44

> *"The model is interchangeable. The harness is the moat."*
>  --  The AI Automators, Harness Engineering Series

---

## References

- **Video 1:** Karpathy's March of Nines  --  The AI Automators  --  https://youtu.be/I2K81s0OQto
- **Video 2:** Harness Engineering for Solo Devs  --  Solo Swift Crafter  --  https://youtu.be/DN2mhf0b02s
- **Video 3:** AI Agent Harness is Here  --  This is the Year E44  --  https://youtu.be/ZqM5kbB0D4o
- **Video 4:** Harness Engineering Explained  --  This is the Year E45  --  https://youtu.be/z10zi0F_1fE
- **Stripe Minions:** https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2
- **KYSM Design Principles:** docs/HARNESS_DESIGN_PRINCIPLES.md
- **KYSM Contracts:** backend/app/agents/swarm/contracts.py
- **KYSM Harness Runs:** backend/app/core/harness_runs.py
